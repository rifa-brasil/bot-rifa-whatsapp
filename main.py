import os
import json
import uuid
import fcntl
import logging
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(name)

# ========== CONFIGURACIÓN ==========
DATA_FILE = "data.json"
GRUPO_CHAT_ID = os.environ.get("GRUPO_CHAT_ID_RESPALDO")      # ID del grupo de la rifa
ADMIN_CHAT_ID = os.environ.get("WHATSAPP_ADMIN_CHAT_ID")      # Administrador Brasil (quien confirma)
BOT_PHONE = os.environ.get("BOT_ASISTENTE_PHONE")             # Número del bot (sin '+')

logging.basicConfig(level=logging.INFO)

# ========== PERSISTENCIA ATÓMICA ==========
def cargar_data():
    """Carga los datos del archivo JSON con bloqueo de lectura."""
    try:
        with open(DATA_FILE, 'r') as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            data = json.load(f)
            fcntl.flock(f, fcntl.LOCK_UN)
            return data
    except FileNotFoundError:
        data = {"numeros": {}, "solicitudes_pendientes": {}}
        guardar_data_completa(data)
        return data

def guardar_data_completa(data):
    """Guarda los datos con bloqueo exclusivo (atómico)."""
    with open(DATA_FILE, 'w') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
        fcntl.flock(f, fcntl.LOCK_UN)

# ========== FUNCIONES AUXILIARES ==========
def generar_id_solicitud():
    """Genera un ID único de 8 caracteres hexadecimales."""
    return "r" + uuid.uuid4().hex[:8]

def normalizar_telefono(numero):
    """Elimina caracteres no numéricos (para usar en enlaces)."""
    return ''.join(filter(str.isdigit, numero))

def formatear_numeros(numeros):
    """Convierte lista de enteros a string con dos dígitos."""
    return ", ".join(str(n).zfill(2) for n in numeros)

def enviar_mensaje_whapi(chat_id, texto, mencion=None):
    """
    Envía un mensaje por WHAPI.
    Si se proporciona 'mencion' (teléfono), se añade una mención.
    (Adaptar según la API real de WHAPI)
    """
    # Aquí iría tu implementación real con requests.post()
    # Ejemplo:
    # payload = {"chatId": chat_id, "text": texto, "mentions": [mencion] if mencion else []}
    # requests.post("https://api.whapi.com/messages", json=payload)
    logging.info(f"Mensaje a {chat_id}: {texto}")
    if mencion:
        logging.info(f"Con mención a: {mencion}")
    # return True

# ========== COMANDOS DEL BOT ==========
def manejar_lista(chat_id):
    """Envía la lista de números con estados (ocupado, pendiente, disponible)."""
    data = cargar_data()
    numeros = data.get("numeros", {})
    mensaje = "🎟 *LISTA DE NÚMEROS DISPONIBLES* 🎟\n\n"
    for i in range(1, 101):
        estado = numeros.get(str(i), {}).get("estado", "disponible")
        if estado == "ocupado":
            simbolo = "🔴"
        elif estado == "pendiente":
            simbolo = "🟡"
        else:
            simbolo = "🟢"
        mensaje += f"{simbolo} {str(i).zfill(2)}  "
        if i % 10 == 0:
            mensaje += "\n"
    mensaje += "\n\n🔴 Ocupado | 🟡 Pendiente | 🟢 Disponible"
    enviar_mensaje_whapi(chat_id, mensaje)

