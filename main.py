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
BOT_ASISTENTE_PHONE = "5353215119"
DB_FILE = "rifa_db.json"

def inicializar_rifa():
    if not os.path.exists(DB_FILE):
        data_inicial = {"estado_rifa": "activa", "numeros": {str(i): {"estado": "disponible", "nombre": "", "telefono": "", "solicitud_id": ""} for i in range(1, 101)}, "solicitudes_pendientes": {}}
        with open(DB_FILE, "w") as f: json.dump(data_inicial, f, indent=4)

def obtener_data_completa():
    inicializar_rifa()
    with open(DB_FILE, "r") as f: return json.load(f)

def guardar_data_completa(data):
    with open(DB_FILE, "w") as f: json.dump(data, f, indent=4)

def generar_texto_lista():
    data = obtener_data_completa()
    rifa = data["numeros"]
    texto = "🎟️ *LISTA OFICIAL DE LA RIFA (1 al 100)* 🎟️\n\n"
    disponibles = 0
    for i in range(1, 101):
        num_str = str(i).zfill(2)
        estado = rifa[str(i)]["estado"]
        if estado == "disponible":
            texto += f"🟢 *{num_str}*: Disponible\n"
            disponibles += 1
        elif estado == "pendiente":
            texto += f"🟡 *{num_str}*: Verificando...\n"
        else:
            texto += f"🔴 *{num_str}*: Ocupado por {rifa[str(i)]['nombre']}\n"
    texto += f"\n📊 *Resumen:* Quedan {disponibles} disponibles."
    return texto

def enviar_mensaje_whapi(chat_id, texto, menciones=[]):
    payload = {"to": chat_id, "body": texto}
    if menciones: payload["mentions"] = menciones
    headers = {"accept": "application/json", "content-type": "application/json", "authorization": f"Bearer {WHAPI_TOKEN}"}
    requests.post(WHAPI_API_URL, json=payload, headers=headers)

@app.route("/webhook", methods=["POST"])
def webhook():
    data_webhook = request.get_json() or {}
    messages = data_webhook.get("messages", [])
    if not messages: return "OK", 200

    msg = messages[0]
    texto_usuario = msg.get("text", {}).get("body", "").strip()
    comando = texto_usuario.lower()
    chat_id = msg.get("chat_id", "")
    sender_id = re.sub(r'\D', '', msg.get("from", "").split("@")[0])
    nombre_usuario = msg.get("from_name", f"+{sender_id}")
    
    data = obtener_data_completa()
    
    # 1. COMANDOS ADMIN (Confirmar/Rechazar)
    if (comando.startswith("confirmar ") or comando.startswith("rechazar ")) and sender_id == "48824359":
        req_id = comando.split()[1]
        if req_id in data["solicitudes_pendientes"]:
            sol = data["solicitudes_pendientes"][req_id]
            mencion_id = sol["telefono"].replace("+", "")
            if comando.startswith("confirmar"):
                for n in sol["numeros"]: data["numeros"][n].update({"estado": "ocupado", "nombre": sol["nombre"]})
                enviar_mensaje_whapi(chat_id, f"✅ Solicitud {req_id} aprobada.")
                enviar_mensaje_whapi(sol["grupo_id"], f"🎉 *¡PAGO CONFIRMADO!* 🎉\n👤 @{mencion_id}\n🎟️ *Números:* {', '.join(sol['numeros'])}", menciones=[f"{mencion_id}@s.whatsapp.net"])
            else:
                for n in sol["numeros"]: data["numeros"][n]["estado"] = "disponible"
                enviar_mensaje_whapi(chat_id, f"❌ Solicitud {req_id} rechazada.")
                enviar_mensaje_whapi(sol["grupo_id"], f"⚠️ *SOLICITUD CANCELADA* ⚠️\nHola @{mencion_id}, tu reserva de los números {', '.join(sol['numeros'])} fue rechazada.", menciones=[f"{mencion_id}@s.whatsapp.net"])
            del data["solicitudes_pendientes"][req_id]
            guardar_data_completa(data)
        return "OK", 200

    # 2. PROCESAR NÚMEROS (Ej: "7, 14")
    partes = [p.strip() for p in texto_usuario.split(",")]
    if all(p.isdigit() for p in partes):
        validos = [p for p in partes if 1 <= int(p) <= 100 and data["numeros"][str(int(p))]["estado"] == "disponible"]
        if validos:
            req_id = "r" + str(uuid.uuid4().int)[:4]
            data["solicitudes_pendientes"][req_id] = {"nombre": nombre_usuario, "telefono": f"+{sender_id}", "numeros": validos, "grupo_id": chat_id}
            for n in validos: data["numeros"][n]["estado"] = "pendiente"
            guardar_data_completa(data)
            enviar_mensaje_whapi(chat_id, f"⏳ *Solicitud recibida:* {', '.join(validos)}. Esperando confirmación de admin.")
            enviar_mensaje_whapi(WHATSAPP_ADMIN_CHAT_ID, f"📥 *NUEVA COMPRA* (ID: `{req_id}`)\n👤 {nombre_usuario}\n🎟️ {', '.join(validos)}\n\n🟢 Confirmar: wa.me/{BOT_ASISTENTE_PHONE}?text=confirmar%20{req_id}")
        else:
            enviar_mensaje_whapi(chat_id, "⚠️ Esos números no están disponibles o no son válidos.")
        return "OK", 200

    # 3. LISTA
    if comando in ["lista", "rifa", "hola"]:
        enviar_mensaje_whapi(chat_id, generar_texto_lista())
        
    return "OK", 200

if __name__ == "__main__":
    inicializar_rifa()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
