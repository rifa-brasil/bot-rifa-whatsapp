import os
import json
import requests
import re
import uuid
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

app = Flask(__name__)

# 🔑 TOKEN DE WHAPI
WHAPI_TOKEN = "zL78J7yS7OM8I3ml5Ybvps1rkcxbKV7K" 
WHAPI_API_URL = "https://gate.whapi.cloud/messages/text"

# 🔑 ID DE RESPALDO DE TU GRUPO
GRUPO_CHAT_ID_RESPALDO = "DyI3ISDPZjyKw3w0cD8elC@g.us"

# 👑 ADMINISTRADOR GENERAL
WHATSAPP_ADMIN_PHONE = "5511948824359" 
WHATSAPP_ADMIN_CHAT_ID = f"{WHATSAPP_ADMIN_PHONE}@s.whatsapp.net"
NUMERO_ADMIN_SEGURO = "48824359" 

# 🤖 BOT ASISTENTE
BOT_ASISTENTE_PHONE = "5353215119"

# 🔑 CLAVE SECRETA DE ADMINISTRADOR
CLAVE_RESET = "admin.resetear.rifa.99"

DB_FILE = "rifa_db.json"

def inicializar_rifa():
    try:
        if not os.path.exists(DB_FILE):
            data_inicial = {
                "estado_rifa": "activa",
                "numeros": {str(i): {"estado": "disponible", "nombre": "", "telefono": "", "enlace": "", "solicitud_id": ""} for i in range(1, 101)},
                "solicitudes_pendientes": {}
            }
            with open(DB_FILE, "w") as f: json.dump(data_inicial, f, indent=4)
    except Exception as e:
        print(f"🔴 Error al inicializar JSON: {e}")

def borrar_y_recrear_base_datos():
    try:
        if os.path.exists(DB_FILE): os.remove(DB_FILE)
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
            return data
    except Exception:
        borrar_y_recrear_base_datos()
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
        estado = info.get("estado", "disponible")
        if estado == "disponible":
            texto += f"🟢 *{num_str}*: Disponible\n"
            disponibles += 1
        elif estado == "pendiente":
            texto += f"🟡 *{num_str}*: En verificación de pago...\n"
        else:
            link = info.get("enlace", "")
            texto += f"🔴 *{num_str}*: Ocupado por {info['nombre']} {f'👉 {link}' if link else ''}\n"
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
    try:
        data_webhook = request.get_json()
        if not data_webhook or "messages" not in data_webhook: return "OK", 200
        msg = data_webhook["messages"][0]
        mensaje_texto = msg.get("text", {}).get("body", "").strip()
        comando = mensaje_texto.lower()
        chat_id_actual = msg.get("chat_id", "")
        raw_from = msg.get("from", "")
        numero_persona = re.sub(r'\D', '', raw_from.split("@")[0])
        nombre_usuario = msg.get("from_name", f"+{numero_persona}")

        data_rifa = obtener_data_completa()
        rifa, solicitudes = data_rifa["numeros"], data_rifa.get("solicitudes_pendientes", {})
        es_admin_general = (NUMERO_ADMIN_SEGURO in numero_persona)

        # COMANDOS ADMIN
        if comando.startswith("confirmar ") or comando.startswith("rechazar "):
            if not es_admin_general: return "OK", 200
            partes = mensaje_texto.split()
            accion, req_id = partes[0].lower(), partes[1] if len(partes) > 1 else ""
            
            if req_id in solicitudes:
                sol = solicitudes[req_id]
                mencion_id = sol["telefono"].replace("+", "")
                nums_txt = ", ".join([n.zfill(2) for n in sol["numeros"]])
                
                if accion == "confirmar":
                    for n in sol["numeros"]:
                        rifa[n].update({"estado": "ocupado", "nombre": sol["nombre"], "telefono": sol["telefono"], "enlace": f"wa.me/{mencion_id}"})
                    del solicitudes[req_id]
                    guardar_data_completa({"numeros": rifa, "solicitudes_pendientes": solicitudes, "estado_rifa": data_rifa.get("estado_rifa")})
                    
                    enviar_mensaje_whapi(chat_id_actual, f"✅ Solicitud {req_id} aprobada.")
                    msg_grupo = f"🎉 *¡PAGO CONFIRMADO!* 🎉\n\n👤 Usuario: @{mencion_id}\n🎟️ Números: {nums_txt}\n\n¡Gracias por tu compra! 🤝"
                    enviar_mensaje_whapi(sol["grupo_id"], msg_grupo, menciones=[f"{mencion_id}@s.whatsapp.net"])
                
                else: # RECHAZAR
                    for n in sol["numeros"]:
                        rifa[n] = {"estado": "disponible", "nombre": "", "telefono": "", "enlace": "", "solicitud_id": ""}
                    del solicitudes[req_id]
                    guardar_data_completa({"numeros": rifa, "solicitudes_pendientes": solicitudes, "estado_rifa": data_rifa.get("estado_rifa")})
                    
                    enviar_mensaje_whapi(chat_id_actual, f"❌ Solicitud {req_id} rechazada.")
                    msg_grupo = f"⚠️ *SOLICITUD CANCELADA* ⚠️\n\nHola @{mencion_id}, tu solicitud para los números *{nums_txt}* fue rechazada."
                    enviar_mensaje_whapi(sol["grupo_id"], msg_grupo, menciones=[f"{mencion_id}@s.whatsapp.net"])
            return "OK", 200

        # LISTA / RESERVAS (Lógica existente mantenida)
        elif comando in ["lista", "rifa", "hola"]:
            enviar_mensaje_whapi(chat_id_actual, generar_texto_lista())
        
        # ... resto del código para manejar reservas ...
        
    except Exception as e:
        print(f"Error: {e}")
    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

