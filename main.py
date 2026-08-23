import os
import json
import uuid
import asyncio
import logging
from datetime import datetime
from aiohttp import web, ClientSession, ClientError

# ============================================
# CONFIGURACIÓN (TUS DATOS)
# ============================================
EVOLUTION_API_URL = "https://mi-whatsapp-api-pobo.onrender.com"
EVOLUTION_API_KEY = "55725d7c0b0fb17cb5e6564edac38c1f"
INSTANCE_NAME = "mi-bot"
ADMIN_PHONE_NUMBER = "5511948824359"
BOT_PHONE_NUMBER = "5562993984530"  # Opcional, para evitar auto-respuestas
WEBHOOK_PATH = "/webhook"
PORT = int(os.environ.get("PORT", 10000))

# Validación básica de configuración
if not all([EVOLUTION_API_URL, INSTANCE_NAME, ADMIN_PHONE_NUMBER]):
    print("❌ Error: Faltan variables de entorno. Asegúrate de definir EVOLUTION_API_URL, INSTANCE_NAME y ADMIN_PHONE_NUMBER.")
    exit(1)

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============================================
# PERSISTENCIA (JSON)
# ============================================
DB_FILE = "rifa_db.json"

def inicializar_rifa():
    try:
        if not os.path.exists(DB_FILE):
            data_inicial = {
                "estado_rifa": "activa",
                "numeros": {str(i): {"estado": "disponible", "nombre": "", "user_id": "", "username": ""} for i in range(1, 101)},
                "solicitudes_pendientes": {}
            }
            with open(DB_FILE, "w") as f:
                json.dump(data_inicial, f, indent=4)
    except Exception as e:
        logger.error(f"Error al inicializar JSON: {e}")

def borrar_y_recrear_base_datos():
    try:
        if os.path.exists(DB_FILE):
            os.remove(DB_FILE)
    except Exception as e:
        logger.error(f"Error al eliminar archivo: {e}")
    inicializar_rifa()

def obtener_data_completa():
    inicializar_rifa()
    try:
        with open(DB_FILE, "r") as f:
            data = json.load(f)
        # Asegurar campos necesarios
        if "estado_rifa" not in data:
            data["estado_rifa"] = "activa"
        if "solicitudes_pendientes" not in data:
            data["solicitudes_pendientes"] = {}
        return data
    except Exception as e:
        logger.error(f"Error al leer JSON: {e}")
        borrar_y_recrear_base_datos()
        with open(DB_FILE, "r") as f:
            return json.load(f)

