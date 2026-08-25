import os
import json
import uuid
import asyncio
import logging
from aiohttp import web, ClientSession

# ============================================
# CONFIGURACIÓN (TUS DATOS OFICIALES)
# ============================================
EVOLUTION_API_URL = "https://mi-whatsapp-api-pobo.onrender.com"
EVOLUTION_API_KEY = "55725d7c0b0fb17cb5e6564edac38c1f"
INSTANCE_NAME = "mi-bot"
ADMIN_PHONE_NUMBER = "5511948824359"
BOT_PHONE_NUMBER = "5562993984530"
WEBHOOK_PATH = "/webhook"
PORT = int(os.environ.get("PORT", 10000))

# Validación básica de configuración
if not all([EVOLUTION_API_URL, INSTANCE_NAME, ADMIN_PHONE_NUMBER]):
    print("❌ Error: Faltan variables de entorno.")
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
            with open(DB_FILE, "w", encoding="utf-8") as f:
                json.dump(data_inicial, f, indent=4, ensure_ascii=False)
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
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "estado_rifa" not in data:
            data["estado_rifa"] = "activa"
        if "solicitudes_pendientes" not in data:
            data["solicitudes_pendientes"] = {}
        return data
    except Exception as e:
        logger.error(f"Error al leer JSON: {e}")
        borrar_y_recrear_base_datos()
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

def guardar_data_completa(data):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error al guardar JSON: {e}")

# ============================================
# LÓGICA DE NEGOCIO
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

    p5 = int(VALOR_POR_NUMERO * 4)
    p4 = int(VALOR_POR_NUMERO * 3.5)
    p3 = int(VALOR_POR_NUMERO * 2.5)
    p2 = int(VALOR_POR_NUMERO * 1.5)
    p1 = VALOR_POR_NUMERO

    if cantidad >= 5:
        return p5
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
        "1️⃣ *Respeto:* Mantén un ambiente de respeto absoluto.\n"
        "2️⃣ *Números y Promoción:* Disponemos de 100 números (del 01 al 100).\n"
        f"✨ *Valores para tu primera jugada (Promoción):*\n"
        f"• 1 número = *{VALOR_POR_NUMERO} reales*\n"
        f"• 2 números = *{int(VALOR_POR_NUMERO * 1.5)} reales*\n"
        f"• 3 números = *{int(VALOR_POR_NUMERO * 2.5)} reales*\n"
        f"• 4 números = *{int(VALOR_POR_NUMERO * 3.5)} reales*\n"
        f"• 5 números = *{int(VALOR_POR_NUMERO * 4)} reales*\n\n"
        f"Envía la palabra `lista` para ver los disponibles y escribe los que deseas separados por coma (ej: *7, 14*).\n"
        f"3️⃣ *Premio:* El usuario ganador recibirá un premio de *{premio_actual} reales*.\n"
        "4️⃣ *Transparencia:* Definido con la Lotería de Florida (Pick 3)."
    )

# ============================================
# ENVÍO DE MENSAJES (Evolution API)
# ============================================
async def send_whatsapp_message(chat_id, text):
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
                    logger.info(f"Mensaje enviado con éxito a {chat_id}")
    except Exception as e:
        logger.error(f"Excepción enviando mensaje: {e}")

