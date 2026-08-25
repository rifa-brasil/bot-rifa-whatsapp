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
PRECIO_2_NUMEROS = 18.0
PRECIO_3_NUMEROS = 25.0
PRECIO_4_NUMEROS = 32.0
PRECIO_5_NUMEROS = 40.0

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
        print(f"Respuesta de envío WhatsApp: {response.text}")
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
    texto = "🎟️ *LISTA OFICIAL DE LA RIFA* 🎟️\n\n"
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
            user_id = info.get("user_id", "")
            jid_completo = info.get("jid_completo", "")
            if user_id and jid_completo:
                texto += f"🟡 *{num_str}*: En verificación de pago (@{user_id})...\n"
                menciones_lista.append(jid_completo)
            else:
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
        texto += "\n\n🔒 *ESTADO:* RIFA cerrada/finalizada."
    return texto, menciones_lista

@app.route("/", methods=["GET"])
def index():
    return "Bot de LA RIFA Activo y en Línea!", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error"}), 400

    try:
        # --- IMPRESIÓN DE DEPURACIÓN EN CONSOLA DE RENDER ---
        print("=== NUEVO EVENTO RECIBIDO DE EVOLUTION API ===")
        print(json.dumps(data, indent=2))

        event = data.get("event")
        if event != "messages.upsert":
            return jsonify({"status": "ignored"}), 200

        msg_data = data.get("data", {})
        
        remote_jid = msg_data.get("key", {}).get("remoteJid", "")
        is_group = "@g.us" in remote_jid
        
        # Extracción ultra simplificada y directa del remitente
        sender_full_jid = ""
        if is_group:
            sender_full_jid = (
                msg_data.get("participantAlt") or 
                msg_data.get("participant") or 
                msg_data.get("key", {}).get("participant") or 
                ""
            )
            # Si viene en formato LID pero tenemos el número puro en otra parte, o extraemos dígitos
            if "@lid" in sender_full_jid:
                # Intentamos extraer solo los números de teléfono si están embebidos o usar remoteJid si falla
                digits = "".join(filter(str.isdigit, sender_full_jid))
                if len(digits) > 10:
                    sender_full_jid = f"{digits}@s.whatsapp.net"
        else:
            sender_full_jid = remote_jid

        if not sender_full_jid:
            sender_full_jid = remote_jid

        sender_id = sender_full_jid.split("@")[0].split(":")[0]
        # Asegurar que solo queden números para el sender_id
        sender_id = "".join(filter(str.isdigit, sender_id))

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

        print(f"Mensaje procesado -> Texto: '{mensaje_texto}' | Remitente ID: {sender_id} | Grupo: {remote_jid}")

        data_rifa = obtener_data_completa()
        rifa = data_rifa["numeros"]
        solicitudes = data_rifa.get("solicitudes_pendientes", {})
        bloqueados = data_rifa.get("usuarios_bloqueados", [])
        estado_actual_rifa = data_rifa.get("estado_rifa", "activa")

        if sender_id in bloqueados and sender_id != ADMIN_PHONE:
            return jsonify({"status": "blocked"}), 200

        # --- 1. COMANDO LISTA (PRIORIDAD ABSOLUTA) ---
        if comando in ["lista", "listas"]:
            texto_lista, menciones_lista = generar_texto_lista()
            respuesta = f"¡Hola {push_name}! Estado actual de LA RIFA:\n\n{texto_lista}"
            if estado_actual_rifa == "activa":
                respuesta += "\n\n👉 *¿Cómo comprar?* Envía los números que deseas separados por coma (ej: *7, 14*)."
            
            enviar_whatsapp(remote_jid, respuesta, mencion_jid=menciones_lista if menciones_lista else None)
            return jsonify({"status": "success"}), 200

        # --- 2. REGLAS ---
        if comando in ["/reglas", "reglas"]:
            texto_reglas = (
                f"📌 *Reglas de LA RIFA:*\n"
                f"1. Escribe `lista` para ver los números disponibles.\n"
                f"2. Envía los números deseados separados por comas (ej: `7, 14`)."
            )
            enviar_whatsapp(remote_jid, texto_reglas)
            return jsonify({"status": "success"}), 200

        # --- 3. ADMINISTRADOR ---
        if sender_id == ADMIN_PHONE:
            if comando.startswith("/reset"):
                borrar_y_recrear_base_datos()
                texto_lista, _ = generar_texto_lista()
                enviar_whatsapp(sender_id, "🔄 *¡Reseteado con éxito!*:\n\n" + texto_lista)
                return jsonify({"status": "success"}), 200
 
            elif comando.startswith("conf_") or comando.startswith("rech_"):
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
                        guardar_data_completa(data_rifa)
                        
                        enviar_whatsapp(admin_num:=ADMIN_PHONE, f"✅ Aprobado: {nums_formatted}")
                        txt_conf = f"🎉 ¡Hola @{user_tel}! Tu pago fue verificado. Tus números ({nums_formatted}) ya están registrados."
                        enviar_whatsapp(chat_origen, txt_conf, mencion_jid=jid_completo)

                    elif accion == "rech":
                        for n in user_nums:
                            rifa[n] = {"estado": "disponible", "nombre": "", "user_id": "", "jid_completo": ""}
 
                        del solicitudes[req_id]
                        data_rifa["numeros"] = rifa
                        data_rifa["solicitudes_pendientes"] = solicitudes
                        guardar_data_completa(data_rifa)
                        
                        enviar_whatsapp(ADMIN_PHONE, f"❌ Rechazado ID {req_id}")
                        txt_rech = f"❌ Lo sentimos @{user_tel}, tu solicitud fue rechazada."
                        enviar_whatsapp(chat_origen, txt_rech, mencion_jid=jid_completo)
 
                return jsonify({"status": "success"}), 200

        # --- 4. SELECCIÓN DE NÚMEROS ---
        partes = [p.strip() for p in mensaje_texto.split(",")]
        es_lista_numeros = all(p.isdigit() for p in partes) if partes else False

        if es_lista_numeros:
            if estado_actual_rifa == "finalizada":
                enviar_whatsapp(remote_jid, "🔒 El sistema está cerrado.")
                return jsonify({"status": "success"}), 200

            validos_para_reservar = []
            for p in partes:
                num_elegido = int(p)
                if 1 <= num_elegido <= 100:
                    num_str = str(num_elegido)
                    if rifa[num_str].get("estado", "disponible") == "disponible":
                        validos_para_reservar.append(num_str)

            if validos_para_reservar:
                req_id = "r" + str(uuid.uuid4().int)[:4]
                for n in validos_para_reservar:
                    rifa[n]["estado"] = "pendiente"
                    rifa[n]["nombre"] = push_name
                    rifa[n]["user_id"] = sender_id
                    rifa[n]["jid_completo"] = sender_full_jid

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

                nums_txt = ", ".join([n.zfill(2) for n in validos_para_reservar])
                total, promo = calcular_total_promocion(len(validos_para_reservar))

                msg = f"⏳ Hola @{sender_id}, recibimos tu pedido para: *{nums_txt}*.\n💰 Total: ${total:.2f}\n🟡 Quedan temporalmente reservados."
                enviar_whatsapp(remote_jid, msg, mencion_jid=sender_full_jid)

                link_ok = f"https://wa.me/{BOT_PHONE}?text=conf_{req_id}"
                link_no = f"https://wa.me/{BOT_PHONE}?text=rech_{req_id}"
                txt_admin = f"📥 Solicitud `{req_id}` de @{sender_id} para *{nums_txt}* (${total:.2f}).\n👉 APROBAR: {link_ok}\n👉 RECHAZAR: {link_no}"
                enviar_whatsapp(ADMIN_PHONE, txt_admin, mencion_jid=sender_full_jid)

            return jsonify({"status": "success"}), 200

        return jsonify({"status": "ignored_text"}), 200

    except Exception as e:
        print(f"Error crítico en webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    inicializar_rifa()
    app.run(host="0.0.0.0", port=PORT)
