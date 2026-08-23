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
    """Carga la base de datos local y asegura la estructura completa de la rifa."""
    if not os.path.exists(DB_FILE):
        db_initial = {
            "numeros": {str(i): {"estado": "disponible", "comprador": None, "telefono": None} for i in range(1, 101)},
            "config": {
                "grupo_activo": None  # Aquí guardamos el JID del grupo donde se interactúa
            }
        }
        save_db(db_initial)
        return db_initial
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "numeros" not in data:
                data["numeros"] = {str(i): {"estado": "disponible", "comprador": None, "telefono": None} for i in range(1, 101)}
            if "config" not in data:
                data["config"] = {"grupo_activo": None}
            return data
    except Exception:
        return {
            "numeros": {str(i): {"estado": "disponible", "comprador": None, "telefono": None} for i in range(1, 101)},
            "config": {"grupo_activo": None}
        }

def save_db(data):
    """Guarda la base de datos local."""
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def send_whatsapp_message(recipient_id, text):
    """
    Envía un mensaje a través de Evolution API.
    'recipient_id' puede ser un número privado (ej: '5562999999999') 
    o un JID de grupo completo (ej: '1203630...@@g.us').
    """
    url = f"{EVOLUTION_API_URL}/message/sendText/{INSTANCE_NAME}"
    headers = {
        "Content-Type": "application/json",
        "apikey": EVOLUTION_API_KEY
    }
    payload = {
        "number": recipient_id,
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
    return "Bot de Rifa Avanzado con Evolution API activo.", 200

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
            participant_jid = message_data.get("key", {}).get("participant", "") # Si viene de un grupo, aquí está el usuario real
            
            # Detectar si es un mensaje de grupo
            is_group = remote_jid.endswith("@g.us")
            
            # Extraer número o identificador del remitente para chats privados
            if is_group:
                group_id = remote_jid
                sender_id = participant_jid.split("@")[0] if participant_jid else remote_jid
            else:
                group_id = None
                sender_id = remote_jid.split("@")[0]

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

            # Si interactúan en un grupo, guardamos el JID del grupo como activo para notificaciones futuras
            if is_group and group_id:
                if db["config"]["grupo_activo"] != group_id:
                    db["config"]["grupo_activo"] = group_id
                    save_db(db)

            # 1. COMANDO: LISTA (Muestra estado de 1 al 100)
            if text_lower == "lista" or text_lower == "/lista":
                msg_lines = ["📋 *LISTA DE NÚMEROS DE LA RIFA (1-100)*\n"]
                for i in range(1, 101):
                    num_str = str(i)
                    info = db["numeros"].get(num_str, {"estado": "disponible"})
                    if info["estado"] == "ocupado":
                        comprador = info.get("comprador", "Ocupado")
                        msg_lines.append(f"❌ {num_str}: {comprador} (Ocupado)")
                    else:
                        msg_lines.append(f"✅ {num_str}: Disponible")
                
                full_text = "\n".join(msg_lines)
                
                # Enviar respuesta al lugar donde se solicitó (grupo o privado)
                target = group_id if is_group else sender_id
                send_whatsapp_message(target, full_text)

            # 2. COMANDO: COMPRAR / JUGAR (Números separados por coma)
            elif text_lower.startswith("jugar") or text_lower.startswith("comprar") or "," in text or text.isdigit():
                clean_text = text_lower.replace("jugar", "").replace("comprar", "").strip()
                parts = [p.strip() for p in clean_text.split(",") if p.strip().isdigit()]
                
                if not parts:
                    if not is_group:
                        send_whatsapp_message(sender_id, "⚠️ Formato no reconocido. Envía los números separados por coma (Ej: *5, 12, 25*).")
                    return jsonify({"status": "bad_format"}), 200

                ocupados_intentados = []
                exitosos = []

                for p in parts:
                    if p in db["numeros"]:
                        if db["numeros"][p]["estado"] == "disponible":
                            db["numeros"][p]["estado"] = "ocupado"
                            db["numeros"][p]["comprador"] = push_name
                            db["numeros"][p]["telefono"] = sender_id
                            exitosos.append(p)
                        else:
                            ocupados_intentados.append(p)

                save_db(db)

                # Construir mensaje de confirmación detallado
                respuesta = ""
                if exitosos:
                    respuesta += f"🎉 ¡Jugada registrada con éxito!\n👤 *Participante:* {push_name}\n🔢 *Números apartados:* *{', '.join(exitosos)}*\n"
                if ocupados_intentados:
                    respuesta += f"⚠️ Los siguientes números ya estaban ocupados: *{', '.join(ocupados_intentados)}*."

                if respuesta:
                    # NOTIFICACIÓN 1: Enviar al chat privado del usuario (si la interacción ocurrió en un grupo o privado)
                    send_whatsapp_message(sender_id, f"🎟️ *Confirmación de tu Jugada*\n\n{respuesta}")

                    # NOTIFICACIÓN 2: Enviar al grupo si la jugada se hizo en grupo
                    if is_group and group_id:
                        send_whatsapp_message(group_id, f"📢 *¡Nuevo movimiento en la rifa!*\n\n{respuesta}")

            # 3. COMANDO ADMINISTRATIVO OPCIONAL: /ganador <numero> (Notifica privado y grupo)
            elif text_lower.startswith("/ganador") or text_lower.startswith("ganador"):
                partes_g = text.split()
                if len(partes_g) > 1 and partes_g[1].isdigit():
                    num_ganador = partes_g[1]
                    info_num = db["numeros"].get(num_ganador, {})
                    
                    if info_num.get("estado") == "ocupado":
                        ganador_nombre = info_num.get("comprador", "Desconocido")
                        ganador_tel = info_num.get("telefono")
                        
                        msj_ganador = f"🏆🎉 ¡FELICIDADES *{ganador_nombre}*! El número ganador de la rifa es el *{num_ganador}*! 🎊🏆"
                        
                        # Notificar al grupo activo
                        activo_group = db["config"].get("grupo_activo")
                        if activo_group:
                            send_whatsapp_message(activo_group, msj_ganador)
                        
                        # Notificar por privado al ganador si tenemos su teléfono registrado
                        if ganador_tel:
                            send_whatsapp_message(ganador_tel, f"🏆 ¡Has ganado la rifa con el número *{num_ganador}*! Ponte en contacto con el administrador.")
                    else:
                        target = group_id if is_group else sender_id
                        send_whatsapp_message(target, f"⚠️ El número *{num_ganador}* no está ocupado o no existe.")
                else:
                    target = group_id if is_group else sender_id
                    send_whatsapp_message(target, "⚠️ Uso del comando ganador incorrecto. Ejemplo: *ganador 45*.")

            else:
                # Mensaje de ayuda si escribe otra cosa en privado
                if not is_group:
                    send_whatsapp_message(sender_id, 
                        "🤖 *Bot de Rifa Activo*\n\n"
                        "• Escribe *lista* para ver los números del 1 al 100.\n"
                        "• Envía los números separados por coma (ej: *5, 12, 20*) para jugar."
                    )

    except Exception as e:
        print(f"Error procesando el webhook: {e}")
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "success"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
