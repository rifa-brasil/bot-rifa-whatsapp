import os
import json
import requests
import re
import uuid
from flask import Flask, request

app = Flask(__name__)

# 🔑 CONFIGURACIÓN
WHAPI_TOKEN = "zL78J7yS7OM8I3ml5Ybvps1rkcxbKV7K" 
WHAPI_API_URL = "https://gate.whapi.cloud/messages/text"
GRUPO_CHAT_ID_RESPALDO = "DyI3ISDPZjyKw3w0cD8elC@g.us"
WHATSAPP_ADMIN_PHONE = "5511948824359" 
WHATSAPP_ADMIN_CHAT_ID = f"{WHATSAPP_ADMIN_PHONE}@s.whatsapp.net"
NUMERO_ADMIN_SEGURO = "48824359"
BOT_ASISTENTE_PHONE = "5353215119"
CLAVE_RESET = "admin.resetear.rifa.99"
DB_FILE = "rifa_db.json"

def inicializar_rifa():
    if not os.path.exists(DB_FILE):
        data = {
            "estado_rifa": "activa",
            "numeros": {str(i): {"estado": "disponible", "nombre": "", "telefono": "", "enlace": "", "solicitud_id": ""} for i in range(1, 101)},
            "solicitudes_pendientes": {}
        }
        with open(DB_FILE, "w") as f: json.dump(data, f, indent=4)

def obtener_data():
    inicializar_rifa()
    with open(DB_FILE, "r") as f: return json.load(f)

def guardar_data(data):
    with open(DB_FILE, "w") as f: json.dump(data, f, indent=4)

def generar_texto_lista():
    data = obtener_data()
    texto = "🎟️ *LISTA OFICIAL DE LA RIFA (1 al 100)* 🎟️\n\n"
    disponibles = 0
    for i in range(1, 101):
        num = str(i).zfill(2)
        info = data["numeros"][str(i)]
        if info["estado"] == "disponible":
            texto += f"🟢 *{num}*: Disponible\n"
            disponibles += 1
        elif info["estado"] == "pendiente":
            texto += f"🟡 *{num}*: En verificación...\n"
        else:
            texto += f"🔴 *{num}*: Ocupado por {info['nombre']}\n"
    texto += f"\n📊 *Resumen:* Quedan {disponibles} números disponibles."
    return texto

def enviar_mensaje(chat_id, texto, menciones=[]):
    headers = {"accept": "application/json", "content-type": "application/json", "authorization": f"Bearer {WHAPI_TOKEN}"}
    payload = {"to": chat_id, "body": texto, "mentions": menciones}
    requests.post(WHAPI_API_URL, json=payload, headers=headers)

@app.route("/webhook", methods=["POST"])
def webhook():
    data_webhook = request.get_json()
    if not data_webhook or "messages" not in data_webhook: return "OK", 200
    
    msg = data_webhook["messages"][0]
    if msg.get("from_me"): return "OK", 200 # Ignorar mensajes propios

    # Extraer texto de forma segura
    txt = (msg.get("text", {}).get("body", "") if "text" in msg else msg.get("body", "")).strip().lower()
    chat_id = msg.get("chat_id", "")
    author = msg.get("author") or msg.get("sender_id") or msg.get("from", "")
    numero = re.sub(r'\D', '', author.split("@")[0])
    es_admin = NUMERO_ADMIN_SEGURO in numero

    # 1. COMANDO LISTA (Flexible)
    if any(x in txt for x in ["lista", "hola", "inicio", "rifa"]):
        enviar_mensaje(chat_id, f"👋 ¡Hola! Aquí tienes la rifa:\n\n{generar_texto_lista()}")
        return "OK", 200

    # 2. RESET
    if txt == CLAVE_RESET and es_admin:
        os.remove(DB_FILE)
        inicializar_rifa()
        enviar_mensaje(chat_id, "🔄 Rifa reseteada.")
        return "OK", 200

    # 3. APROBACIÓN ADMIN
    if (txt.startswith("confirmar ") or txt.startswith("rechazar ")) and es_admin:
        partes = txt.split()
        accion, req_id = partes[0], partes[1]
        data = obtener_data()
        if req_id in data["solicitudes_pendientes"]:
            sol = data["solicitudes_pendientes"][req_id]
            if accion == "confirmar":
                for n in sol["numeros"]:
                    data["numeros"][n].update({"estado": "ocupado", "nombre": sol["nombre"], "telefono": sol["telefono"]})
                enviar_mensaje(f"{sol['telefono'].replace('+', '')}@s.whatsapp.net", "🎉 ¡Pago verificado! Tus números están confirmados.")
            del data["solicitudes_pendientes"][req_id]
            guardar_data(data)
            enviar_mensaje(chat_id, f"✅ Acción {accion} ejecutada.")
        return "OK", 200

    # 4. RESERVA USUARIO
    if re.match(r'^[\d,\s]+$', txt):
        data = obtener_data()
        nums = [n.strip() for n in txt.split(",")]
        # (Aquí va tu lógica de validación de números disponible)
        req_id = "r" + str(uuid.uuid4().int)[:4]
        # Guardar en solicitudes...
        enviar_mensaje(chat_id, "⏳ Solicitud recibida. Esperando confirmación del Admin.")
        enviar_mensaje(WHATSAPP_ADMIN_CHAT_ID, f"📥 Nueva solicitud {req_id} de {numero}. Toca para confirmar: wa.me/{BOT_ASISTENTE_PHONE}?text=confirmar%20{req_id}")
        return "OK", 200

    return "OK", 200

if __name__ == "__main__":
    inicializar_rifa()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
