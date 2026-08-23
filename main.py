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
ADMIN_PHONE = os.getenv("ADMIN_PHONE", "5511948824359")

def load_db():
    if not os.path.exists(DB_FILE):
        db_initial = {
            "numeros": {str(i): {"estado": "disponible", "comprador": None, "telefono": None} for i in range(1, 101)},
            "pendientes": {},
            "config": {"grupo_activo": None}
        }
        save_db(db_initial)
        return db_initial
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "numeros" not in data:
                data["numeros"] = {str(i): {"estado": "disponible", "comprador": None, "telefono": None} for i in range(1, 101)}
            if "pendientes" not in data:
                data["pendientes"] = {}
            if "config" not in data:
                data["config"] = {"grupo_activo": None}
            return data
    except Exception:
        return {
            "numeros": {str(i): {"estado": "disponible", "comprador": None, "telefono": None} for i in range(1, 101)},
            "pendientes": {},
            "config": {"grupo_activo": None}
        }

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def send_whatsapp_message(recipient_id, text):
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
    return "Bot de Rifa Activo y Sincronizado.", 200

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
            participant_jid = message_data.get("key", {}).get("participant", "")
            
            is_group = remote_jid.endswith("@g.us")
            
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

            if is_group and group_id:
                if db["config"]["grupo_activo"] != group_id:
                    db["config"]["grupo_activo"] = group_id
                    save_db(db)

            # 1. COMANDO: LISTA
            if text_lower == "lista" or text_lower == "/lista":
                msg_lines = ["📋 *LISTA DE NÚMEROS DE LA RIFA (1-100)*\n"]
                for i in range(1, 101):
                    num_str = str(i)
                    info = db["numeros"].get(num_str, {"estado": "disponible"})
                    estado = info["estado"]
                    if estado == "ocupado":
                        comprador = info.get("comprador", "Ocupado")
                        msg_lines.append(f"❌ {num_str}: {comprador} (Pagado)")
                    elif estado == "pendiente":
                        comprador = info.get("comprador", "Reservado")
                        msg_lines.append(f"⏳ {num_str}: {comprador} (En espera de pago)")
                    else:
                        msg_lines.append(f"✅ {num_str}: Disponible")
                
                full_text = "\n".join(msg_lines)
                target = group_id if is_group else sender_id
                send_whatsapp_message(target, full_text)

            # 2. COMANDO: COMPRAR / JUGAR (Validación rigurosa de disponibilidad)
            elif text_lower.startswith("jugar") or text_lower.startswith("comprar") or "," in text or text.isdigit():
                clean_text = text_lower.replace("jugar", "").replace("comprar", "").strip()
                parts = [p.strip() for p in clean_text.split(",") if p.strip().isdigit()]
                
                if not parts:
                    if not is_group:
                        send_whatsapp_message(sender_id, "⚠️ Formato incorrecto. Envía los números separados por coma (Ej: *5, 12, 25*).")
                    return jsonify({"status": "bad_format"}), 200

                no_disponibles = []
                solicitados = []

                # Verificar uno por uno si están libres
                for p in parts:
                    if p in db["numeros"]:
                        estado_actual = db["numeros"][p]["estado"]
                        if estado_actual == "disponible":
                            solicitados.append(p)
                        else:
                            no_disponibles.append(p)
                    else:
                        no_disponibles.append(p)

                # Si alguno de los números pedidos ya está ocupado o pendiente, rechazar la jugada completa
                if no_disponibles or not solicitados:
                    respuesta = f"⚠️ Los siguientes números no están disponibles: *{', '.join(no_disponibles)}*. Por favor elige otros."
                    target = group_id if is_group else sender_id
                    send_whatsapp_message(target, respuesta)
                    return jsonify({"status": "unavailable"}), 200

                # Marcar estrictamente como 'pendiente' (bloqueados temporalmente, NO ocupados)
                for p in solicitados:
                    db["numeros"][p]["estado"] = "pendiente"
                    db["numeros"][p]["comprador"] = push_name
                    db["numeros"][p]["telefono"] = sender_id

                import time
                req_id = str(int(time.time()))[-6:]
                db["pendientes"][req_id] = {
                    "telefono": sender_id,
                    "nombre": push_name,
                    "numeros": solicitados
                }
                save_db(db)

                # Notificar al usuario que su jugada está en espera de revisión del admin
                msj_usuario = (
                    f"⏳ *¡Jugada en Proceso de Espera!*\n\n"
                    f"👤 *Participante:* {push_name}\n"
                    f"🔢 *Números solicitados:* *{', '.join(solicitados)}*\n\n"
                    f"💳 Envía tu comprobante de transferencia al administrador. Tus números están bloqueados temporalmente hasta que se confirme tu pago."
                )
                send_whatsapp_message(sender_id, msj_usuario)

                # Notificar al grupo
                if is_group and group_id:
                    send_whatsapp_message(group_id, 
                        f"⏳ *¡Nueva jugada pendiente!*\n"
                        f"👤 *{push_name}* ha solicitado los números: *{', '.join(solicitados)}*. "
                        f"En espera de verificación de pago."
                    )

                # Enviar alerta directo al teléfono del administrador (5511948824359)
                if ADMIN_PHONE:
                    send_whatsapp_message(ADMIN_PHONE, 
                        f"🔔 *SOLICITUD DE PAGO PENDIENTE (ID: {req_id})*\n\n"
                        f"👤 Usuario: {push_name} ({sender_id})\n"
                        f"🔢 Números: {', '.join(solicitados)}\n\n"
                        f"👉 Para aprobar: `/aprobar {req_id}`\n"
                        f"👉 Para rechazar: `/rechazar {req_id}`"
                    )

            # 3. COMANDOS DE ADMINISTRADOR (/aprobar o /rechazar)
            elif text_lower.startswith("/aprobar") or text_lower.startswith("/rechazar"):
                partes_admin = text.split()
                if len(partes_admin) == 2:
                    accion = partes_admin[0].replace("/", "")
                    req_id = partes_admin[1]

                    if req_id in db["pendientes"]:
                        datos_reserva = db["pendientes"][req_id]
                        u_tel = datos_reserva["telefono"]
                        u_nombre = datos_reserva["nombre"]
                        u_nums = datos_reserva["numeros"]

                        if accion == "aprobar":
                            # Pasan formalmente a 'ocupado'
                            for p in u_nums:
                                if db["numeros"][p]["estado"] == "pendiente":
                                    db["numeros"][p]["estado"] = "ocupado"
                            
                            del db["pendientes"][req_id]
                            save_db(db)

                            # Mensaje privado al usuario confirmando sus números
                            send_whatsapp_message(u_tel, f"🎉 ¡Pago verificado y confirmado! Tus números *{', '.join(u_nums)}* ya son oficialmente tuyos.")
                            
                            # Notificación al grupo
                            activo_group = db["config"].get("grupo_activo")
                            if activo_group:
                                send_whatsapp_message(activo_group, f"✅ *¡Jugada Aprobada!* El administrador confirmó el pago de *{u_nombre}* para los números: *{', '.join(u_nums)}*.")

                            send_whatsapp_message(sender_id, f"👍 Solicitud {req_id} aprobada con éxito.")

                        elif accion == "rechazar":
                            # Se liberan los números de regreso a 'disponible'
                            for p in u_nums:
                                if db["numeros"][p]["estado"] == "pendiente":
                                    db["numeros"][p]["estado"] = "disponible"
                                    db["numeros"][p]["comprador"] = None
                                    db["numeros"][p]["telefono"] = None

                            del db["pendientes"][req_id]
                            save_db(db)

                            # Notificar al usuario que fue rechazada/liberada
                            send_whatsapp_message(u_tel, f"❌ Tu solicitud con los números *{', '.join(u_nums)}* fue rechazada o no se confirmó el pago. Los números han sido liberados.")
                            send_whatsapp_message(sender_id, f"🗑️ Solicitud {req_id} rechazada y números liberados.")
                    else:
                        send_whatsapp_message(sender_id, f"⚠️ No existe ninguna solicitud pendiente con el ID: {req_id}.")
                else:
                    send_whatsapp_message(sender_id, "⚠️ Uso incorrecto. Ejemplo: */aprobar 123456*")

            # 4. COMANDO DE GANADOR
            elif text_lower.startswith("/ganador") or text_lower.startswith("ganador"):
                partes_g = text.split()
                if len(partes_g) > 1 and partes_g[1].isdigit():
                    num_ganador = partes_g[1]
                    info_num = db["numeros"].get(num_ganador, {})
                    
                    if info_num.get("estado") == "ocupado":
                        ganador_nombre = info_num.get("comprador", "Desconocido")
                        ganador_tel = info_num.get("telefono")
                        
                        msj_ganador = f"🏆🎉 ¡FELICIDADES *{ganador_nombre}*! El número ganador de la rifa es el *{num_ganador}*! 🎊🏆"
                        
                        activo_group = db["config"].get("grupo_activo")
                        if activo_group:
                            send_whatsapp_message(activo_group, msj_ganador)
                        
                        if ganador_tel:
                            send_whatsapp_message(ganador_tel, f"🏆 ¡Has ganado la rifa con el número *{num_ganador}*!")
                    else:
                        target = group_id if is_group else sender_id
                        send_whatsapp_message(target, f"⚠️ El número *{num_ganador}* no está pagado o asignado.")

    except Exception as e:
        print(f"Error procesando el webhook: {e}")
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "success"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
