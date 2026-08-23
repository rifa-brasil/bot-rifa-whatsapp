import os
import json
import uuid
from flask import Flask, request, jsonify

app = Flask(__name__)

DB_FILE = "rifa_db.json"
VALOR_POR_NUMERO = 10
ADMIN_WHATSAPP_JID = os.environ.get("ADMIN_WHATSAPP_JID", "5562900000000@s.whatsapp.net") # Pon aquí tu número con @s.whatsapp.net o configúralo en variables de entorno

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
            if "estado_rifa" not in data:
                data["estado_rifa"] = "activa"
            if "solicitudes_pendientes" not in data:
                data["solicitudes_pendientes"] = {}
            if "idiomas_usuarios" not in data:
                data["idiomas_usuarios"] = {}
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

def calcular_premio_total():
    recaudacion_total = 100 * VALOR_POR_NUMERO
    premio = recaudacion_total * 0.55
    if premio.is_integer():
        return int(premio)
    return round(premio, 2)

def calcular_precio_total(cantidad, usuario_ya_tiene_compras=False):
    if cantidad <= 0:
        return 0
    if usuario_ya_tiene_compras:
        return cantidad * VALOR_POR_NUMERO

    total = 0
    restantes = cantidad
    p5 = int(VALOR_POR_NUMERO * 4)
    p4 = int(VALOR_POR_NUMERO * 3.5)
    p3 = int(VALOR_POR_NUMERO * 2.5)
    p2 = int(VALOR_POR_NUMERO * 1.5)
    p1 = VALOR_POR_NUMERO

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

def generar_texto_lista(lang="es"):
    data = obtener_data_completa()
    rifa = data["numeros"]
    
    if lang == "pt":
        texto = "🎟️ *LISTA OFICIAL DA RIFA (1 ao 100)* 🎟️\n\n"
    else:
        texto = "🎟️ *LISTA OFICIAL DE LA RIFA (1 al 100)* 🎟️\n\n"
        
    disponibles = 0
    for i in range(1, 101):
        num_str = str(i).zfill(2)
        info = rifa[str(i)]
        estado = info.get("estado", "disponible")

        if estado == "disponible":
            texto += f"🟢 *{num_str}*: " + ("Disponível" if lang == "pt" else "Disponible") + "\n"
            disponibles += 1
        elif estado == "pendiente":
            texto += f"🟡 *{num_str}*: " + ("Em verificação de pagamento..." if lang == "pt" else "En verificación de pago...") + "\n"
        else:
            nombre = info.get("nombre", "Usuário")
            user_id = info.get("user_id", "")
            # En WhatsApp el enlace al usuario se hace con wa.me usando los dígitos limpios del número
            clean_phone = user_id.split("@")[0] if user_id else ""
            
            if clean_phone:
                texto += f"🔴 *{num_str}*: Ocupado por [{nombre}](https://wa.me/{clean_phone})\n"
            else:
                texto += f"🔴 *{num_str}*: Ocupado por {nombre}\n"
             
    if lang == "pt":
        texto += f"\n📊 *Resumo:* Restam {disponibles} números disponíveis."
    else:
        texto += f"\n📊 *Resumen:* Quedan {disponibles} números disponibles."
        
    estado_actual = data.get("estado_rifa")
    if estado_actual == "finalizada":
        texto += "\n\n🔒 *ESTADO:* " + ("Rifa encerrada/finalizada." if lang == "pt" else "Rifa cerrada/finalizada.")
    elif estado_actual == "bloqueada":
        texto += "\n\n⛔ *ESTADO:* " + ("Rifa temporariamente bloqueada pelo administrador." if lang == "pt" else "Rifa temporalmente bloqueada por el administrador.")
    return texto

def obtener_texto_reglas(lang="es"):
    premio_actual = calcular_premio_total()
    if lang == "pt":
        return (
            "📌 *REGRAS E DINÂMICA DO GRUPO (Grande Sorteio 100):*\n\n"
            "1️⃣ *Respeito:* Mantenha um ambiente de respeito absoluto...\n"
            f"✨ *Valores para sua primeira jogada:* 1 núm = {VALOR_POR_NUMERO} reais...\n"
            f"5️⃣ *Entrega do Prêmio:* {premio_actual} reais via PIX o CUP.\n"
            "🤝 Grupo: https://chat.whatsapp.com/HEaEIKaEjksJRrWEKcIVEo"
        )
    else:
        return (
            "📌 *REGLAS Y DINÁMICA DEL GRUPO (Gran Sorteo 100):*\n\n"
            "1️⃣ *Respeto:* Mantén un ambiente de respeto absoluto...\n"
            f"✨ *Valores para tu primera jugada:* 1 núm = {VALOR_POR_NUMERO} reales...\n"
            f"5️⃣ *Entrega del Premio:* {premio_actual} reales vía PIX o CUP.\n"
            "🤝 Grupo: https://chat.whatsapp.com/HEaEIKaEjksJRrWEKcIVEo"
        )