# ============================================
# MANEJADOR DE COMANDOS Y MENSAJES
# ============================================
async def handle_message(data):
    try:
        logger.info(f"Estructura recibida: {json.dumps(data, indent=2)}")
        
        event = data.get("event")
        if event != "messages.upsert":
            return

        event_data = data.get("data", {})
        
        if event_data.get("key", {}).get("fromMe", False):
            return

        remote_jid = event_data.get("key", {}).get("remoteJid", "")
        participant_alt = event_data.get("key", {}).get("participantAlt", "")
        participant_jid = event_data.get("key", {}).get("participant", "")
        push_name = event_data.get("pushName", "Participante")

        is_group = remote_jid.endswith("@g.us")

        if is_group:
            chat_id = remote_jid
            # Priorizamos participantAlt para obtener el número real si viene por LID
            if participant_alt:
                sender_phone = participant_alt.split("@")[0]
            elif participant_jid:
                sender_phone = participant_jid.split("@")[0]
            else:
                sender_phone = remote_jid.split("@")[0]
        else:
            chat_id = remote_jid.split("@")[0]
            sender_phone = chat_id

        if sender_phone == BOT_PHONE_NUMBER:
            return

        message_content = event_data.get("message", {})
        message_text = (
            message_content.get("conversation") or
            message_content.get("extendedTextMessage", {}).get("text") or ""
        ).strip()

        if not message_text:
            return

        text_lower = message_text.lower()
        data_rifa = obtener_data_completa()

        if text_lower.startswith("/"):
            parts = message_text.split()
            command = parts[0].lower()

            if command == "/start" or command == "/lista" or text_lower == "lista":
                await send_whatsapp_message(chat_id, f"Estado actual de la Rifa:\n\n{generar_texto_lista()}")
                return

            if command == "/reglas":
                await send_whatsapp_message(chat_id, obtener_texto_reglas())
                return

            if sender_phone != ADMIN_PHONE_NUMBER:
                await send_whatsapp_message(chat_id, "⛔ No estás autorizado para este comando.")
                return

            if command == "/confirmar":
                if len(parts) < 2:
                    await send_whatsapp_message(chat_id, "⚠️ Uso: `/confirmar <ID>`")
                    return
                req_id = parts[1].strip()
                solicitudes = data_rifa.get("solicitudes_pendientes", {})
                if req_id not in solicitudes:
                    await send_whatsapp_message(chat_id, f"⚠️ La solicitud `{req_id}` no existe.")
                    return
                
                sol = solicitudes[req_id]
                u_id = sol["user_id"]
                u_nums = sol["numeros"]
                u_nombre = sol["nombre"]
                chat_origen = sol["chat_origen"]
                nums_fmt = ", ".join([n.zfill(2) for n in u_nums])

                rifa = data_rifa["numeros"]
                for n in u_nums:
                    rifa[n]["estado"] = "ocupado"
                    rifa[n]["nombre"] = u_nombre
                    rifa[n]["user_id"] = u_id

                del solicitudes[req_id]
                guardar_data_completa(data_rifa)

                await send_whatsapp_message(chat_id, f"✅ Solicitud {req_id} APROBADA.")
                
                msj_exito = f"🎉 *¡PAGO CONFIRMADO!* 🎉\n\n👤 *Usuario:* {u_nombre}\n📋 *Números asignados:* {nums_fmt}\n¡Felicidades! 🙌"
                await send_whatsapp_message(chat_origen, msj_exito)
                if chat_origen != u_id:
                    await send_whatsapp_message(u_id, msj_exito)
                return

            if command == "/rechazar":
                if len(parts) < 2:
                    await send_whatsapp_message(chat_id, "⚠️ Uso: `/rechazar <ID>`")
                    return
                req_id = parts[1].strip()
                solicitudes = data_rifa.get("solicitudes_pendientes", {})
                if req_id not in solicitudes:
                    await send_whatsapp_message(chat_id, f"⚠️ La solicitud `{req_id}` no existe.")
                    return

                sol = solicitudes[req_id]
                u_id = sol["user_id"]
                u_nums = sol["numeros"]
                nums_fmt = ", ".join([n.zfill(2) for n in u_nums])

                rifa = data_rifa["numeros"]
                for n in u_nums:
                    rifa[n] = {"estado": "disponible", "nombre": "", "user_id": "", "username": ""}

                del solicitudes[req_id]
                guardar_data_completa(data_rifa)

                await send_whatsapp_message(chat_id, f"❌ Solicitud {req_id} RECHAZADA y números liberados.")
                await send_whatsapp_message(u_id, f"❌ Tu solicitud para los números *{nums_fmt}* fue rechazada.")
                return

            if command == "/reset":
                borrar_y_recrear_base_datos()
                await send_whatsapp_message(chat_id, f"🔄 Rifa reseteada.\n\n{generar_texto_lista()}")
                return

        partes = [p.strip() for p in message_text.split(",")]
        es_lista = all(p.isdigit() for p in partes) if partes else False

        if es_lista:
            estado_rifa = data_rifa.get("estado_rifa", "activa")
            if estado_rifa in ["finalizada", "bloqueada"]:
                await send_whatsapp_message(chat_id, "⛔ La lista está cerrada o bloqueada.")
                return

            rifa = data_rifa["numeros"]
            solicitudes = data_rifa.get("solicitudes_pendientes", {})
            ocupados, pendientes, validos, invalidos = [], [], [], []

            for p in partes:
                num_int = int(p)
                if 1 <= num_int <= 100:
                    num_str = str(num_int)
                    est = rifa[num_str].get("estado", "disponible")
                    if est == "ocupado":
                        ocupados.append(num_str.zfill(2))
                    elif est == "pendiente":
                        pendientes.append(num_str.zfill(2))
                    else:
                        validos.append(num_str)
                else:
                    invalidos.append(p)

            if (ocupados or pendientes or invalidos) and not validos:
                await send_whatsapp_message(chat_id, "⚠️ Los números seleccionados no están disponibles o están fuera de rango.")
                return

            if validos:
                ya_tiene = usuario_tiene_jugada_previa(sender_phone, data_rifa)
                req_id = "r" + str(uuid.uuid4().int)[:4]

                for n in validos:
                    rifa[n]["estado"] = "pendiente"

                solicitudes[req_id] = {
                    "nombre": push_name,
                    "user_id": sender_phone,
                    "numeros": validos,
                    "chat_origen": chat_id
                }

                data_rifa["numeros"] = rifa
                data_rifa["solicitudes_pendientes"] = solicitudes
                guardar_data_completa(data_rifa)

                nums_txt = ", ".join([n.zfill(2) for n in validos])
                cant = len(validos)
                total = calcular_precio_total(cant, usuario_ya_tiene_compras=ya_tiene)

                msj_usr = (
                    f"⏳ *SOLICITUD EN PROCESO* ⏳\n\n"
                    f"Hola *{push_name}*, tus números (*{nums_txt}*) están reservados temporalmente.\n"
                    f"💵 Total a transferir: *{total} reales*\n\n"
                    f"Envía tu comprobante al administrador."
                )
                await send_whatsapp_message(chat_id, msj_usr)

                msj_admin = (
                    f"📩 *NUEVA SOLICITUD* (ID: `{req_id}`)\n\n"
                    f"👤 *Cliente:* {push_name} ({sender_phone})\n"
                    f"📋 *Números:* *{nums_txt}*\n"
                    f"💰 *Total:* *{total} reales*\n\n"
                    f"Aprobar: `/confirmar {req_id}`\n"
                    f"Rechazar: `/rechazar {req_id}`"
                )
                await send_whatsapp_message(ADMIN_PHONE_NUMBER, msj_admin)

    except Exception as e:
        logger.error(f"Error procesando mensaje: {e}")

# ============================================
# SERVIDOR WEB
# ============================================
async def handle_webhook(request):
    try:
        data = await request.json()
        asyncio.create_task(handle_message(data))
        return web.Response(text="OK", status=200)
    except Exception as e:
        logger.error(f"Error en webhook: {e}")
        return web.Response(text="Error", status=500)

async def handle_health(request):
    return web.Response(text="Bot de Rifa WhatsApp Activo 24/7!")

async def start_web_server():
    app = web.Application()
    ruta_webhook = f"/{WEBHOOK_PATH.lstrip('/')}"
    app.router.add_post(ruta_webhook, handle_webhook)
    app.router.add_get("/", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"🚀 Servidor web corriendo en el puerto {PORT}")

async def main():
    inicializar_rifa()
    await start_web_server()
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot detenido correctamente.")