def manejar_reserva(chat_id, numero_persona, nombre_usuario, texto):
    """Procesa la solicitud de reserva de números."""
    # Extraer números del mensaje (separados por espacios o comas)
    try:
        numeros_solicitados = []
        for token in texto.replace(',', ' ').split():
            try:
                num = int(token)
                if 1 <= num <= 100:
                    numeros_solicitados.append(num)
            except ValueError:
                pass
        if not numeros_solicitados:
            enviar_mensaje_whapi(chat_id, "❌ Por favor, envía números válidos del 1 al 100 separados por espacios o comas.")
            return
    except Exception as e:
        logging.error(f"Error al parsear números: {e}")
        enviar_mensaje_whapi(chat_id, "❌ Formato incorrecto. Envía números del 1 al 100 separados por espacios.")
        return
        # Cargar datos actuales
    data = cargar_data()
    rifa = data.get("numeros", {})
    ocupados = []
    pendientes = []
    invalidos = []
    validos = []

    for n in numeros_solicitados:
        estado = rifa.get(str(n), {}).get("estado", "disponible")
        if estado == "ocupado":
            ocupados.append(n)
        elif estado == "pendiente":
            pendientes.append(n)
        elif n < 1 or n > 100:
            invalidos.append(n)
        else:
            validos.append(n)

    # Mensajes de conflicto
    mensajes_conflicto = []
    if ocupados:
        mensajes_conflicto.append(f"🔴 El/los número(s) {formatear_numeros(ocupados)} ya está(n) *OCUPADO(S)*.")
    if pendientes:
        mensajes_conflicto.append(f"🟡 El/los número(s) {formatear_numeros(pendientes)} está(n) *EN PROCESO DE VERIFICACIÓN* por otro participante.")
    if invalidos:
        mensajes_conflicto.append(f"⚠️ El/los número(s) {formatear_numeros(invalidos)} está(n) fuera del rango (1 al 100).")

    # Si no hay números válidos, informar y terminar
    if mensajes_conflicto and not validos:
        respuesta = f"Hola {nombre_usuario}:\n" + "\n".join(mensajes_conflicto)
        enviar_mensaje_whapi(chat_id, respuesta)
        return

    # Si hay números válidos, proceder con la reserva temporal
    if validos:
        req_id = generar_id_solicitud()
        telefono_limpio = normalizar_telefono(numero_persona)

        # Marcar números como pendientes
        for n in validos:
            rifa[str(n)] = {
                "estado": "pendiente",
                "solicitud_id": req_id,
                "usuario": nombre_usuario,
                "telefono": telefono_limpio
            }

        # Guardar la solicitud en el diccionario de pendientes
        solicitudes = data.get("solicitudes_pendientes", {})
        solicitudes[req_id] = {
            "nombre": nombre_usuario,
            "telefono": telefono_limpio,
            "numeros": validos,
            "grupo_id": chat_id if "@g.us" in chat_id else GRUPO_CHAT_ID,
            "fecha": str(datetime.now())
        }
        data["numeros"] = rifa
        data["solicitudes_pendientes"] = solicitudes
        guardar_data_completa(data)

        # Notificar al usuario (en el mismo chat) que está en proceso
        nums_txt = formatear_numeros(validos)
        msg_usuario = (
            f"⏳ *SOLICITUD RECIBIDA* ⏳\n\n"
            f"Hola {nombre_usuario}, recibimos tu pedido para el/los número(s): *{nums_txt}*.\n\n"
            f"🟡 Quedan *reservados temporalmente* mientras el administrador verifica tu transferencia.\n"
            f"Te notificaremos tan pronto se confirme o rechace."
        )
        if mensajes_conflicto:
            msg_usuario += "\n\n📌 *Nota:* " + " ".join(mensajes_conflicto)
        enviar_mensaje_whapi(chat_id, msg_usuario)

        # Enviar mensaje al administrador (Brasil) con enlaces de confirmación/rechazo
        link_confirmar = f"wa.me/{BOT_PHONE}?text=confirmar%20{req_id}"
        link_rechazar = f"wa.me/{BOT_PHONE}?text=rechazar%20{req_id}"

        txt_admin = (
            f"📥 *NUEVA SOLICITUD DE COMPRA* (ID: {req_id})\n\n"
            f"👤 *Cliente:* {nombre_usuario}\n"
            f"📱 *Teléfono:* wa.me/{telefono_limpio}\n"
            f"🎟 *Números:* *{nums_txt}*\n\n"
            f"-----------------------------------\n"
            f"Toca una opción para responder:\n\n"
            f"🟢 *[ CONFIRMAR PAGO ]*\n{link_confirmar}\n\n"
            f"🔴 *[ RECHAZAR PAGO ]*\n{link_rechazar}"
        )
        enviar_mensaje_whapi(ADMIN_CHAT_ID, txt_admin)

