import os
import json
import requests
import re
from flask import Flask, request, jsonify

app = Flask(__name__)

# Tu Token de Whapi configurado de forma segura
WHAPI_TOKEN = "zL78J7yS7OM8I3ml5Ybvps1rkcxbKV7K" 
WHAPI_API_URL = "https://gate.whapi.cloud/messages/text"

DB_FILE = "rifa_db.json"

def inicializar_rifa():
    if not os.path.exists(DB_FILE):
        rifa = {str(i): {"estado": "disponible", "nombre": "", "telefono": ""} for i in range(1, 101)}
        with open(DB_FILE, "w") as f:
            json.dump(rifa, f, indent=4)

def obtener_rifa():
    with open(DB_FILE, "r") as f:
        return json.load(f)

def guardar_rifa(rifa):
    with open(DB_FILE, "w") as f:
        json.dump(rifa, f, indent=4)

def generar_texto_lista():
    rifa = obtener_rifa()
    texto = "🎟️ *LISTA OFICIAL DE LA RIFA (1 al 100)* 🎟️\n\n"
    disponibles = 0
    for i in range(1, 101):
        num_str = str(i).zfill(2)
        info = rifa[str(i)]
        if info["estado"] == "disponible":
            texto += f"🟢 *{num_str}*: Disponible\n"
            disponibles += 1
        else:
            if info.get("enlace"):
                link = info["enlace"]
            elif info.get("telefono"):
                tel_limpio = info["telefono"].replace("+", "").strip()
                link = f"wa.me/{tel_limpio}"
            else:
                link = ""

            if link:
                texto += f"🔴 *{num_str}*: Ocupado por {info['nombre']} 👉 {link}\n"
            else:
                texto += f"🔴 *{num_str}*: Ocupado por {info['nombre']}\n"
            
    texto += f"\n📊 *Resumen:* Quedan {disponibles} números disponibles."
    return texto

def enviar_mensaje_whapi(chat_id, texto):
    payload = {
        "to": chat_id,
        "body": texto
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Bearer {WHAPI_TOKEN}"
    }
    try:
        response = requests.post(WHAPI_API_URL, json=payload, headers=headers)
        print(f"Respuesta de Whapi: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error al enviar a Whapi: {e}")

@app.route("/", methods=["GET"])
def home():
    return "Servidor conectado con Whapi listo.", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    if not data:
        return "No data", 400

    messages = data.get("messages", [])
    if not messages:
        return "No messages", 200

    msg = messages[0]
    
    if msg.get("from_me", False):
        return "Sent by me", 200

    chat_id = msg.get("chat_id", "")
    sender_id = msg.get("sender_id", "")
    
    # Tomamos el identificador del emisor
    raw_sender = sender_id if sender_id else chat_id
    
    # 1. Quitamos el @g.us o @c.us si viene incluido
    id_antes_del_arroba = raw_sender.split("@")[0]
    
    # 2. Si Whapi junta el ID del grupo y el del usuario con un guion (ej: 5511999999999-162839@g.us)
    # nos quedamos estrictamente con la parte del número del usuario que suele venir después del guion
    # o si viene al revés, extraemos solo la cadena numérica limpia del teléfono.
    if "-" in id_antes_del_arroba:
        partes = id_antes_del_arroba.split("-")
        # Por lo general en Whapi el formato de participante de grupo es IDGRUPO-IDUSUARIO o viceversa.
        # Buscamos cuál de las partes parece un número de teléfono real (más de 8 dígitos)
        numero_persona = partes[1] if len(partes[1]) >= 8 else partes[0]
    else:
        numero_persona = id_antes_del_arroba

    # 3. Limpieza final: dejamos SOLO los números (eliminando letras o símbolos raros residuales)
    numero_persona = re.sub(r'\D', '', numero_persona)
    
    link_directo = f"wa.me/{numero_persona}"
    
    # Lógica para obtener el nombre
    nombre_usuario = msg.get("sender_name", "").strip()
    if not nombre_usuario:
        nombre_usuario = msg.get("contact", {}).get("name", "").strip()
    
    if not nombre_usuario:
        nombre_usuario = f"+{numero_persona}"
    
    text_obj = msg.get("text", {})
    mensaje_texto = text_obj.get("body", "").strip() if text_obj else ""

    inicializar_rifa()
    rifa = obtener_rifa()

    respuesta = ""

    if mensaje_texto.lower() in ["hola", "buenas", "lista", "inicio", "rifa"]:
        respuesta = f"¡Hola {nombre_usuario}! Bienvenido a la Rifa Automática. ✨\n\n" + generar_texto_lista() + "\n\n👉 *¿Cómo comprar?* Responde escribiendo el número que deseas."

    elif mensaje_texto.isdigit():
        num_elegido = int(mensaje_texto)
        if 1 <= num_elegido <= 100:
            num_str = str(num_elegido)
            info = rifa[num_str]
            if info["estado"] == "disponible":
                rifa[num_str] = {
                    "estado": "ocupado",
                    "nombre": nombre_usuario,
                    "telefono": f"+{numero_persona}",
                    "enlace": link_directo
                }
                guardar_rifa(rifa)
                respuesta = f"✅ ¡Felicidades! El número *{num_str.zfill(2)}* ha sido reservado por {nombre_usuario}.\n\n" + generar_texto_lista()
            else:
                respuesta = f"❌ El número *{num_str.zfill(2)}* ya está ocupado por {info['nombre']}.\n\n" + generar_texto_lista()

    if respuesta:
        enviar_mensaje_whapi(chat_id, respuesta)

    return "OK", 200

if __name__ == "__main__":
    inicializar_rifa()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