def guardar_data_completa(data):
    try:
        with open(DB_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logger.error(f"Error al guardar JSON: {e}")

# ============================================
# LÓGICA DE NEGOCIO (precios, generación de lista, etc.)
# ============================================
VALOR_POR_NUMERO = 10

def calcular_premio_total():
    recaudacion_total = 100 * VALOR_POR_NUMERO
    premio = recaudacion_total * 0.55
    return int(premio) if premio.is_integer() else round(premio, 2)

def calcular_precio_total(cantidad, usuario_ya_tiene_compras=False):
    if cantidad <= 0:
        return 0
    if usuario_ya_tiene_compras:
        return cantidad * VALOR_POR_NUMERO

    # Promoción para primera jugada
    p5 = int(VALOR_POR_NUMERO * 4)
    p4 = int(VALOR_POR_NUMERO * 3.5)
    p3 = int(VALOR_POR_NUMERO * 2.5)
    p2 = int(VALOR_POR_NUMERO * 1.5)
    p1 = VALOR_POR_NUMERO

    if cantidad >= 5:
        return p5  # Si pide 5 o más, solo aplica el paquete de 5 (puede ajustarse)
    elif cantidad == 4:
        return p4
    elif cantidad == 3:
        return p3
    elif cantidad == 2:
        return p2
    else:
        return p1

def usuario_tiene_jugada_previa(user_id, data_completa):
    rifa = data_completa.get("numeros", {})
    solicitudes = data_completa.get("solicitudes_pendientes", {})
    for num_str, info in rifa.items():
        if info.get("user_id") == user_id and info.get("estado") in ["ocupado", "pendiente"]:
            return True
    for req_id, sol in solicitudes.items():
        if sol.get("user_id") == user_id:
            return True
    return False

def generar_texto_lista():
    data = obtener_data_completa()
    rifa = data["numeros"]
    texto = "📋 *LISTA OFICIAL DE LA RIFA (1 al 100)* 📋\n\n"
    disponibles = 0
    for i in range(1, 101):
        num_str = str(i).zfill(2)
        info = rifa[str(i)]
        estado = info.get("estado", "disponible")
        if estado == "disponible":
            texto += f"🔓 *{num_str}*: Disponible\n"
            disponibles += 1
        elif estado == "pendiente":
            texto += f"⏳ *{num_str}*: En verificación de pago...\n"
        else:
            nombre = info.get("nombre", "Usuario")
            user_id = info.get("user_id")
            if user_id:
                texto += f"🔒 *{num_str}*: Ocupado por [{nombre}](tel:{user_id})\n"
            else:
                texto += f"🔒 *{num_str}*: Ocupado por {nombre}\n"
    texto += f"\n📊 *Resumen:* Quedan {disponibles} números disponibles."
    estado_actual = data.get("estado_rifa")
    if estado_actual == "finalizada":
        texto += "\n\n🔒 *ESTADO:* Rifa cerrada/finalizada."
    elif estado_actual == "bloqueada":
        texto += "\n\n⛔ *ESTADO:* Rifa temporalmente bloqueada por el administrador."
    return texto

def obtener_texto_reglas():
    premio_actual = calcular_premio_total()
    return (
        "📜 *REGLAS Y DINÁMICA DEL GRUPO (Gran Sorteo 100):*\n\n"
        "1️⃣ *Respeto:* Mantén un ambiente de respeto absoluto hacia todos los miembros y administradores.\n"
        "2️⃣ *Números y Promoción:* Disponemos de 100 números (del 01 al 100).\n"
        f"✨ *Valores para tu primera jugada (Promoción):*\n"
        f"• 1 número = *{VALOR_POR_NUMERO} reales*\n"
        f"• 2 números = *{int(VALOR_POR_NUMERO * 1.5)} reales*\n"
        f"• 3 números = *{int(VALOR_POR_NUMERO * 2.5)} reales*\n"
        f"• 4 números = *{int(VALOR_POR_NUMERO * 3.5)} reales*\n"
        f"• 5 números = *{int(VALOR_POR_NUMERO * 4)} reales*\n"
        f"*(Si pides más de 5 números en tu primera jugada, los primeros 5 tienen precio promocional y a partir del 6to cada uno cuesta exactamente {VALOR_POR_NUMERO} reales).* \n\n"
        f"⚠️ *¡Atención a las jugadas adicionales!* La promoción aplica **únicamente para la primera jugada** de cada usuario. A partir de tu segunda jugada, **cada número tiene un costo fijo de {VALOR_POR_NUMERO} reales**.\n\n"
        "Envía la palabra `lista` para ver los disponibles y escribe los que deseas separados por coma (ej: *7, 14*) aquí o en el grupo.\n"
        "3️⃣ *Condición del Sorteo:* El sorteo se realizará **únicamente cuando los 100 números estén 100% ocupados y pagados**.\n"
        "4️⃣ *Garantía de Devolución:* Si algún participante adquiere sus números pero **no desea esperar**, puede solicitar la **devolución íntegra de su dinero** con el administrador.\n"
        f"5️⃣ *Entrega del Premio:* El usuario ganador recibirá un premio de *{premio_actual} reales* (vía PIX o en Cuba en CUP).\n"
        "6️⃣ *Transparencia:* El ganador se define utilizando los resultados oficiales de la *Lotería de Florida* (Pick 3) en el horario nocturno.\n\n"
        "🙏 *¡Ayúdanos a crecer!* Invita a otros usuarios al grupo."
    )

# ============================================
# FUNCIONES PARA ENVIAR MENSAJES A WHATSAPP (Evolution API)
# ============================================
async def send_whatsapp_message(chat_id, text):
    """
    Envía un mensaje de texto a través de Evolution API.
    chat_id: número de teléfono (grupo o individuo) sin '+' y sin espacios.
    text: texto a enviar.
    """
    url = f"{EVOLUTION_API_URL}/message/sendText/{INSTANCE_NAME}"
    headers = {
        "Content-Type": "application/json",
        "apikey": EVOLUTION_API_KEY
    }
    payload = {
        "number": chat_id,
        "text": text
    }
    try:
        async with ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    logger.error(f"Error al enviar mensaje a {chat_id}: {resp.status} - {await resp.text()}")
                else:
                    logger.info(f"Mensaje enviado a {chat_id}")
    except Exception as e:
        logger.error(f"Excepción enviando mensaje: {e}")

# ============================================
# MANEJADORES DE MENSAJES Y COMANDOS
# ============================================
async def handle_command(command, sender_phone, message_body, chat_id, context):
    """
    Procesa comandos que empiezan con '/'
    """
    # Comandos públicos
    if command == "/start":
        await send_whatsapp_message(chat_id, f"¡Hola! Estado actual de la Rifa:\n\n{generar_texto_lista()}")
        return

    if command == "/reglas":
        await send_whatsapp_message(chat_id, obtener_texto_reglas())
        return

    # Comandos de administrador (solo si el remitente es el admin)
    if sender_phone != ADMIN_PHONE_NUMBER:
        await send_whatsapp_message(chat_id, "⛔ No estás autorizado para este comando.")
        return

    # Comando para confirmar pago (admin)
    if command == "/confirmar":
        args = message_body.split()
        if len(args) < 2:
            await send_whatsapp_message(chat_id, "⚠️ Debes especificar el ID de la solicitud. Ejemplo: `/confirmar r123`")
            return
        req_id = args[1].strip()
        data_rifa = obtener_data_completa()
        solicitudes = data_rifa.get("solicitudes_pendientes", {})
        if req_id not in solicitudes:
            await send_whatsapp_message(chat_id, f"⚠️ La solicitud `{req_id}` no existe o ya fue procesada.")
            return
        sol = solicitudes[req_id]
        user_id = sol["user_id"]
        user_nums = sol["numeros"]
        user_nombre = sol["nombre"]
        chat_origen = sol["chat_origen"]
        nums_formatted = ", ".join([n.zfill(2) for n in user_nums])

        # Marcar números como ocupados
        rifa = data_rifa["numeros"]
        for n in user_nums:
            rifa[n]["estado"] = "ocupado"
            rifa[n]["nombre"] = user_nombre
            rifa[n]["user_id"] = user_id

        del solicitudes[req_id]
        data_rifa["numeros"] = rifa
        data_rifa["solicitudes_pendientes"] = solicitudes

        # Verificar si se completaron los 100 números
        if all(rifa[str(n)]["estado"] == "ocupado" for n in range(1, 101)):
            data_rifa["estado_rifa"] = "finalizada"
            aviso_cierre = (
                "🚨 *¡ATENCIÓN COMUNIDAD!* 🚨\n\n"
                "📋 ¡Se han ocupado todos los números de la lista!\n"
                "🔒 La lista ha sido **bloqueada automáticamente** y permanecerá cerrada hasta que se dé el resultado.\n\n"
                "🎰 El resultado será anunciado en el próximo tiro de la Florida. ¡Estén atentos! 🍀"
            )
            try:
                await send_whatsapp_message(chat_origen, aviso_cierre)
            except Exception as e:
                logger.error(f"Error enviando aviso de cierre: {e}")

        guardar_data_completa(data_rifa)

        # Mensaje de confirmación al admin
        await send_whatsapp_message(chat_id, f"✅ *Solicitud {req_id} APROBADA.* Números: {nums_formatted}")

        # Mensaje al usuario y al grupo
        mensaje_confirmacion = (
            f"🎉 *¡PAGO CONFIRMADO!* 🎉\n\n"
            f"👤 *Usuario:* {user_nombre}\n"
            f"📋 *Números asignados:* {nums_formatted}\n\n"
            "¡Muchas felicidades! 🙌"
        )
        try:
            await send_whatsapp_message(chat_origen, mensaje_confirmacion)
            await send_whatsapp_message(user_id, mensaje_confirmacion)
        except Exception as e:
            logger.error(f"Error enviando confirmación: {e}")
        return

    # Comando para rechazar pago (admin)
    if command == "/rechazar":
        args = message_body.split()
        if len(args) < 2:
            await send_whatsapp_message(chat_id, "⚠️ Debes especificar el ID de la solicitud. Ejemplo: `/rechazar r123`")
            return
        req_id = args[1].strip()
        data_rifa = obtener_data_completa()
        solicitudes = data_rifa.get("solicitudes_pendientes", {})
        if req_id not in solicitudes:
            await send_whatsapp_message(chat_id, f"⚠️ La solicitud `{req_id}` no existe o ya fue procesada.")
            return
        sol = solicitudes[req_id]
        user_id = sol["user_id"]
        user_nums = sol["numeros"]
        user_nombre = sol["nombre"]
        chat_origen = sol["chat_origen"]
        nums_formatted = ", ".join([n.zfill(2) for n in user_nums])

        # Liberar números (volver a disponible)
        rifa = data_rifa["numeros"]
        for n in user_nums:
            rifa[n] = {"estado": "disponible", "nombre": "", "user_id": "", "username": ""}

        del solicitudes[req_id]
        data_rifa["numeros"] = rifa
        data_rifa["solicitudes_pendientes"] = solicitudes
        guardar_data_completa(data_rifa)

        await send_whatsapp_message(chat_id, f"❌ *Solicitud {req_id} RECHAZADA.*")
        try:
            await send_whatsapp_message(user_id, f"❌ *SOLICITUD RECHAZADA* ❌\n\nHola {user_nombre}, lamentablemente tu pago para el/los número(s) *{nums_formatted}* fue rechazado y los números han sido liberados nuevamente.")
        except Exception as e:
            logger.error(f"Error enviando rechazo: {e}")
        return

    if command == "/reset":
        borrar_y_recrear_base_datos()
        await send_whatsapp_message(chat_id, f"🔄 *¡La rifa ha sido reseteada con éxito!*\n\n{generar_texto_lista()}")
        return

    if command == "/ganador":
        args = message_body.split()
        if len(args) < 2:
            await send_whatsapp_message(chat_id, "⚠️ Indica el número ganador. Ejemplo: `/ganador 14`")
            return
        num_ingresado = args[1].strip()
        if not num_ingresado.isdigit() or not (1 <= int(num_ingresado) <= 100):
            await send_whatsapp_message(chat_id, "⚠️ El número debe estar entre 1 y 100.")
            return
        num_str = str(int(num_ingresado))
        data_rifa = obtener_data_completa()
        info_num = data_rifa["numeros"].get(num_str, {})
        if info_num.get("estado") != "ocupado":
            await send_whatsapp_message(chat_id, f"⚠️ El número *{num_ingresado.zfill(2)}* no está ocupado.")
            return
        ganador_nombre = info_num.get("nombre")
        ganador_id = info_num.get("user_id")
        num_formateado = num_str.zfill(2)
        premio_actual = calcular_premio_total()

        # Cerrar la rifa
        data_rifa["estado_rifa"] = "finalizada"
        guardar_data_completa(data_rifa)

        # Mensaje de resultado en el chat
        await send_whatsapp_message(chat_id, f"🎰 *¡RESULTADO OFICIAL DE LA LOTERÍA!* 🎰\n\nEl número ganador de la Florida Pick 3 es el: *{num_formateado}*")
        await send_whatsapp_message(chat_id, f"🎉 *¡Felicidades al Ganador!* 🎉\n\nEl usuario {ganador_nombre} ha ganado con el número {num_formateado} un premio de {premio_actual} reales. ¡Muchas felicidades! 🥳\n\nPor favor, póngase en contacto con el administrador para recibir su premio. Una vez recibida la transferencia, envíe una captura de pantalla al grupo como evidencia.")
        # Notificar en privado al ganador
        if ganador_id:
            await send_whatsapp_message(ganador_id, f"🎉 *¡FELICIDADES {ganador_nombre}!* 🎉\n\nHas ganado el Gran Sorteo 100 con tu número *{num_formateado}* llevándote un premio de *{premio_actual} reales*! 🥳\n\nPor favor, ponte en contacto con el administrador para recibir tu premio. Una vez recibas la transferencia, envía una captura de pantalla al grupo como evidencia.")
        return

    if command == "/bloquear":
        data_rifa = obtener_data_completa()
        data_rifa["estado_rifa"] = "bloqueada"
        guardar_data_completa(data_rifa)
        await send_whatsapp_message(chat_id, "⛔ *La rifa ha sido bloqueada temporalmente.*")
        return

    if command == "/desbloquear":
        data_rifa = obtener_data_completa()
        if data_rifa.get("estado_rifa") == "finalizada":
            await send_whatsapp_message(chat_id, "⚠️ La rifa se encuentra finalizada. Usa `/reset` para reiniciar.")
            return
        data_rifa["estado_rifa"] = "activa"
        guardar_data_completa(data_rifa)
        await send_whatsapp_message(chat_id, f"🔓 *La rifa ha sido desbloqueada.*\n\n{generar_texto_lista()}")
        return

    if command == "/liberar":
        args = message_body.split()
        if len(args) < 2:
            await send_whatsapp_message(chat_id, "⚠️ Indica el nombre del usuario a liberar. Ejemplo: `/liberar Juan`")
            return
        nombre_buscar = " ".join(args[1:]).strip().lower()
        data_rifa = obtener_data_completa()
        rifa = data_rifa["numeros"]
        numeros_liberados = []
        for num_str, info in rifa.items():
            if info.get("estado") == "ocupado":
                nombre_usuario_reg = info.get("nombre", "").lower()
                if nombre_buscar in nombre_usuario_reg:
                    numeros_liberados.append(num_str.zfill(2))
                    rifa[num_str] = {"estado": "disponible", "nombre": "", "user_id": "", "username": ""}
        if not numeros_liberados:
            await send_whatsapp_message(chat_id, f"⚠️ No se encontraron números ocupados para: *{nombre_buscar}*.")
            return
        # Si estaba finalizada, cambiar a activa
        if data_rifa.get("estado_rifa") == "finalizada":
            data_rifa["estado_rifa"] = "activa"
        data_rifa["numeros"] = rifa
        guardar_data_completa(data_rifa)
        nums_str_lib = ", ".join(numeros_liberados)
        await send_whatsapp_message(chat_id, f"🔄 Números *{nums_str_lib}* liberados con éxito.")
        return

    # Si el comando no se reconoce
    await send_whatsapp_message(chat_id, "Comando no reconocido. Usa /start para ver la lista.")

async def handle_message(data):
    """
    Procesa un mensaje entrante (texto o evento de participantes)
    """
    try:
        # Extraer información común
        if "data" in data:
            # Formato típico de Evolution API
            event_data = data.get("data", {})
            message = event_data.get("message", {})
            sender = event_data.get("sender", {})
            chat = event_data.get("chat", {})
            sender_phone = sender.get("phone") or sender.get("id")  # puede variar
            chat_id = chat.get("id") or sender_phone  # para grupos, el id del chat
            message_text = message.get("text") or message.get("body") or ""
            message_type = event_data.get("type")  # "text", "participants", etc.
        else:
            # Estructura alternativa
            sender_phone = data.get("from") or data.get("phone")
            chat_id = data.get("chatId") or sender_phone
            message_text = data.get("body") or data.get("text") or ""
            message_type = data.get("type") or "text"

        # Si es un evento de participantes (nuevos miembros)
        if message_type == "participants" and chat_id:
            # Verificar si se agregó un nuevo participante
            participants = event_data.get("participants", []) if "event_data" in locals() else data.get("participants", [])
            if not participants:
                # Intentar obtener de otra forma
                participants = data.get("data", {}).get("participants", [])
            for p in participants:
                if p.get("action") == "add":
                    new_user = p.get("phone") or p.get("id")
                    if new_user and new_user != BOT_PHONE_NUMBER:
                        # Enviar bienvenida al grupo
                        await send_whatsapp_message(chat_id, f"🎉 *¡Bienvenido/a al Gran Sorteo 100!* 🎉\n\n{obtener_texto_reglas()}")
            return

        # Si no es mensaje de texto o es del bot, ignorar
        if message_type != "text" or sender_phone == BOT_PHONE_NUMBER:
            return

        # Limpiar mensaje
        message_text = message_text.strip()
        if not message_text:
            return

        # Comandos (empiezan con '/')
        if message_text.startswith("/"):
            parts = message_text.split()
            command = parts[0].lower()
            await handle_command(command, sender_phone, message_text, chat_id, None)
            return

        # Mensaje de texto normal: podría ser lista de números o palabra clave "lista"
        if message_text.lower() in ["hola", "buenas", "lista", "inicio", "rifa", "sorteo"]:
            await send_whatsapp_message(chat_id, f"¡Hola! Estado actual de la Rifa:\n\n{generar_texto_lista()}")
            return

        # Intentar parsear como lista de números separados por coma
        partes = [p.strip() for p in message_text.split(",")]
        es_lista_numeros = all(p.isdigit() for p in partes) if partes else False

        if es_lista_numeros:
            data_rifa = obtener_data_completa()
            estado_actual_rifa = data_rifa.get("estado_rifa", "activa")
            if estado_actual_rifa in ["finalizada", "bloqueada"]:
                await send_whatsapp_message(chat_id, "⛔ Lo sentimos, la lista se encuentra cerrada o bloqueada en este momento.")
                return

            rifa = data_rifa["numeros"]
            solicitudes = data_rifa.get("solicitudes_pendientes", {})
            ocupados, pendientes, validos_para_reservar, invalidos = [], [], [], []

            for p in partes:
                num_elegido = int(p)
                if 1 <= num_elegido <= 100:
                    num_str = str(num_elegido)
                    est = rifa[num_str].get("estado", "disponible")
                    if est == "ocupado":
                        ocupados.append(f"*{num_str.zfill(2)}*")
                    elif est == "pendiente":
                        pendientes.append(f"*{num_str.zfill(2)}*")
                    else:
                        validos_para_reservar.append(num_str)
                else:
                    invalidos.append(p)

            # Mostrar conflictos si los hay
            mensajes_conflicto = []
            if ocupados:
                mensajes_conflicto.append(f"🔒 El/los número(s) {', '.join(ocupados)} ya está(n) *OCUPADO(S)*.")
            if pendientes:
                mensajes_conflicto.append(f"⏳ El/los número(s) {', '.join(pendientes)} está(n) *EN PROCESO DE VERIFICACIÓN*.")
            if invalidos:
                mensajes_conflicto.append(f"⚠️ El/los número(s) {', '.join(invalidos)} está(n) fuera del rango (1 al 100).")

            if mensajes_conflicto and not validos_para_reservar:
                await send_whatsapp_message(chat_id, f"Hola:\n" + "\n".join(mensajes_conflicto))
                return

            if validos_para_reservar:
                ya_tiene_compras = usuario_tiene_jugada_previa(sender_phone, data_rifa)
                req_id = "r" + str(uuid.uuid4().int)[:4]

                # Marcar números como pendientes
                for n in validos_para_reservar:
                    rifa[n]["estado"] = "pendiente"

                solicitudes[req_id] = {
                    "nombre": sender_phone,  # Usamos el número como nombre, ya que WhatsApp no tiene nombre de usuario
                    "user_id": sender_phone,
                    "username": "",
                    "numeros": validos_para_reservar,
                    "chat_origen": chat_id
                }

                data_rifa["numeros"] = rifa
                data_rifa["solicitudes_pendientes"] = solicitudes
                guardar_data_completa(data_rifa)

                nums_solicitados_txt = ", ".join([n.zfill(2) for n in validos_para_reservar])
                cantidad_numeros = len(validos_para_reservar)
                total_a_pagar = calcular_precio_total(cantidad_numeros, usuario_ya_tiene_compras=ya_tiene_compras)

                aviso_promocion = f"\n⚠️ *Aviso importante:* Como ya tienes una jugada previa registrada, esta nueva jugada de {cantidad_numeros} número(s) **no aplica para la promoción** y se cobra a precio estándar (*{VALOR_POR_NUMERO} reales cada número*).\n" if ya_tiene_compras else f"\n✨ *¡Primera jugada detectada!* Aplica la tarifa promocional para tus {cantidad_numeros} número(s).\n"

                # Respuesta al usuario
                mensaje_usuario = (
                    f"⏳ *SOLICITUD EN PROCESO* ⏳\n\n"
                    f"Hola, tus números (*{nums_solicitados_txt}*) están reservados temporalmente.\n"
                    f"{aviso_promocion}"
                    f"💰 Cantidad: *{cantidad_numeros}*\n"
                    f"💵 Total a transferir: *{total_a_pagar} reales*\n\n"
                    f"Contacta al administrador para pagar."
                )
                await send_whatsapp_message(chat_id, mensaje_usuario)

                # Enviar solicitud al administrador (en privado)
                mensaje_admin = (
                    f"📩 *NUEVA SOLICITUD* (ID: `{req_id}`)\n\n"
                    f"👤 *Cliente:* {sender_phone} {'*(Jugada Posterior - Precio Normal)*' if ya_tiene_compras else '*(1era Jugada - Promoción)*'}\n"
                    f"📋 *Números:* *{nums_solicitados_txt}*\n"
                    f"💰 *Total:* *{total_a_pagar} reales* ({cantidad_numeros} núm.)\n\n"
                    f"Responde con `/confirmar {req_id}` o `/rechazar {req_id}`"
                )
                await send_whatsapp_message(ADMIN_PHONE_NUMBER, mensaje_admin)

        else:
            # Mensaje no reconocido
            await send_whatsapp_message(chat_id, "No entendí tu mensaje. Envía números separados por coma (ej: 7, 14) o usa /start para ver la lista.")

    except Exception as e:
        logger.error(f"Error procesando mensaje: {e}")
        # Intentar notificar al admin
        await send_whatsapp_message(ADMIN_PHONE_NUMBER, f"⚠️ Error en el bot: {e}")

# ============================================
# SERVIDOR WEB (aiohttp)
# ============================================
async def handle_webhook(request):
    try:
        data = await request.json()
        logger.info(f"Webhook recibido: {data}")
        # Procesar el mensaje en segundo plano para no bloquear la respuesta
        asyncio.create_task(handle_message(data))
        return web.Response(text="OK", status=200)
    except Exception as e:
        logger.error(f"Error en webhook: {e}")
        return web.Response(text="Error", status=500)

async def handle_health(request):
    return web.Response(text="Bot de Rifa WhatsApp Activo 24/7!")

async def start_web_server():
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, handle_webhook)
    app.router.add_get("/", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"🚀 Servidor web corriendo en el puerto {PORT}")

# ============================================
# MAIN
# ============================================
async def main():
    inicializar_rifa()
    await start_web_server()
    # Mantener el proceso vivo
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot detenido correctamente.")
