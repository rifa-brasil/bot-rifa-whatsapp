import os
import json
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# Configuración de Evolution API
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "https://mi-whatsapp-api-pobo.onrender.com")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "55725d7c0b0fb17cb5e6564edac38c1f")
INSTANCE_NAME = os.getenv("INSTANCE_NAME", "mi-bot")

DB_FILE = "rifa_db.json"

def load_db():
    """Carga la base de datos local y asegura la estructura de 1 a 100."""
    if not os.path.exists(DB_FILE):
        db_initial = {
            "numeros": {str(i): {"estado": "disponible", "comprador": None} for i in range(1, 101)}
        }
        save_db(db_initial)
        return db_initial
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Asegurar que existan del 1 al 100 por si acaso
            if "numeros" not in data:
                data["numeros"] = {str(i): {"estado": "disponible", "comprador": None} for i in range(1, 101)}
            return data
    except Exception:
        return {
            "numeros": {str(i): {"estado": "disponible", "comprador": None} for i in range(1, 101)}
        }

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
    return "Bot de Rifa (1-100) con Evolution API activo.", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    print("Webhook recibido:", json.dumps(data, indent=2))

    try:
        event = data.get("event")
        if event == "messages.upsert":
            message_data = data.get("data", {})
            
            if message_data.get("key", {}).get("fromMe", False):
                return jsonify({"status": "ignored_from_me"}), 200

            remote_jid = message_data.get("key", {}).get("remoteJid", "")
            phone_number = remote_jid.split("@")[0]
            
            # Obtener nombre del remitente si viene en el payload
            push_name = message_data.get("pushName", "Participante")

            message_content = message_data.get("message", {})
            text = (
                message_content.get("conversation") or
                message_content.get("extendedTextMessage", {}).get("text") or ""
            ).strip()

            if not text:
                return jsonify({"status": "no_text_found"}), 200

            text_lower = text.lower()
            db = load_db()

            # Comando: lista -> Muestra del 1 al 100 indicando libres y ocupados
            if text_lower == "lista" or text_lower == "/lista":
                msg_lines = ["📋 *LISTA DE NÚMEROS DE LA RIFA (1-100)*\n"]
                for i in range(1, 101):
                    num_str = str(i)
                    info = db["numeros"].get(num_str, {"estado": "disponible"})
                    if info["estado"] == "ocupado":
                        comprador = info.get("comprador", "Ocupado")
                        msg_lines.append(f"❌ {num_str}: <s>{comprador}</s> (Ocupado)")
                    else:
                        msg_lines.append(f"✅ {num_str}: Disponible")
                
                # Dividir el mensaje si es muy largo para WhatsApp (máximo 4000 caracteres aprox)
                full_text = "\n".join(msg_lines)
                send_whatsapp_message(phone_number, full_text)

            # Comando para comprar: ej. "5, 12, 45" o "jugar 5,12"
            elif text_lower.startswith("jugar") or "," in text or text.isdigit():
                # Limpiar texto para extraer solo los números separados por coma
                clean_text = text_lower.replace("jugar", "").replace("comprar", "").strip()
                
                # Extraer números separados por coma
                parts = [p.strip() for p in clean_text.split(",") if p.strip().isdigit()]
                
                if not parts:
                    send_whatsapp_message(phone_number, "⚠️ Formato no reconocido. Para apartar números, envíalos separados por coma (Ejemplo: *5, 12, 25*).")
                    return jsonify({"status": "bad_format"}), 200

                ocupados_intentados = []
                exitosos = []

                for p in parts:
                    if p in db["numeros"]:
                        if db["numeros"][p]["estado"] == "disponible":
                            db["numeros"][p]["estado"] = "ocupado"
                            db["numeros"][p]["comprador"] = push_name
                            exitosos.append(p)
                        else:
                            ocupados_intentados.append(p)

                save_db(db)

                # Construir respuesta
                respuesta = ""
                if exitosos:
                    respuesta += f"🎉 ¡Listo *{push_name}*! Has apartado con éxito los números: *{', '.join(exitosos)}*.\n"
                if ocupados_intentados:
                    respuesta += f"⚠️ Los siguientes números ya estaban ocupados: *{', '.join(ocupados_intentados)}*."
                
                if not respuesta:
                    respuesta = "⚠️ Los números seleccionados ya no están disponibles."

                send_whatsapp_message(phone_number, respuesta)

            else:
                send_whatsapp_message(phone_number, 
                    "🤖 *Bot de Rifa Activo*\n\n"
                    "• Escribe *lista* para ver todos los números del 1 al 100.\n"
                    "• Escribe los números separados por coma (ej: *5, 12, 20*) para apartarlos."
                )

    except Exception as e:
        print(f"Error procesando el webhook: {e}")
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "success"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
