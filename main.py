import os
import json
import uuid
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# --- CONFIGURACIÓN DE CREDENCIALES DE WHATSAPP (EVOLUTION API) ---
EVOLUTION_API_URL = os.environ.get("EVOLUTION_API_URL", "https://mi-whatsapp-api-pobo.onrender.com")
EVOLUTION_API_KEY = os.environ.get("EVOLUTION_API_KEY", "56349C29-49EE-4045-94AD-9746CB0FA280")
INSTANCE_NAME = os.environ.get("INSTANCE_NAME", "mi-bot")
ADMIN_PHONE = os.environ.get("ADMIN_PHONE", "5562999999999")  # Número del admin sin '+'

DB_FILE = "rifa_db.json"
VALOR_POR_NUMERO = 10

# --- FUNCIÓN PARA ENVIAR MENSAJES A WHATSAPP (EVOLUTION API) ---
def enviar_mensaje_whatsapp(destinatario_jid, texto, interactive_buttons=None):
    """Envía un mensaje de texto o interactivo a través de Evolution API."""
    if not destinatario_jid:
        print("Error: Intentando enviar mensaje sin destinatario JID.")
        return None
    
    # Asegurar formato de JID si es un número plano
    if "@" not in destinatario_jid:
        destinatario_jid = f"{destinatario_jid}@s.whatsapp.net"

    url = f"{EVOLUTION_API_URL}/message/sendText/{INSTANCE_NAME}"
    headers = {
        "apikey": EVOLUTION_API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "number": destinatario_jid,
        "text": texto
    }

    # Si se requieren botones, Evolution API los soporta mediante opciones avanzadas o texto formateado
    if interactive_buttons:
        botones_texto = "\n\n" + "\n".join([f"👉 Responde con: *{btn['title']}*" for btn in interactive_buttons])
        payload["text"] = texto + botones_texto

    try:
        response = requests.post(url, json=payload, headers=headers)
        return response.json()
    except Exception as e:
        print(f"Error enviando mensaje por Evolution API: {e}")
        return None

# --- RUTA WEB Y WEBHOOK PARA FLASK / RENDER ---
@app.route("/", methods=["GET"])
def handle_web():
    return "Bot de Rifa WhatsApp Activo y en Línea 24/7!", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    """Recepción de mensajes y eventos desde la Evolution API."""
    try:
        body = request.json
        if not body:
            return jsonify({"status": "ignored"}), 200

        event = body.get("event", "").lower()
        if "messages.upsert" not in event:
            return jsonify({"status": "ignored_event"}), 200

        data_msg = body.get("data", {})
        message_data = data_msg.get("message", {})
        
        texto_mensaje = ""
        if "conversation" in message_data:
            texto_mensaje = message_data["conversation"]
        elif "extendedTextMessage" in message_data:
            texto_mensaje = message_data["extendedTextMessage"].get("text", "")

        if not texto_mensaje:
            return jsonify({"status": "no_text"}), 200

        remote_jid = data_msg.get("key", {}).get("remoteJid", "")
        from_me = data_msg.get("key", {}).get("fromMe", False)
        
        if from_me or not remote_jid:
            return jsonify({"status": "from_me_or_no_jid"}), 200

        from_phone = remote_jid.split("@")[0]
        push_name = data_msg.get("pushName", f"Usuario_{from_phone[-4:]}")

        # Procesar de forma sincrónica con la misma lógica
        procesar_mensaje_entrante(from_phone, push_name, texto_mensaje.strip())

        return jsonify({"status": "processed"}), 200
    except Exception as e:
        print(f"Error procesando webhook POST: {e}")
        return jsonify({"status": "error", "details": str(e)}), 500

# --- GESTIÓN DE BASE DE DATOS JSON ---
def inicializar_rifa():
    try:
        if not os.path.exists(DB_FILE):
            data_inicial = {
                "estado_rifa": "activa",
                "numeros": {str(i): {"estado": "disponible", "nombre": "", "user_id": "", "username": ""} for i in range(1, 101)},
                "solicitudes_pendientes": {},
                "idiomas_usuarios": {}
            }
            with open(DB_FILE, "w") as f:
                json.dump(data_inicial, f, indent=4)
    except Exception as e:
        print(f"Error al inicializar JSON: {e}")

