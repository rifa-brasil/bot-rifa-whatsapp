import os
import json
import requests
import re
import uuid
from flask import Flask, request

app = Flask(__name__)

# 🔑 CREDENCIALES WHAPI
WHAPI_TOKEN = "zL78J7yS7OM8I3ml5Ybvps1rkcxbKV7K" 
WHAPI_API_URL = "https://gate.whapi.cloud/messages/text"

# 👑 CONFIGURACIÓN DE CONTACTOS
WHATSAPP_ADMIN_PHONE = "5511948824359" 
WHATSAPP_ADMIN_CHAT_ID = f"{WHATSAPP_ADMIN_PHONE}@s.whatsapp.net"
BOT_ASISTENTE_PHONE = "5353215119"
GRUPO_CHAT_ID_RESPALDO = "DyI3ISDPZjyKw3w0cD8elC@g.us"
DB_FILE = "rifa_db.json"

# --- FUNCIÓN DE ENVÍO WHAPI ---
def enviar_mensaje_whapi(chat_id, texto):
    payload = {"to": chat_id, "body": texto}
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Bearer {WHAPI_TOKEN}"
    }
    try:
        r = requests.post(WHAPI_API_URL, json=payload, headers=headers)
        return r.status_code in [200, 201]
    except Exception as e:
        print(f"🔴 Error al enviar mensaje: {e}")
        return False

# --- LÓGICA DE BASE DE DATOS (Mantiene tu estado actual) ---
def obtener_data_completa():
    if not os.path.exists(DB_FILE):
        return {"numeros": {str(i): {"estado": "disponible"} for i in range(1, 101)}, "solicitudes_pendientes": {}}
    with open(DB_FILE, "r") as f: return json.load(f)

# --- WEBHOOK PRINCIPAL ---
@app.route("/webhook", methods=["POST"])
def webhook():
    data_webhook = request.get_json(silent=True) or {}
    messages = data_webhook.get("messages", [])
    if not messages: return "OK", 200

    msg = messages[0]
    mensaje_texto = msg.get("text", {}).get("body", "").strip()
    chat_id_actual = msg.get("chat_id", "")
    numero_persona = re.sub(r'\D', '', chat_id_actual.split("@")[0])
    nombre_usuario = msg.get("from_name", f"+{numero_persona}")

    # Detectar intento de compra (ej: "7, 14")
    if mensaje_texto.replace(",", "").replace(" ", "").isdigit():
        req_id = "r" + str(uuid.uuid4().int)[:4]
        
        # 1. Notificación al cliente en el grupo/chat
        txt_confirmacion = "⏳ *SOLICITUD RECIBIDA*\nTu reserva está pendiente de verificación."
        enviar_mensaje_whapi(chat_id_actual, txt_confirmacion)

        # 2. NOTIFICACIÓN PRIVADA AL ADMIN (Esto hará que suene tu teléfono)
        txt_admin = (
            f"📥 *NUEVA COMPRA* (ID: `{req_id}`)\n"
            f"👤 Cliente: {nombre_usuario}\n"
            f"🎟️ Números: *{mensaje_texto}*\n\n"
            f"🟢 Confirmar: wa.me/{BOT_ASISTENTE_PHONE}?text=confirmar%20{req_id}"
        )
        # Se envía directo al chat privado del administrador (tu número)
        enviar_mensaje_whapi(WHATSAPP_ADMIN_CHAT_ID, txt_admin)
        
        return "OK", 200

    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
