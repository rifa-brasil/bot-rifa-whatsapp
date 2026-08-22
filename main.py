import os
import json
import uuid
import asyncio
from datetime import datetime
from aiohttp import web

# --- TUS CREDENCIALES DE EVOLUTION API ---
EVOLUTION_URL = "https://mi-whatsapp-api-pobo.onrender.com"
EVOLUTION_API_KEY = "55725d7c0b0fb17cb5e6564edac38c1f"
INSTANCE_NAME = "mi-bot"
ADMIN_PHONE = "5511948824359"

DB_FILE = "rifa_db.json"

# --- CONFIGURAR WEBHOOK AUTOMÁTICAMENTE AL INICIAR ---
async def configurar_webhook_automatico():
    """Configura automáticamente el webhook en Evolution API para no tener que buscarlo en menús."""
    url = f"{EVOLUTION_URL}/webhook/set/{INSTANCE_NAME}"
    headers = {
        "apikey": EVOLUTION_API_KEY,
        "Content-Type": "application/json"
    }
    # Obtenemos la URL pública de este mismo servicio en Render de forma automática o usando la fija
    webhook_url = "https://bot-rifa-whatsapp.onrender.com/webhook"
    
    payload = {
        "webhook": {
            "enabled": True,
            "url": webhook_url,
            "byEvents": False,
            "events": [
                "MESSAGES_UPSERT"
            ]
        }
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status in [200, 201]:
                    print("✅ Webhook configurado automáticamente con éxito en Evolution API.")
                else:
                    body = await resp.text()
                    print(f"⚠️ Aviso al configurar webhook ({resp.status}): {body}")
    except Exception as e:
        print(f"No se pudo conectar automáticamente con Evolution API: {e}")

# --- CLIENTE HTTP GLOBAL PARA ENVIAR MENSAJES ---
async def enviar_mensaje_whatsapp(session, to_phone, text_body, interactive_buttons=None):
    remote_jid = f"{to_phone}@s.whatsapp.net" if "@" not in str(to_phone) else to_phone

    headers = {
        "apikey": EVOLUTION_API_KEY,
        "Content-Type": "application/json",
    }

    if interactive_buttons:
        url = f"{EVOLUTION_URL}/message/sendButtons/{INSTANCE_NAME}"
        buttons_payload = [
            {"type": "reply", "displayText": btn["title"][:20], "id": btn["id"]}
            for btn in interactive_buttons[:3]
        ]
        payload = {
            "number": remote_jid,
            "title": "Gran Sorteo 100",
            "description": text_body,
            "footer": "Selecciona una opción",
            "buttons": buttons_payload
        }
    else:
        url = f"{EVOLUTION_URL}/message/sendText/{INSTANCE_NAME}"
        payload = {
            "number": remote_jid,
            "text": text_body
        }

    try:
        async with session.post(url, headers=headers, json=payload) as resp:
            if resp.status not in [200, 201]:
                body_err = await resp.text()
                print(f"Error al enviar mensaje Evolution API ({resp.status}): {body_err}")
    except Exception as e:
        print(f"Excepción enviando mensaje vía Evolution API: {e}")

# --- SERVIDOR WEB Y WEBHOOK ---
async def handle_post_webhook(request):
    try:
        body = await request.json()
        event_type = body.get("event")
        
        if event_type == "messages.upsert" or "data" in body:
            data_payload = body.get("data", {})
            key = data_payload.get("key", {})
            if key.get("fromMe", False):
                return web.Response(text="OK", status=200)

            remote_jid = key.get("remoteJid", "")
            from_phone = remote_jid.split("@")[0] if "@" in remote_jid else remote_jid
            message_data = data_payload.get("message", {})
            
            texto_mensaje = ""
            btn_id_pulsado = None

            if "conversation" in message_data:
                texto_mensaje = message_data.get("conversation", "").strip()
            elif "extendedTextMessage" in message_data:
                texto_mensaje = message_data.get("extendedTextMessage", {}).get("text", "").strip()
            elif "buttonsResponseMessage" in message_data:
                btn_id_pulsado = message_data.get("buttonsResponseMessage", {}).get("selectedButtonId")
            elif "templateButtonReplyMessage" in message_data:
                btn_id_pulsado = message_data.get("templateButtonReplyMessage", {}).get("selectedId")

            async with aiohttp.ClientSession() as session:
                if btn_id_pulsado:
                    await procesar_callback_btn(session, from_phone, btn_id_pulsado)
                elif texto_mensaje:
                    await procesar_mensaje_entrante(session, from_phone, texto_mensaje)

        return web.Response(text="EVENT_RECEIVED", status=200)
    except Exception as e:
        print(f"Error procesando webhook POST de Evolution: {e}")
        return web.Response(text="OK", status=200)

async def handle_web(request):
    return web.Response(text="Bot de Rifa con Evolution API Activo y en Línea 24/7!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_web)
    app.router.add_post("/webhook", handle_post_webhook)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"🌐 Servidor web y Webhook corriendo en el puerto {port}")

# --- GESTIÓN DE BASE DE DATOS JSON ---
def inicializar_rifa():
    try:
        if not os.path.exists(DB_FILE):
            data_inicial = {
                "estado_rifa": "activa",
                "numeros": {str(i): {"estado": "disponible", "nombre": "", "user_id": "", "username": ""} for i in range(1, 101)},
                "solicitudes_pendientes": {},
                "idiomas_usuarios": {}
            }
            with open(DB_FILE, "w") as f:
                json.dump(data_inicial, f, indent=4)
    except Exception as e:
        print(f"Error al inicializar JSON: {e}")

def borrar_y_recrear_base_datos():
    try:
        if os.path.exists(DB_FILE):
            os.remove(DB_FILE)
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
            if "idiomas_usuarios" not in data: data["idiomas_usuarios"] = {}
            return data
    except Exception as e:
        borrar_y_recrear_base_datos()
        with open(DB_FILE, "r") as f:
            return json.load(f)

def guardar_data_completa(data):
    try:
        with open(DB_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error al guardar JSON: {e}")

# --- VALORES Y PRECIOS ---
VALOR_POR_NUMERO = 10

def calcular_premio_total():
    recaudacion_total = 100 * VALOR_POR_NUMERO
    premio = recaudacion_total * 0.55
    return int(premio) if premio.is_integer() else round(premio, 2)

def calcular_precio_total(cantidad, usuario_ya_tiene_compras=False):
    if cantidad <= 0: return 0
    if usuario_ya_tiene_compras: return cantidad * VALOR_POR_NUMERO

    total = 0
    restantes = cantidad
    p5, p4, p3, p2, p1 = int(VALOR_POR_NUMERO * 4), int(VALOR_POR_NUMERO * 3.5), int(VALOR_POR_NUMERO * 2.5), int(VALOR_POR_NUMERO * 1.5), VALOR_POR_NUMERO

    if restantes >= 5:
        total += p5
        restantes -= 5
    else:
        if restantes == 4: return p4
        elif restantes == 3: return p3
        elif restantes == 2: return p2
        elif restantes == 1: return p1

    if restantes > 0:
        total += restantes * VALOR_POR_NUMERO
    return total

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

# --- GENERADORES DE TEXTO ---
def generar_teclado_idioma():
    return [
        {"id": "lang_es", "title": "🇪🇸 Cubano (Español)"},
        {"id": "lang_pt", "title": "🇧🇷 Brasileiro (PT)"}
    ]

def generar_texto_lista(lang="es"):
    data = obtener_data_completa()
    rifa = data["numeros"]
    texto = "🎟️ *LISTA OFICIAL DA RIFA (1 ao 100)* 🎟️\n\n" if lang == "pt" else "🎟️ *LISTA OFICIAL DE LA RIFA (1 al 100)* 🎟️\n\n"
    
    disponibles = 0
    for i in range(1, 101):
        num_str = str(i).zfill(2)
        info = rifa[str(i)]
        estado = info.get("estado", "disponible")

        if estado == "disponible":
            texto += f"🟢 *{num_str}*: " + ("Disponível" if lang == "pt" else "Disponible") + "\n"
            disponibles += 1
        elif estado == "pendiente":
            texto += f"🟡 *{num_str}*: " + ("Em verificação..." if lang == "pt" else "En verificación de pago...") + "\n"
        else:
            nombre = info.get("nombre", "Usuário")
            texto += f"🔴 *{num_str}*: Ocupado por {nombre}\n"
            
    texto += f"\n📊 *Resumo:* Restam {disponibles} números disponíveis." if lang == "pt" else f"\n📊 *Resumen:* Quedan {disponibles} números disponibles."
    
    estado_actual = data.get("estado_rifa")
    if estado_actual == "finalizada":
        texto += "\n\n🔒 *ESTADO:* Rifa encerrada/finalizada." if lang == "pt" else "\n\n🔒 *ESTADO:* Rifa cerrada/finalizada."
    elif estado_actual == "bloqueada":
        texto += "\n\n⛔ *ESTADO:* Rifa temporariamente bloqueada pelo administrador." if lang == "pt" else "\n\n⛔ *ESTADO:* Rifa temporalmente bloqueada por el administrador."
    return texto

def obtener_texto_reglas(lang="es"):
    premio_actual = calcular_premio_total()
    if lang == "pt":
        return (
            "📌 *REGRAS E DINÂMICA DO GRUPO (Grande Sorteio 100):*\n\n"
            "1️⃣ *Respeito:* Mantenha um ambiente de respeito absoluto.\n"
            "2️⃣ *Números e Promoção:* 100 números (01 a 100).\n"
            f"• 1 núm = {VALOR_POR_NUMERO} reais | • 5 núm = {int(VALOR_POR_NUMERO * 4)} reais (Promoção 1ª jogada).\n"
            f"⚠️ A partir da 2ª jogada, cada número custa exatamente {VALOR_POR_NUMERO} reais.\n"
            "Envie `lista` para ver os disponíveis e escreva os desejados separados por vírgula (ex: *7, 14*).\n"
            "3️⃣ Sorteio realizado apenas com 100% dos números ocupados e pagos.\n"
            "4️⃣ Garantia de reembolso integral solicitando ao administrador.\n"
            f"5️⃣ Prêmio de *{premio_actual} reais* (PIX ou CUP para Cuba).\n"
            "6️⃣ Baseado na Loteria da Flórida (Pick 3) noturna."
        )
    else:
        return (
            "📌 *REGLAS Y DINÁMICA DEL GRUPO (Gran Sorteo 100):*\n\n"
            "1️⃣ *Respeto:* Mantén un ambiente de respeto absoluto.\n"
            "2️⃣ *Números y Promoción:* 100 números (del 01 al 100).\n"
            f"• 1 núm = {VALOR_POR_NUMERO} reales | • 5 núm = {int(VALOR_POR_NUMERO * 4)} reais (Promoción 1ra jugada).\n"
            f"⚠️ A partir de tu 2da jugada, cada número cuesta exactamente {VALOR_POR_NUMERO} reales.\n"
            "Envía `lista` para ver los disponibles y escribe los que deseas separados por coma (ej: *7, 14*).\n"
            "3️⃣ El sorteo se realiza cuando los 100 números estén ocupados y pagados.\n"
            "4️⃣ Garantía de devolución íntegra con el administrador.\n"
            f"5️⃣ Premio de *{premio_actual} reales* (vía PIX o CUP en Cuba).\n"
            "6️⃣ Basado en la Lotería de Florida (Pick 3) nocturna."
        )

# --- PROCESADOR DE MENSAJES ---
async def procesar_mensaje_entrante(session, from_phone, mensaje_texto):
    comando = mensaje_texto.lower()
    data_rifa = obtener_data_completa()
    idiomas = data_rifa.get("idiomas_usuarios", {})
    lang_usuario = idiomas.get(from_phone, "es")

    if from_phone == ADMIN_PHONE:
        if comando.startswith("/bloquear"):
            data_rifa["estado_rifa"] = "bloqueada"
            guardar_data_completa(data_rifa)
            await enviar_mensaje_whatsapp(session, from_phone, "⛔ La rifa ha sido bloqueada temporalmente.")
            return
        elif comando.startswith("/desbloquear"):
            data_rifa["estado_rifa"] = "activa"
            guardar_data_completa(data_rifa)
            await enviar_mensaje_whatsapp(session, from_phone, "🟢 La rifa ha sido desbloqueada.\n\n" + generar_texto_lista("es"))
            return
        elif comando.startswith("/reset"):
            borrar_y_recrear_base_datos()
            await enviar_mensaje_whatsapp(session, from_phone, "🔄 ¡Gran Sorteo 100 ha sido reseteado con éxito!")
            return
        elif comando.startswith("/ganador"):
            partes_cmd = comando.split()
            if len(partes_cmd) > 1 and partes_cmd[1].isdigit():
                num_str = str(int(partes_cmd[1]))
                info_num = data_rifa["numeros"].get(num_str, {})
                if info_num.get("estado") == "ocupado":
                    data_rifa["estado_rifa"] = "finalizada"
                    guardar_data_completa(data_rifa)
                    ganador_nombre = info_num.get("nombre")
                    premio_actual = calcular_premio_total()
                    msg_ganador = f"🎉 ¡Felicidades {ganador_nombre}! Has ganado con el número {num_str.zfill(2)} un premio de {premio_actual} reales."
                    await enviar_mensaje_whatsapp(session, from_phone, msg_ganador)
                    if info_num.get("user_id"):
                        await enviar_mensaje_whatsapp(session, info_num.get("user_id"), msg_ganador)
                    return

    if comando in ["hola", "buenas", "lista", "inicio", "rifa", "sorteo", "reglas"]:
        if comando == "reglas":
            texto_resp = obtener_texto_reglas(lang_usuario)
        else:
            texto_resp = f"Estado actual de Gran Sorteo 100:\n\n{generar_texto_lista(lang_usuario)}"
        
        await enviar_mensaje_whatsapp(session, from_phone, texto_resp, interactive_buttons=generar_teclado_idioma())
        return

    partes = [p.strip() for p in mensaje_texto.split(",")]
    es_lista_numeros = all(p.isdigit() for p in partes) if partes else False

    if es_lista_numeros:
        estado_actual_rifa = data_rifa.get("estado_rifa", "activa")
        if estado_actual_rifa in ["finalizada", "bloqueada"]:
            await enviar_mensaje_whatsapp(session, from_phone, "⛔ Lo sentimos, la lista se encuentra cerrada o bloqueada.")
            return

        rifa = data_rifa["numeros"]
        solicitudes = data_rifa.get("solicitudes_pendientes", {})
        validos_para_reservar = []

        for p in partes:
            num_elegido = int(p)
            if 1 <= num_elegido <= 100:
                num_str = str(num_elegido)
                if rifa[num_str].get("estado", "disponible") == "disponible":
                    validos_para_reservar.append(num_str)

        if validos_para_reservar:
            ya_tiene_compras = usuario_tiene_jugada_previa(from_phone, data_rifa)
            req_id = "r" + str(uuid.uuid4().int)[:4]
            
            for n in validos_para_reservar:
                rifa[n]["estado"] = "pendiente"

            solicitudes[req_id] = {
                "nombre": f"Usuario_{from_phone[-4:]}",
                "user_id": from_phone,
                "numeros": validos_para_reservar
            }

            data_rifa["numeros"] = rifa
            data_rifa["solicitudes_pendientes"] = solicitudes
            guardar_data_completa(data_rifa)

            nums_solicitados_txt = ", ".join([n.zfill(2) for n in validos_para_reservar])
            cantidad_numeros = len(validos_para_reservar)
            total_a_pagar = calcular_precio_total(cantidad_numeros, usuario_ya_tiene_compras=ya_tiene_compras)

            msg_usuario = (
                f"⏳ *SOLICITUD EN PROCESO* ⏳\n\n"
                f"Tus números (*{nums_solicitados_txt}*) están reservados temporalmente.\n"
                f"💰 Cantidad: *{cantidad_numeros}*\n"
                f"💵 Total a transferir: *{total_a_pagar} reales*\n\n"
                f"Contacta al administrador para pagar."
            )
            await enviar_mensaje_whatsapp(session, from_phone, msg_usuario)

            botones_admin = [
                {"id": f"conf_{req_id}", "title": "🟢 Aprobar"},
                {"id": f"rech_{req_id}", "title": "🔴 Rechazar"}
            ]
            msg_admin = (
                f"📥 *NUEVA SOLICITUD* (ID: `{req_id}`)\n"
                f"📱 *Teléfono:* {from_phone}\n"
                f"🎟️ *Números:* *{nums_solicitados_txt}*\n"
                f"💵 *Total:* *{total_a_pagar} reales*"
            )
            await enviar_mensaje_whatsapp(session, ADMIN_PHONE, msg_admin, interactive_buttons=botones_admin)

# --- PROCESADOR DE BOTONES INTERACTIVOS (CALLBACKS) ---
async def procesar_callback_btn(session, from_phone, btn_id):
    data_rifa = obtener_data_completa()

    if btn_id.startswith("lang_"):
        lang = btn_id.split("_")[1]
        if "idiomas_usuarios" not in data_rifa:
            data_rifa["idiomas_usuarios"] = {}
        data_rifa["idiomas_usuarios"][from_phone] = lang
        guardar_data_completa(data_rifa)

        texto_resp = f"✅ Idioma actualizado.\n\n{generar_texto_lista(lang)}"
        await enviar_mensaje_whatsapp(session, from_phone, texto_resp, interactive_buttons=generar_teclado_idioma())
        return

    if from_phone != ADMIN_PHONE:
        return

    accion, req_id = btn_id.split("_", 1)
    rifa = data_rifa["numeros"]
    solicitudes = data_rifa.get("solicitudes_pendientes", {})

    if req_id not in solicitudes:
        await enviar_mensaje_whatsapp(session, ADMIN_PHONE, f"⚠️ La solicitud `{req_id}` ya fue procesada.")
        return

    sol = solicitudes[req_id]
    user_phone = sol["user_id"]
    user_nums = sol["numeros"]
    nums_formatted = ", ".join([n.zfill(2) for n in user_nums])

    if accion == "conf":
        for n in user_nums:
            rifa[n]["estado"] = "ocupado"
            rifa[n]["nombre"] = f"Cliente_{user_phone[-4:]}"
            rifa[n]["user_id"] = user_phone

        del solicitudes[req_id]
        data_rifa["numeros"] = rifa
        data_rifa["solicitudes_pendientes"] = solicitudes

        if all(rifa[str(n)]["estado"] == "ocupado" for n in range(1, 101)):
            data_rifa["estado_rifa"] = "finalizada"

        guardar_data_completa(data_rifa)
        await enviar_mensaje_whatsapp(session, ADMIN_PHONE, f"✅ Aprobado con éxito. Números: {nums_formatted}")

        msg_confirmacion = f"🎉 *¡PAGO CONFIRMADO!* 🎉\n\nTus números ({nums_formatted}) ya están oficiales. ¡Muchas felicidades y mucha suerte! 🤝"
        await enviar_mensaje_whatsapp(session, user_phone, msg_confirmacion)

    elif accion == "rech":
        for n in user_nums:
            rifa[n] = {"estado": "disponible", "nombre": "", "user_id": "", "username": ""}

        del solicitudes[req_id]
        data_rifa["numeros"] = rifa
        data_rifa["solicitudes_pendientes"] = solicitudes
        guardar_data_completa(data_rifa)
        
        await enviar_mensaje_whatsapp(session, ADMIN_PHONE, f"❌ Solicitud rechazada.")
        await enviar_mensaje_whatsapp(session, user_phone, f"❌ Tu solicitud para los números *{nums_formatted}* fue rechazada.")

# --- FUNCIÓN PRINCIPAL ---
async def main():
    inicializar_rifa()
    # Configura el webhook automáticamente en cuanto enciende el bot
    await configurar_webhook_automatico()
    await start_web_server()

    stop_signal = asyncio.Event()
    await stop_signal.wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot detenido correctamente.")