def borrar_y_recrear_base_datos():
    try:
        if os.path.exists(DB_FILE):
            os.remove(DB_FILE)
    except Exception as e:
        print(f"Error al eliminar archivo: {e}")
    inicializar_rifa()

def obtener_data_completa():
    inicializar_rifa()
    try:
        with open(DB_FILE, "r") as f:
            data = json.load(f)
            if "estado_rifa" not in data: data["estado_rifa"] = "activa"
            if "solicitudes_pendientes" not in data: data["solicitudes_pendientes"] = {}
            if "idiomas_usuarios" not in data: data["idiomas_usuarios"] = {}
            return data
    except Exception as e:
        borrar_y_recrear_base_datos()
        with open(DB_FILE, "r") as f:
            return json.load(f)

def guardar_data_completa(data):
    try:
        with open(DB_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error al guardar JSON: {e}")

# --- VALORES Y PRECIOS ---
def calcular_premio_total():
    recaudacion_total = 100 * VALOR_POR_NUMERO
    premio = recaudacion_total * 0.55
    return int(premio) if premio.is_integer() else round(premio, 2)

def calcular_precio_total(cantidad, usuario_ya_tiene_compras=False):
    if cantidad <= 0: return 0
    if usuario_ya_tiene_compras: return cantidad * VALOR_POR_NUMERO

    total = 0
    restantes = cantidad
    p5, p4, p3, p2, p1 = int(VALOR_POR_NUMERO * 4), int(VALOR_POR_NUMERO * 3.5), int(VALOR_POR_NUMERO * 2.5), int(VALOR_POR_NUMERO * 1.5), VALOR_POR_NUMERO

    if restantes >= 5:
        total += p5
        restantes -= 5
    else:
        if restantes == 4: return p4
        elif restantes == 3: return p3
        elif restantes == 2: return p2
        elif restantes == 1: return p1

    if restantes > 0:
        total += restantes * VALOR_POR_NUMERO
    return total

def usuario_tiene_jugada_previa(user_id, data_completa):
    rifa = data_completa.get("numeros", {})
    solicitudes = data_completa.get("solicitudes_pendientes", {})
    for num_str, info in rifa.items():
        if info.get("user_id") == user_id and info.get("estado") in ["ocupado", "pendiente"]:
            return True
    for req_id, sol in solicitudes.items():
        if sol.get("user_id") == user_id:
            return True
    return False

# --- GENERADORES DE TEXTO ---
def generar_teclado_idioma():
    return [
        {"id": "lang_es", "title": "es"},
        {"id": "lang_pt", "title": "pt"}
    ]

def generar_texto_lista(lang="es"):
    data = obtener_data_completa()
    rifa = data["numeros"]
    texto = "🎟️ *LISTA OFICIAL DA RIFA (1 ao 100)* 🎟️\n\n" if lang == "pt" else "🎟️ *LISTA OFICIAL DE LA RIFA (1 al 100)* 🎟️\n\n"
    
    disponibles = 0
    for i in range(1, 101):
        num_str = str(i).zfill(2)
        info = rifa[str(i)]
        estado = info.get("estado", "disponible")

        if estado == "disponible":
            texto += f"🟢 *{num_str}*: " + ("Disponível" if lang == "pt" else "Disponible") + "\n"
            disponibles += 1
        elif estado == "pendiente":
            texto += f"🟡 *{num_str}*: " + ("Em verificação..." if lang == "pt" else "En verificación de pago...") + "\n"
        else:
            nombre = info.get("nombre", "Usuário")
            user_id = info.get("user_id", "")
            clean_phone = user_id.split("@")[0] if user_id else ""
            if clean_phone:
                texto += f"🔴 *{num_str}*: Ocupado por [{nombre}](https://wa.me/{clean_phone})\n"
            else:
                texto += f"🔴 *{num_str}*: Ocupado por {nombre}\n"
            
    texto += f"\n📊 *Resumo:* Restam {disponibles} números disponíveis." if lang == "pt" else f"\n📊 *Resumen:* Quedan {disponibles} números disponibles."
    
    estado_actual = data.get("estado_rifa")
    if estado_actual == "finalizada":
        texto += "\n\n🔒 *ESTADO:* Rifa encerrada/finalizada." if lang == "pt" else "\n\n🔒 *ESTADO:* Rifa cerrada/finalizada."
    elif estado_actual == "bloqueada":
        texto += "\n\n⛔ *ESTADO:* Rifa temporariamente bloqueada pelo administrador." if lang == "pt" else "\n\n⛔ *ESTADO:* Rifa temporalmente bloqueada por el administrador."
    return texto

def obtener_texto_reglas(lang="es"):
    premio_actual = calcular_premio_total()
    if lang == "pt":
        return (
            "📌 *REGRAS E DINÂMICA DO GRUPO (Grande Sorteio 100):*\n\n"
            "1️⃣ *Respeito:* Mantenha um ambiente de respeito absoluto.\n"
            "2️⃣ *Números e Promoção:* 100 números (01 a 100).\n"
            f"• 1 núm = {VALOR_POR_NUMERO} reais | • 5 núm = {int(VALOR_POR_NUMERO * 4)} reais (Promoção 1ª jogada).\n"
            f"⚠️ A partir da 2ª jogada, cada número custa exatamente {VALOR_POR_NUMERO} reais.\n"
            "Envie `lista` para ver os disponíveis e escreva os desejados separados por vírgula (ex: *7, 14*).\n"
            "3️⃣ Sorteio realizado apenas com 100% dos números ocupados e pagos.\n"
            "4️⃣ Garantia de reembolso integral solicitando ao administrador.\n"
            f"5️⃣ Prêmio de *{premio_actual} reais* (PIX ou CUP para Cuba).\n"
            "6️⃣ Baseado na Loteria da Flórida (Pick 3) noturna."
        )
    else:
        return (
            "📌 *REGLAS Y DINÁMICA DEL GRUPO (Gran Sorteo 100):*\n\n"
            "1️⃣ *Respeto:* Mantén un ambiente de respeto absoluto.\n"
            "2️⃣ *Números y Promoción:* 100 números (del 01 al 100).\n"
            f"• 1 núm = {VALOR_POR_NUMERO} reales | • 5 núm = {int(VALOR_POR_NUMERO * 4)} reais (Promoción 1ra jugada).\n"
            f"⚠️ A partir de tu 2da jugada, cada número cuesta exactamente {VALOR_POR_NUMERO} reales.\n"
            "Envía `lista` para ver los disponibles y escribe los que deseas separados por coma (ej: *7, 14*).\n"
            "3️⃣ El sorteo se realiza cuando los 100 números estén ocupados y pagados.\n"
            "4️⃣ Garantía de devolución íntegra con el administrador.\n"
            f"5️⃣ Premio de *{premio_actual} reales* (vía PIX o CUP en Cuba).\n"
            "6️⃣ Basado en la Lotería de Florida (Pick 3) nocturna."
        )

# --- PROCESADOR DE MENSAJES ---
def procesar_mensaje_entrante(from_phone, push_name, mensaje_texto):
    comando = mensaje_texto.lower()
    data_rifa = obtener_data_completa()
    idiomas = data_rifa.get("idiomas_usuarios", {})
    lang_usuario = idiomas.get(from_phone, "es")

    # Selección de Idioma por texto rápido
    if comando in ["es", "español", "cubano"]:
        idiomas[from_phone] = "es"
        data_rifa["idiomas_usuarios"] = idiomas
        guardar_data_completa(data_rifa)
        enviar_mensaje_whatsapp(from_phone, f"✅ Idioma cambiado a Español 🇨🇺\n\n{generar_texto_lista('es')}")
        return
    elif comando in ["pt", "português", "brasileiro"]:
        idiomas[from_phone] = "pt"
        data_rifa["idiomas_usuarios"] = idiomas
        guardar_data_completa(data_rifa)
        enviar_mensaje_whatsapp(from_phone, f"✅ Idioma alterado para Português 🇧🇷\n\n{generar_texto_lista('pt')}")
        return

    # Comandos de Administrador
    if from_phone == ADMIN_PHONE:
        if comando.startswith("/bloquear"):
            data_rifa["estado_rifa"] = "bloqueada"
            guardar_data_completa(data_rifa)
            enviar_mensaje_whatsapp(from_phone, "⛔ La rifa ha sido bloqueada temporalmente.")
            return
        elif comando.startswith("/desbloquear"):
            data_rifa["estado_rifa"] = "activa"
            guardar_data_completa(data_rifa)
            enviar_mensaje_whatsapp(from_phone, "🟢 La rifa ha sido desbloqueada.\n\n" + generar_texto_lista("es"))
            return
        elif comando.startswith("/reset"):
            borrar_y_recrear_base_datos()
            enviar_mensaje_whatsapp(from_phone, "🔄 ¡Gran Sorteo 100 ha sido reseteado con éxito!")
            return
        elif comando.startswith("/ganador"):
            partes_cmd = comando.split()
            if len(partes_cmd) > 1 and partes_cmd[1].isdigit():
                num_str = str(int(partes_cmd[1]))
                info_num = data_rifa["numeros"].get(num_str, {})
                if info_num.get("estado") == "ocupado":
                    data_rifa["estado_rifa"] = "finalizada"
                    guardar_data_completa(data_rifa)
                    ganador_nombre = info_num.get("nombre")
                    premio_actual = calcular_premio_total()
                    msg_ganador = f"🎉 ¡Felicidades {ganador_nombre}! Has ganado con el número {num_str.zfill(2)} un premio de {premio_actual} reales."
                    enviar_mensaje_whatsapp(from_phone, msg_ganador)
                    if info_num.get("user_id"):
                        enviar_mensaje_whatsapp(info_num.get("user_id"), msg_ganador)
                    return
        
        # El administrador también puede aprobar o rechazar escribiendo por ejemplo: conf_r1234 o rech_r1234
        if comando.startswith("conf_") or comando.startswith("rech_"):
            procesar_accion_admin(from_phone, comando, data_rifa)
            return

    # Comandos generales
    if comando in ["hola", "buenas", "lista", "inicio", "rifa", "sorteo", "reglas"]:
        if comando == "reglas":
            texto_resp = obtener_texto_reglas(lang_usuario)
        else:
            clean_phone = from_phone
            user_mencion = f"[{push_name}](https://wa.me/{clean_phone})"
            texto_resp = f"¡Hola {user_mencion}!\n\nEstado actual de Gran Sorteo 100:\n\n{generar_texto_lista(lang_usuario)}\n\n🌍 *¿Idioma? Escribe `es` (Español) o `pt` (Português)*"
        
        enviar_mensaje_whatsapp(from_phone, texto_resp)
        return

    # Selección de números separados por coma
    partes = [p.strip() for p in mensaje_texto.split(",")]
    es_lista_numeros = all(p.isdigit() for p in partes) if partes else False

    if es_lista_numeros:
        estado_actual_rifa = data_rifa.get("estado_rifa", "activa")
        if estado_actual_rifa in ["finalizada", "bloqueada"]:
            enviar_mensaje_whatsapp(from_phone, "⛔ Lo sentimos, la lista se encuentra cerrada o bloqueada.")
            return

        rifa = data_rifa["numeros"]
        solicitudes = data_rifa.get("solicitudes_pendientes", {})
        validos_para_reservar = []

        for p in partes:
            num_elegido = int(p)
            if 1 <= num_elegido <= 100:
                num_str = str(num_elegido)
                if rifa[num_str].get("estado", "disponible") == "disponible":
                    validos_para_reservar.append(num_str)

        if validos_para_reservar:
            ya_tiene_compras = usuario_tiene_jugada_previa(from_phone, data_rifa)
            req_id = "r" + str(uuid.uuid4().int)[:4]
            
            for n in validos_para_reservar:
                rifa[n]["estado"] = "pendiente"
                rifa[n]["nombre"] = push_name
                rifa[n]["user_id"] = from_phone

            solicitudes[req_id] = {
                "nombre": push_name,
                "user_id": from_phone,
                "numeros": validos_para_reservar
            }

            data_rifa["numeros"] = rifa
            data_rifa["solicitudes_pendientes"] = solicitudes
            guardar_data_completa(data_rifa)

            nums_solicitados_txt = ", ".join([n.zfill(2) for n in validos_para_reservar])
            cantidad_numeros = len(validos_para_reservar)
            total_a_pagar = calcular_precio_total(cantidad_numeros, usuario_ya_tiene_compras=ya_tiene_compras)

            clean_phone = from_phone
            user_mencion = f"[{push_name}](https://wa.me/{clean_phone})"

            msg_usuario = (
                f"⏳ *SOLICITUD EN PROCESO* ⏳\n\n"
                f"Hola {user_mencion}, tus números (*{nums_solicitados_txt}*) están reservados temporalmente.\n"
                f"💰 Cantidad: *{cantidad_numeros}*\n"
                f"💵 Total a transferir: *{total_a_pagar} reales*\n\n"
                f"Contacta al administrador para pagar."
            )
            enviar_mensaje_whatsapp(from_phone, msg_usuario)

            # Notificar al Administrador con comandos rápidos de texto para aprobar/rechazar
            msg_admin = (
                f"📥 *NUEVA SOLICITUD* (ID: `{req_id}`)\n\n"
                f"👤 *Cliente:* {user_mencion} (`{from_phone}`)\n"
                f"🎟️ *Números:* *{nums_solicitados_txt}*\n"
                f"💵 *Total:* *{total_a_pagar} reales*\n\n"
                f"👉 Para aprobar responde exactamente: `conf_{req_id}`\n"
                f"👉 Para rechazar responde exactamente: `rech_{req_id}`"
            )
            enviar_mensaje_whatsapp(ADMIN_PHONE, msg_admin)

def procesar_accion_admin(admin_phone, comando, data_rifa):
    try:
        accion, req_id = comando.split("_", 1)
        rifa = data_rifa["numeros"]
        solicitudes = data_rifa.get("solicitudes_pendientes", {})

        if req_id not in solicitudes:
            enviar_mensaje_whatsapp(admin_phone, f"⚠️ La solicitud `{req_id}` ya fue procesada o no existe.")
            return

        sol = solicitudes[req_id]
        user_phone = sol["user_id"]
        user_nums = sol["numeros"]
        nums_formatted = ", ".join([n.zfill(2) for n in user_nums])

        if accion == "conf":
            for n in user_nums:
                rifa[n]["estado"] = "ocupado"
                rifa[n]["nombre"] = sol["nombre"]
                rifa[n]["user_id"] = user_phone

            del solicitudes[req_id]
            data_rifa["numeros"] = rifa
            data_rifa["solicitudes_pendientes"] = solicitudes

            if all(rifa[str(n)]["estado"] == "ocupado" for n in range(1, 101)):
                data_rifa["estado_rifa"] = "finalizada"

            guardar_data_completa(data_rifa)
            enviar_mensaje_whatsapp(admin_phone, f"✅ Aprobado con éxito. Números: {nums_formatted}")

            msg_confirmacion = f"🎉 *¡PAGO CONFIRMADO!* 🎉\n\nTus números ({nums_formatted}) ya están oficiales. ¡Muchas felicidades y mucha suerte! 🤝"
            enviar_mensaje_whatsapp(user_phone, msg_confirmacion)

        elif accion == "rech":
            for n in user_nums:
                rifa[n] = {"estado": "disponible", "nombre": "", "user_id": "", "username": ""}

            del solicitudes[req_id]
            data_rifa["numeros"] = rifa
            data_rifa["solicitudes_pendientes"] = solicitudes
            guardar_data_completa(data_rifa)
            
            enviar_mensaje_whatsapp(admin_phone, f"❌ Solicitud rechazada.")
            enviar_mensaje_whatsapp(user_phone, f"❌ Tu solicitud para los números *{nums_formatted}* fue rechazada.")
    except Exception as e:
        print(f"Error procesando acción admin: {e}")

# --- PUNTO DE ENTRADA PRINCIPAL ---
if __name__ == "__main__":
    inicializar_rifa()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