def manejar_confirmar(chat_id, req_id):
    """Confirma una solicitud: marca números como ocupados y notifica."""
    data = cargar_data()
    solicitudes = data.get("solicitudes_pendientes", {})
    if req_id not in solicitudes:
        enviar_mensaje_whapi(chat_id, f"❌ Solicitud {req_id} no encontrada o ya fue procesada.")
        return
        solicitud = solicitudes[req_id]
    numeros = solicitud["numeros"]
    nombre_usuario = solicitud["nombre"]
    telefono_usuario = solicitud["telefono"]  # sin '+'
    grupo_id = solicitud["grupo_id"]

    # Marcar números como ocupados en la rifa
    rifa = data.get("numeros", {})
    for n in numeros:
        if str(n) in rifa:
            rifa[str(n)]["estado"] = "ocupado"
            # Opcional: limpiar solicitud_id para no dejar rastro
            rifa[str(n)].pop("solicitud_id", None)

    # Eliminar la solicitud pendiente
    del solicitudes[req_id]
    data["numeros"] = rifa
    data["solicitudes_pendientes"] = solicitudes
    guardar_data_completa(data)

    # ---- 1) Mensaje al GRUPO (solo confirmación, con mención) ----
    nums_txt = formatear_numeros(numeros)
    # Intentamos mencionar usando @ y el número de teléfono (sin '+').
    # En WhatsApp, para mencionar, la API suele requerir el ID del contacto o el número con @c.us.
    # Aquí usamos el formato común: @<número> (la API lo convertirá).
    mensaje_grupo = (
        f"✅ *¡JUGADA CONFIRMADA!* ✅\n\n"
        f"👤 @{telefono_usuario} ({nombre_usuario}) ha confirmado su participación.\n"
        f"🎟 Números: *{nums_txt}*\n\n"
        f"🔴 Ahora están marcados como *OCUPADOS*. ¡Suerte!"
    )
    # Enviar al grupo (puedes pasar el teléfono como mención si la API lo soporta)
    enviar_mensaje_whapi(grupo_id, mensaje_grupo, mencion=telefono_usuario)

    # ---- 2) Mensaje PRIVADO al usuario ----
    # Para enviar un mensaje privado, necesitamos el chat_id del usuario (su número con @c.us o similar).
    # Asumimos que el número de teléfono es suficiente si la API permite enviar a un número.
    chat_privado = telefono_usuario + "@c.us"  # Formato típico de WhatsApp
    mensaje_privado = (
        f"🎉 *¡Tu jugada ha sido CONFIRMADA!* 🎉\n\n"
        f"Hola {nombre_usuario}, el administrador ha verificado tu pago.\n"
        f"Tus números: *{nums_txt}* ahora están *OFICIALMENTE OCUPADOS*.\n\n"
        f"🔴 Quedan registrados a tu nombre. ¡Mucha suerte!"
    )
    enviar_mensaje_whapi(chat_privado, mensaje_privado)

    # Opcional: confirmar al administrador que se realizó
    enviar_mensaje_whapi(chat_id, f"✅ Solicitud {req_id} confirmada exitosamente.")

