import os
import json
import uuid
import requests
from flask import Flask, request, jsonify

# --- CONFIGURACIÓN DE FLASK PARA RENDER ---
app = Flask(__name__)

# --- TUS DATOS CONFIGURADOS FIJOS ---
EVOLUTION_API_URL = "https://mi-whatsapp-api-pobo.onrender.com"
EVOLUTION_API_KEY = "55725d7c0b0fb17cb5e6564edac38c1f"
INSTANCE_NAME = "mi-bot"
ADMIN_PHONE = "5511948824359"  # Tu número de administrador
BOT_PHONE = "5562993984530"    # Tu número de bot
PORT = int(os.environ.get("PORT", 10000))

DB_FILE = "rifa_db.json"

# --- TABLA DE PRECIOS Y PROMOCIONES POR CANTIDAD ---
PRECIO_1_NUMERO = 10.0
PRECIO_2_NUMEROS = 18.0  # Paquete de 2
PRECIO_3_NUMEROS = 25.0  # Paquete de 3
PRECIO_4_NUMEROS = 32.0  # Paquete de 4
PRECIO_5_NUMEROS = 40.0  # Paquete de 5

def inicializar_rifa():
    try:
        if not os.path.exists(DB_FILE):
            data_inicial = {
                "estado_rifa": "activa",
                "numeros": {str(i): {"estado": "disponible", "nombre": "", "user_id": "", "jid_completo": ""} for i in range(1, 101)},
                "solicitudes_pendientes": {},
                "usuarios_bloqueados": []
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
            if "usuarios_bloqueados" not in data:
                data["usuarios_bloqueados"] = []
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

def enviar_whatsapp(numero, texto, mencion_jid=None):
    url = f"{EVOLUTION_API_URL}/message/sendText/{INSTANCE_NAME}"
    headers = {
        "apikey": EVOLUTION_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "number": str(numero).strip(),
        "text": texto
    }
    if mencion_jid:
        if isinstance(mencion_jid, list):
            payload["mentioned"] = [m if "@" in m else f"{m}@s.whatsapp.net" for m in mencion_jid]
        else:
            if "@" not in mencion_jid:
                mencion_jid = f"{mencion_jid}@s.whatsapp.net"
            payload["mentioned"] = [mencion_jid]

    try:
        response = requests.post(url, json=payload, headers=headers)
        return response.json()
    except Exception as e:
        print(f"Error enviando WhatsApp a {numero}: {e}")
        return None

def calcular_total_promocion(cantidad):
    if cantidad <= 0:
        return 0.0, "Sin números"
    elif cantidad == 1:
        return PRECIO_1_NUMERO, "Precio estándar (1 número)"
    elif cantidad == 2:
        return PRECIO_2_NUMEROS, "¡Promoción aplicada por 2 números!"
    elif cantidad == 3:
        return PRECIO_3_NUMEROS, "¡Promoción aplicada por 3 números!"
    elif cantidad == 4:
        return PRECIO_4_NUMEROS, "¡Promoción aplicada por 4 números!"
    elif cantidad == 5:
        return PRECIO_5_NUMEROS, "¡Promoción aplicada por 5 números (Súper Paquete)!"
    else:
        adicionales = cantidad - 5
        total = PRECIO_5_NUMEROS + (adicionales * PRECIO_1_NUMERO)
        return total, f"¡Paquete de 5 + {adicionales} número(s) adicional(es)!"

def generar_texto_lista():
    data = obtener_data_completa()
    rifa = data["numeros"]
    texto = "🎟️ *LISTA OFICIAL DE GRAN SORTEO 100* 🎟️\n\n"
    disponibles = 0
    menciones_lista = []
    
    for i in range(1, 101):
        num_str = str(i).zfill(2)
        info = rifa[str(i)]
        estado = info.get("estado", "disponible")

        if estado == "disponible":
            texto += f"🟢 *{num_str}*: Disponible\n"
            disponibles += 1
        elif estado == "pendiente":
            texto += f"🟡 *{num_str}*: En verificación de pago...\n"
        else:
            user_id = info.get("user_id", "")
            jid_completo = info.get("jid_completo", "")
            if user_id and jid_completo:
                texto += f"🔴 *{num_str}*: Ocupado por @{user_id}\n"
                menciones_lista.append(jid_completo)
            else:
                nombre = info.get("nombre", "Usuario")
                texto += f"🔴 *{num_str}*: Ocupado por {nombre}\n"
            
    texto += f"\n📊 *Resumen:* Quedan {disponibles} números disponibles."
    if data.get("estado_rifa") == "finalizada":
        texto += "\n\n🔒 *ESTADO:* Sorteo cerrado/finalizado."
    return texto, menciones_lista

@app.route("/", methods=["GET"])
def index():
    return "Bot de Gran Sorteo 100 para WhatsApp Activo y en Línea 24/7!", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error"}), 400

    try:
        event = data.get("event")
        if event != "messages.upsert":
            return jsonify({"status": "ignored"}), 200

        msg_data = data.get("data", {})
        
        if msg_data.get("key", {}).get("fromMe", False):
            return jsonify({"status": "ignored"}), 200

        remote_jid = msg_data.get("key", {}).get("remoteJid", "")
        is_group = "@g.us" in remote_jid
        
        if is_group:
            sender_full_jid = msg_data.get("participant", "") or msg_data.get("key", {}).get("participant", "")
        else:
            sender_full_jid = remote_jid

        if not sender_full_jid:
            sender_full_jid = remote_jid

        sender_id = sender_full_jid.split("@")[0].split(":")[0]

        message_content = msg_data.get("message", {})
        mensaje_texto = ""
        if "conversation" in message_content:
            mensaje_texto = message_content["conversation"]
        elif "extendedTextMessage" in message_content:
            mensaje_texto = message_content["extendedTextMessage"].get("text", "")

        if not mensaje_texto:
            return jsonify({"status": "no_text"}), 200

        mensaje_texto = mensaje_texto.strip()
        comando = mensaje_texto.lower()
        push_name = msg_data.get("pushName", "Usuario")

        data_rifa = obtener_data_completa()
        rifa = data_rifa["numeros"]
        solicitudes = data_rifa.get("solicitudes_pendientes", {})
        bloqueados = data_rifa.get("usuarios_bloqueados", [])
        estado_actual_rifa = data_rifa.get("estado_rifa", "activa")

        if sender_id in bloqueados and sender_id != ADMIN_PHONE:
            return jsonify({"status": "blocked"}), 200

        # --- COMANDOS DE ADMINISTRADOR ---
        if sender_id == ADMIN_PHONE:
            if comando.startswith("/reset"):
                borrar_y_recrear_base_datos()
                texto_lista, _ = generar_texto_lista()
                enviar_whatsapp(sender_id, "🔄 *¡Gran Sorteo 100 ha sido reseteado con éxito!* Todos los números vuelven a estar disponibles.\n\n" + texto_lista)
                return jsonify({"status": "success"}), 200

            elif comando.startswith("/ganador"):
                partes_cmd = comando.split(" ")
                if len(partes_cmd) < 2:
                    enviar_whatsapp(sender_id, "⚠️ Por favor indica el número ganador. Ejemplo: `/ganador 14`")
                    return jsonify({"status": "success"}), 200
                
                num_ingresado = partes_cmd[1].strip()
                if not num_ingresado.isdigit() or not (1 <= int(num_ingresado) <= 100):
                    enviar_whatsapp(sender_id, "⚠️ El número debe estar entre 1 y 100.")
                    return jsonify({"status": "success"}), 200

                num_str = str(int(num_ingresado))
                info_num = rifa.get(num_str, {})
                estado = info_num.get("estado")

                if estado != "ocupado":
                    enviar_whatsapp(sender_id, f"⚠️ El número *{num_ingresado.zfill(2)}* no está ocupado.")
                    return jsonify({"status": "success"}), 200

                ganador_tel = info_num.get("user_id")
                ganador_jid = info_num.get("jid_completo")
                num_formateado = num_str.zfill(2)

                msg_anuncio = (
                    f"🏆 *¡RESULTADO OFICIAL DE GRAN SORTEO 100!* 🏆\n\n"
                    f"🎯 El Resultado de la Florida Pick 3 es el: *{num_formateado}*\n\n"
                    f"🎉 ¡El usuario @{ganador_tel} es el ganador de este número! Muchas felicidades. 🥳"
                )
                enviar_whatsapp(remote_jid, msg_anuncio, mencion_jid=ganador_jid)

                if ganador_jid:
                    msg_privado = (
                        f"🎉 *¡FELICIDADES!* 🎉\n\n"
                        f"¡Has ganado Gran Sorteo 100 con tu número *{num_formateado}*! 🏆\n\n"
                        f"Por favor, ponte en contacto con la administración para recibir tu premio. 🤝"
                    )
                    enviar_whatsapp(ganador_tel, msg_privado)
                return jsonify({"status": "success"}), 200

            elif comando.startswith("/liberar"):
                partes_cmd = comando.split(" ")
                if len(partes_cmd) > 1:
                    num_lib = partes_cmd[1].strip()
                    if num_lib.isdigit() and 1 <= int(num_lib) <= 100:
                        n_str = str(int(num_lib))
                        rifa[n_str] = {"estado": "disponible", "nombre": "", "user_id": "", "jid_completo": ""}
                        data_rifa["numeros"] = rifa
                        guardar_data_completa(data_rifa)
                        enviar_whatsapp(sender_id, f"🟢 El número {n_str.zfill(2)} ha sido liberado.")
                return jsonify({"status": "success"}), 200

            if comando.startswith("conf_") or comando.startswith("rech_"):
                partes_cb = comando.split("_", 1)
                accion = partes_cb[0]
                req_id = partes_cb[1] if len(partes_cb) > 1 else ""

                if req_id in solicitudes:
                    sol = solicitudes[req_id]
                    user_nombre = sol["nombre"]
                    user_tel = sol["user_id"]
                    user_nums = sol["numeros"]
                    chat_origen = sol["chat_origen"]
                    jid_completo = sol["jid_completo"]
                    nums_formatted = ", ".join([n.zfill(2) for n in user_nums])

                    if accion == "conf":
                        for n in user_nums:
                            rifa[n]["estado"] = "ocupado"
                            rifa[n]["nombre"] = user_nombre
                            rifa[n]["user_id"] = user_tel
                            rifa[n]["jid_completo"] = jid_completo

                        del solicitudes[req_id]
                        data_rifa["numeros"] = rifa
                        data_rifa["solicitudes_pendientes"] = solicitudes

                        if all(rifa[str(n)]["estado"] == "ocupado" for n in range(1, 101)):
                            data_rifa["estado_rifa"] = "finalizada"

                        guardar_data_completa(data_rifa)
                        enviar_whatsapp(sender_id, f"✅ *Aprobado.* Números: {nums_formatted}")

                        texto_pago_confirmado = (
                            f"🎉 *¡Hola @{user_tel}!* 🎉\n\n"
                            f"Tu pago fue verificado. Tus números *({nums_formatted})* ya están registrados a tu nombre."
                        )

                        try:
                            enviar_whatsapp(user_tel, texto_pago_confirmado)
                        except Exception as e:
                            print(f"Error enviando confirmación al privado: {e}")

                        try:
                            if chat_origen != user_tel:
                                enviar_whatsapp(chat_origen, texto_pago_confirmado, mencion_jid=jid_completo)
                        except Exception as e:
                            print(f"Error enviando confirmación al grupo: {e}")

                    elif accion == "rech":
                        for n in user_nums:
                            rifa[n] = {"estado": "disponible", "nombre": "", "user_id": "", "jid_completo": ""}

                        del solicitudes[req_id]
                        data_rifa["numeros"] = rifa
                        data_rifa["solicitudes_pendientes"] = solicitudes
                        guardar_data_completa(data_rifa)
                        enviar_whatsapp(sender_id, f"❌ *Rechazado el ID {req_id}.*")
                        
                        try:
                            enviar_whatsapp(user_tel, f"❌ Tu solicitud para los números *{nums_formatted}* fue rechazada y liberada.")
                        except Exception as e:
                            print(f"Error notificando rechazo: {e}")

                return jsonify({"status": "success"}), 200

        # --- COMANDOS GENERALES Y CONSULTAS ---
        if comando in ["hola", "buenas", "lista", "inicio", "rifa", "sorteo"]:
            texto_lista, menciones_lista = generar_texto_lista()
            respuesta = f"¡Hola {push_name}! Estado actual de Gran Sorteo 100:\n\n{texto_lista}"
            if estado_actual_rifa == "activa":
                respuesta += "\n\n👉 *¿Cómo comprar?* Envía los números que deseas separados por coma (ej: *7, 14*)."
            
            enviar_whatsapp(remote_jid, respuesta, mencion_jid=menciones_lista if menciones_lista else None)
            return jsonify({"status": "success"}), 200

        if comando == "/reglas":
            texto_reglas = (
                f"📌 *Reglas de Gran Sorteo 100:*\n"
                f"1. Escribe `lista` para ver los números disponibles (del 01 al 100).\n"
                f"2. Envía los números que deseas separados por comas (ejemplo: `7, 14`).\n"
                f"3. Revisa el total calculado con promoción y haz tu transferencia.\n"
                f"4. El ganador se define mediante la Lotería de Florida."
            )
            enviar_whatsapp(remote_jid, texto_reglas)
            return jsonify({"status": "success"}), 200

        # --- PROCESAMIENTO DE SELECCIÓN DE NÚMEROS ---
        partes = [p.strip() for p in mensaje_texto.split(",")]
        es_lista_numeros = all(p.isdigit() for p in partes) if partes else False

        if es_lista_numeros:
            if estado_actual_rifa == "finalizada":
                enviar_whatsapp(remote_jid, "🔒 *Lo sentimos, el sistema está cerrado.*")
                return jsonify({"status": "success"}), 200

            ocupados, pendientes, validos_para_reservar, invalidos = [], [], [], []

            for p in partes:
                num_elegido = int(p)
                if 1 <= num_elegido <= 100:
                    num_str = str(num_elegido)
                    info = rifa[num_str]
                    est = info.get("estado", "disponible")

                    if est == "ocupado":
                        ocupados.append(f"*{num_str.zfill(2)}*")
                    elif est == "pendiente":
                        pendientes.append(f"*{num_str.zfill(2)}*")
                    else:
                        validos_para_reservar.append(num_str)
                else:
                    invalidos.append(p)

            mensajes_conflicto = []
            if ocupados:
                mensajes_conflicto.append(f"🔴 El/los número(s) {', '.join(ocupados)} ya está(n) *OCUPADO(S)*.")
            if pendientes:
                mensajes_conflicto.append(f"🟡 El/los número(s) {', '.join(pendientes)} está(n) *EN PROCESO DE VERIFICACIÓN*.")
            if invalidos:
                mensajes_conflicto.append(f"⚠️ El/los número(s) {', '.join(invalidos)} está(n) fuera del rango (1 al 100).")

            if mensajes_conflicto and not validos_para_reservar:
                enviar_whatsapp(remote_jid, f"Hola {push_name}:\n" + "\n".join(mensajes_conflicto))
                return jsonify({"status": "success"}), 200

            if validos_para_reservar:
                req_id = "r" + str(uuid.uuid4().int)[:4]

                for n in validos_para_reservar:
                    rifa[n]["estado"] = "pendiente"

                solicitudes[req_id] = {
                    "nombre": push_name,
                    "user_id": sender_id,
                    "jid_completo": sender_full_jid,
                    "numeros": validos_para_reservar,
                    "chat_origen": remote_jid
                }

                data_rifa["numeros"] = rifa
                data_rifa["solicitudes_pendientes"] = solicitudes
                guardar_data_completa(data_rifa)

                nums_solicitados_txt = ", ".join([n.zfill(2) for n in validos_para_reservar])
                cantidad_nums = len(validos_para_reservar)
                total_a_pagar, promo_txt = calcular_total_promocion(cantidad_nums)

                msg_cliente = (
                    f"⏳ *SOLICITUD RECIBIDA* ⏳\n\n"
                    f"Hola @{sender_id}, recibimos tu pedido para el/los número(s): *{nums_solicitados_txt}*.\n\n"
                    f"💰 *Total a transferir:* ${total_a_pagar:.2f}\n"
                )
                if promo_txt:
                    msg_cliente += f"🔥 *Promoción:* {promo_txt}\n"
                
                msg_cliente += f"\n🟡 Quedan *reservados temporalmente* mientras el administrador verifica tu pago."

                enviar_whatsapp(remote_jid, msg_cliente, mencion_jid=sender_full_jid)

                link_aprobar = f"https://wa.me/{BOT_PHONE}?text=conf_{req_id}"
                link_rechazar = f"https://wa.me/{BOT_PHONE}?text=rech_{req_id}"

                txt_admin = (
                    f"📥 *NUEVA SOLICITUD DE COMPRA* (ID: `{req_id}`)\n\n"
                    f"👤 *Cliente:* {push_name} (@{sender_id})\n"
                    f"🎟️ *Números:* *{nums_solicitados_txt}* ({cantidad_nums} nums)\n"
                    f"💰 *Total Calculado:* ${total_a_pagar:.2f}\n\n"
                    f"Haz clic para gestionar:\n"
                    f"👉 *APROBAR:* {link_aprobar}\n\n"
                    f"👉 *RECHAZAR:* {link_rechazar}"
                )
                
                enviar_whatsapp(ADMIN_PHONE, txt_admin, mencion_jid=sender_full_jid)

            return jsonify({"status": "success"}), 200

    except Exception as e:
        print(f"Error procesando webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    inicializar_rifa()
    app.run(host="0.0.0.0", port=PORT)
