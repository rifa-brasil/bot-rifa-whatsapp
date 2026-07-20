import os
import json
import requests
import re
import uuid
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

app = Flask(__name__)

# 🔑 TOKEN Y CONFIGURACIÓN
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
        data_inicial = {"estado_rifa": "activa", "numeros": {str(i): {"estado": "disponible", "nombre": "", "telefono": "", "enlace": "", "solicitud_id": ""} for i in range(1, 101)}, "solicitudes_pendientes": {}}
        with open(DB_FILE, "w") as f: json.dump(data_inicial, f, indent=4)

def borrar_y_recrear_base_datos():
    if os.path.exists(DB_FILE): os.remove(DB_FILE)
    inicializar_rifa()

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
        info = rifa[str(i)]
        if info["estado"] == "disponible":
            texto += f"🟢 *{num_str}*: Disponible\n"
            disponibles += 1
        elif info["estado"] == "pendiente":
            texto += f"🟡 *{num_str}*: En verificación...\n"
        else:
            texto += f"🔴 *{num_str}*: Ocupado por {info['nombre']}\n"
    texto += f"\n📊 *Resumen:* Quedan {disponibles} números disponibles."
    return texto

def enviar_mensaje_whapi(chat_id, texto, menciones=[]):
    payload = {"to": chat_id, "body": texto}
    if menciones: payload["mentions"] = menciones
    headers = {"accept": "application/json", "content-type": "application/json", "authorization": f"Bearer {WHAPI_TOKEN}"}
    try:
        r = requests.post(WHAPI_API_URL, json=payload, headers=headers)
        return r.status_code in [200, 201]
    except Exception as e:
        print(f"🔴 Error: {e}")
        return False

@app.route("/webhook", methods=["POST"])
def webhook():
    data_webhook = request.get_json() or {}
    messages = data_webhook.get("messages", [])
    if not messages: return "OK", 200

    msg = messages[0]
    mensaje_texto = msg.get("text", {}).get("body", "").strip()
    comando = mensaje_texto.lower()
    chat_id_actual = msg.get("chat_id", "")
    numero_persona = re.sub(r'\D', '', msg.get("from", "").split("@")[0])
    nombre_usuario = msg.get("from_name", f"+{numero_persona}")
    
    data_rifa = obtener_data_completa()
    rifa = data_rifa["numeros"]
    solicitudes = data_rifa.get("solicitudes_pendientes", {})
    es_admin_general = (NUMERO_ADMIN_SEGURO in numero_persona)

    # Lógica de Confirmación/Rechazo
    if (comando.startswith("confirmar ") or comando.startswith("rechazar ")) and es_admin_general:
        partes_cmd = mensaje_texto.split()
        accion = partes_cmd[0].lower()
        req_id_input = partes_cmd[1].strip()
        
        if req_id_input in solicitudes:
            sol = solicitudes[req_id_input]
            user_nums = sol["numeros"]
            mencion_id = sol["telefono"].replace("+", "").strip()
            nums_formatted = ", ".join([n.zfill(2) for n in user_nums])
            grupo_origen = sol["grupo_id"]

            if accion == "confirmar":
                for n in user_nums:
                    rifa[n].update({"estado": "ocupado", "nombre": sol["nombre"], "telefono": sol["telefono"]})
                del solicitudes[req_id_input]
                guardar_data_completa({"numeros": rifa, "solicitudes_pendientes": solicitudes, "estado_rifa": data_rifa["estado_rifa"]})
                
                enviar_mensaje_whapi(chat_id_actual, f"✅ *Solicitud {req_id_input} APROBADA.*")
                msg_grupo = f"🎉 *¡PAGO CONFIRMADO!* 🎉\n\n👤 Usuario: @{mencion_id}\n🎟️ *Números:* {nums_formatted}\n\n¡Gracias por tu compra! 🤝"
                enviar_mensaje_whapi(grupo_origen, msg_grupo, menciones=[f"{mencion_id}@s.whatsapp.net"])

            elif accion == "rechazar":
                for n in user_nums:
                    rifa[n] = {"estado": "disponible", "nombre": "", "telefono": "", "enlace": "", "solicitud_id": ""}
                del solicitudes[req_id_input]
                guardar_data_completa({"numeros": rifa, "solicitudes_pendientes": solicitudes, "estado_rifa": data_rifa["estado_rifa"]})
                
                enviar_mensaje_whapi(chat_id_actual, f"❌ *Solicitud {req_id_input} RECHAZADA.*")
                msg_grupo = f"⚠️ *SOLICITUD CANCELADA* ⚠️\n\nHola @{mencion_id}, tu solicitud para los números *{nums_formatted}* fue rechazada."
                enviar_mensaje_whapi(grupo_origen, msg_grupo, menciones=[f"{mencion_id}@s.whatsapp.net"])
        
        return "OK", 200

    # Lógica de Inicio (Lista)
    elif comando in ["lista", "rifa"]:
        enviar_mensaje_whapi(chat_id_actual, generar_texto_lista())
        return "OK", 200

    return "OK", 200

if __name__ == "__main__":
    inicializar_rifa()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
