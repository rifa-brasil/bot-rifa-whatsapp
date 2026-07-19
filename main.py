import os
import json
import requests
import re
from flask import Flask, request, jsonify

app = Flask(__name__)

# Tu Token de Whapi configurado de forma segura
WHAPI_TOKEN = "zL78J7yS7OM8I3ml5Ybvps1rkcxbKV7K" 
WHAPI_API_URL = "https://gate.whapi.cloud/messages/text"

# Tu número administrativo (configurado con el código de país sin el +)
NUMERO_ADMIN = "5511948824359" 

DB_FILE = "rifa_db.json"

def inicializar_rifa(forzar=False):
    if forzar or not os.path.exists(DB_FILE):
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
    raw_from = msg.get("from", "")
    
    if not raw_from:
        raw_from = chat_id
        
    id_antes_del_arroba = raw_from.split("@")[0]
    numero_persona = re.sub(r'\D', '', id_antes_del_arroba)
    
    # LÍNEA DE CONTROL: Imprime en la consola de Render quién está enviando el mensaje
    print(f"DEBUG: Mensaje recibido de {numero_persona} (Admin esperado: {NUMERO_ADMIN})")
    
    link_directo = f"wa.me/{numero_persona}"
    
    nombre_usuario = msg.get("from_name", "").strip()
    if not nombre_usuario:
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

    # 🔐 NUEVO COMANDO DE RESET (Sin la barra diagonal)
    if mensaje_texto.lower() == "reiniciar rifa":
        if numero_persona == NUMERO_ADMIN:
            inicializar_rifa(forzar=True)
            respuesta = "🔄 *¡La rifa ha sido reseteada por el Administrador!* Todos los 100 números vuelven a estar disponibles.\n\n" + generar_texto_lista()
        else:
            respuesta = "⚠️ Lo siento, no tienes permisos de administrador para ejecutar este comando."

    elif mensaje_texto.lower() in ["hola", "buenas", "lista", "inicio", "rifa"]:
        respuesta = f"¡Hola {nombre_usuario}! Bienvenido a la Rifa Automática. ✨\n\n" + generar_texto_lista() + "\n\n👉 *¿Cómo comprar?* Responde escribiendo el número que deseas (puedes separar varios por comas, ej: *7, 14, 25*)."

    else:
        partes = [p.strip() for p in mensaje_texto.split(",")]
        es_lista_numeros = all(p.isdigit() for p in partes) if partes and mensaje_texto else False

        if es_lista_numeros:
            exitos = []
            ocupados = []
            invalidos = []

            for p in partes:
                num_elegido = int(p)
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
                        exitos.append(num_str.zfill(2))
                    else:
                        ocupados.append(f"*{num_str.zfill(2)}* (de {info['nombre']})")
                else:
                    invalidos.append(p)

            if exitos:
                guardar_rifa(rifa)

            mensajes_resultado = []
            if exitos:
                mensajes_resultado.append(f"✅ ¡Felicidades! Reservaste con éxito: {', '.join(exitos)}.")
            if ocupados:
                mensajes_resultado.append(f"❌ Los siguientes números ya estaban ocupados: {', '.join(ocupados)}.")
            if invalidos:
                mensajes_resultado.append(f"⚠️ Los números fuera de rango (1 al 100) fueron ignorados: {', '.join(invalidos)}.")

            respuesta = "\n".join(mensajes_resultado) + "\n\n" + generar_texto_lista()

    if respuesta:
        enviar_mensaje_whapi(chat_id, respuesta)

    return "OK", 200

if __name__ == "__main__":
    inicializar_rifa()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