def manejar_rechazar(chat_id, req_id):
    """Rechaza una solicitud: libera los números y notifica."""
    data = cargar_data()
    solicitudes = data.get("solicitudes_pendientes", {})
    if req_id not in solicitudes:
        enviar_mensaje_whapi(chat_id, f"❌ Solicitud {req_id} no encontrada o ya fue procesada.")
        return

    solicitud = solicitudes[req_id]
    numeros = solicitud["numeros"]
    nombre_usuario = solicitud["nombre"]
    telefono_usuario = solicitud["telefono"]
    grupo_id = solicitud["grupo_id"]

    # Liberar números (eliminar estado pendiente)
    rifa = data.get("numeros", {})
    for n in numeros:
        if str(n) in rifa and rifa[str(n)].get("estado") == "pendiente":
            # Volver a disponible
            rifa[str(n)] = {"estado": "disponible"}  # o eliminar la entrada
            # Si quieres eliminar completamente: del rifa[str(n)]

    # Eliminar la solicitud
    del solicitudes[req_id]
    data["numeros"] = rifa
    data["solicitudes_pendientes"] = solicitudes
    guardar_data_completa(data)

    # Notificar al grupo (opcional)
    nums_txt = formatear_numeros(numeros)
    mensaje_grupo = (
        f"❌ *JUGADA RECHAZADA* ❌\n\n"
        f"La solicitud de {nombre_usuario} para los números *{nums_txt}* ha sido rechazada.\n"
        f"Los números quedan disponibles nuevamente."
    )
    enviar_mensaje_whapi(grupo_id, mensaje_grupo)

    # Notificar al usuario por privado
    chat_privado = telefono_usuario + "@c.us"
    mensaje_privado = (
        f"❌ *Tu solicitud ha sido RECHAZADA* ❌\n\n"
    f"Hola {nombre_usuario}, el administrador no pudo verificar tu pago.\n"
        f"Tus números *{nums_txt}* han sido liberados y están disponibles para otros.\n"
        f"Si crees que es un error, contacta al administrador."
    )
    enviar_mensaje_whapi(chat_privado, mensaje_privado)

    enviar_mensaje_whapi(chat_id, f"❌ Solicitud {req_id} rechazada.")

# ========== WEBHOOK PRINCIPAL ==========
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data_in = request.get_json()
        if not data_in:
            return jsonify({"status": "error", "message": "No data"}), 400

        # Extraer información del mensaje (adaptar según WHAPI)
        # Suponemos que el payload contiene: chatId, from, body, etc.
        chat_id = data_in.get("chatId")
        from_number = data_in.get("from")  # número del remitente
        body = data_in.get("body", "").strip()
        sender_name = data_in.get("pushName", "Usuario")  # nombre del contacto

        if not chat_id or not body:
            return jsonify({"status": "ok"}), 200

        # Comandos
        if body.lower() == "lista":
            manejar_lista(chat_id)

        elif body.lower().startswith("confirmar "):
            partes = body.split()
            if len(partes) == 2:
                req_id = partes[1]
                manejar_confirmar(chat_id, req_id)
            else:
                enviar_mensaje_whapi(chat_id, "❌ Formato incorrecto. Usa: confirmar <ID>")

        elif body.lower().startswith("rechazar "):
            partes = body.split()
            if len(partes) == 2:
                req_id = partes[1]
                manejar_rechazar(chat_id, req_id)
            else:
                enviar_mensaje_whapi(chat_id, "❌ Formato incorrecto. Usa: rechazar <ID>")

        else:
            # Si no es un comando, asumimos que es una solicitud de números
            # Solo procesamos si el mensaje contiene números
            if any(c.isdigit() for c in body):
                manejar_reserva(chat_id, from_number, sender_name, body)
            else:
                # Mensaje no reconocido (opcional)
                enviar_mensaje_whapi(chat_id, "❌ No te entiendo. Envía 'lista' para ver disponibles o números para reservar.")

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        logging.error(f"Error en webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ========== INICIO ==========
if name == "main":
    # Asegurar que existe el archivo de datos
    cargar_data()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
    
