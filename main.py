import os
import json
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# Configuración de Evolution API con tus datos reales
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "https://mi-whatsapp-api-pobo.onrender.com")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "55725d7c0b0fb17cb5e6564edac38c1f")
INSTANCE_NAME = os.getenv("INSTANCE_NAME", "mi-bot")

DB_FILE = "rifa_db.json"

def load_db():
    """Carga la base de datos local de la rifa."""
    if not os.path.exists(DB_FILE):
        return {"participantes": [], "numeros_vendidos": []}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"participantes": [], "numeros_vendidos": []}

def save_db(data):
    """Guarda la base de datos local."""
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def send_whatsapp_message(number, text):
    """Envía un mensaje de texto a través de Evolution API."""
    url = f"{EVOLUTION_API_URL}/message/sendText/{INSTANCE_NAME}"
    headers = {
        "Content-Type": "application/json",
        "apikey": EVOLUTION_API_KEY
    }
    payload = {
        "number": number,
        "text": text
    }
    try:
        response = requests.post(url, json=payload, headers=headers)
        return response.json()
    except Exception as e:
        print(f"Error enviando mensaje por WhatsApp: {e}")
        return None

@app.route("/", methods=["GET"])
def home():
    return "Bot de Rifa con Evolution API activo y funcionando correctamente.", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    """Endpoint que recibe los eventos y mensajes entrantes desde Evolution API."""
    data = request.json
    print("Webhook recibido:", json.dumps(data, indent=2))

    try:
        event = data.get("event")
        if event == "messages.upsert":
            message_data = data.get("data", {})
            
            # Evitar bucles respondiendo a mensajes propios
            if message_data.get("key", {}).get("fromMe", False):
                return jsonify({"status": "ignored_from_me"}), 200

            remote_jid = message_data.get("key", {}).get("remoteJid", "")
            phone_number = remote_jid.split("@")[0]
            
            message_content = message_data.get("message", {})
            text = (
                message_content.get("conversation") or
                message_content.get("extendedTextMessage", {}).get("text") or ""
            ).strip().lower()

            if not text:
                return jsonify({"status": "no_text_found"}), 200

            db = load_db()

            if text.startswith("/estado") or text == "estado":
                total = len(db.get("numeros_vendidos", []))
                send_whatsapp_message(phone_number, f"📊 *Estado de la Rifa*\n\nNúmeros ocupados hasta el momento: {total}.")

            elif text.startswith("/comprar") or text == "comprar":
                send_whatsapp_message(phone_number, "🎟️ Para registrar tu número o participar, por favor indícate escribiendo el número que deseas seguido de tu nombre.")

            else:
                send_whatsapp_message(phone_number, "¡Hola! Bienvenido al sistema de rifas. Escribe *estado* para ver los números o *comprar* para participar.")

    except Exception as e:
        print(f"Error procesando el webhook: {e}")
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "success"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