@app.route("/", methods=["GET"])
def index():
    return "Bot de Rifa WhatsApp Activo y en Línea 24/7!", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if not data:
        return jsonify({"status": "ignored"}), 200

    try:
        # Extracción segura de datos desde la estructura de Evolution API
        event = data.get("event")
        if event != "messages.upsert":
            return jsonify({"status": "ignored"}), 200

        data_msg = data.get("data", {})
        message_data = data_msg.get("message", {})
        
        # Obtener texto del mensaje (soporta texto plano y extendedText)
        texto_mensaje = ""
        if "conversation" in message_data:
            texto_mensaje = message_data["conversation"]
        elif "extendedTextMessage" in message_data:
            texto_mensaje = message_data["extendedTextMessage"].get("text", "")

        if not texto_mensaje:
            return jsonify({"status": "no_text"}), 200

        remote_jid = data_msg.get("key", {}).get("remoteJid", "") # Ejemplo: 5562999999999@s.whatsapp.net
        from_me = data_msg.get("key", {}).get("fromMe", False)
        
        if from_me:
            return jsonify({"status": "from_me_ignored"}), 200

        push_name = data_msg.get("pushName", "Usuario")
        comando = texto_mensaje.strip().lower()

        data_rifa = obtener_data_completa()
        idiomas = data_rifa.get("idiomas_usuarios", {})
        lang_usuario = idiomas.get(remote_jid, "es")

        # Comandos básicos
        if comando in ["hola", "buenas", "lista", "inicio", "rifa", "sorteo"]:
            clean_phone = remote_jid.split("@")[0]
            user_mencion = f"[{push_name}](https://wa.me/{clean_phone})"
            respuesta = f"¡Hola {user_mencion}! Estado actual:\n\n{generar_texto_lista(lang_usuario)}"
            # Aquí mandarías la respuesta a través de tu cliente Evolution API usando requests.post(...)
            return jsonify({"status": "success", "response": respuesta}), 200

        # Lógica de números (ej: 7, 14)
        partes = [p.strip() for p in texto_mensaje.split(",")]
        es_lista_numeros = all(p.isdigit() for p in partes) if partes else False

        if es_lista_numeros:
            rifa = data_rifa["numeros"]
            solicitudes = data_rifa.get("solicitudes_pendientes", {})
            estado_actual_rifa = data_rifa.get("estado_rifa", "activa")

            if estado_actual_rifa in ["finalizada", "bloqueada"]:
                return jsonify({"status": "rifa_closed"}), 200

            validos_para_reservar = []
            for p in partes:
                num_elegido = int(p)
                if 1 <= num_elegido <= 100:
                    num_str = str(num_elegido)
                    if rifa[num_str].get("estado") == "disponible":
                        validos_para_reservar.append(num_str)

            if validos_para_reservar:
                ya_tiene_compras = usuario_tiene_jugada_previa(remote_jid, data_rifa)
                req_id = "r" + str(uuid.uuid4().int)[:4]
                
                for n in validos_para_reservar:
                    rifa[n]["estado"] = "pendiente"

                solicitudes[req_id] = {
                    "nombre": push_name,
                    "user_id": remote_jid,
                    "numeros": validos_para_reservar
                }

                data_rifa["numeros"] = rifa
                data_rifa["solicitudes_pendientes"] = solicitudes
                guardar_data_completa(data_rifa)

                cantidad = len(validos_para_reservar)
                total = calcular_precio_total(cantidad, ya_tiene_compras)
                nums_txt = ", ".join([n.zfill(2) for n in validos_para_reservar])
                
                clean_phone = remote_jid.split("@")[0]
                user_mencion = f"[{push_name}](https://wa.me/{clean_phone})"
                
                # Respuesta de reserva pendiente al usuario y aviso al admin
                print(f"Reserva creada: {nums_txt} para {user_mencion} por {total} reales.")

        return jsonify({"status": "processed"}), 200

    except Exception as e:
        print(f"Error procesando webhook: {e}")
        return jsonify({"status": "error", "details": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
