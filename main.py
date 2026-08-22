import os
import json
import uuid
import asyncio
from datetime import datetime
from aiohttp import web

# --- CONFIGURACIÓN DE CREDENCIALES DE WHATSAPP ---
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")  
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")  
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "rifa_token_secreto")  
ADMIN_PHONE = os.environ.get("ADMIN_PHONE", "5562999999999")  
GRUPO_JID = os.environ.get("GRUPO_JID", "")  # ID del grupo (ej: 1203630... @g.us)

DB_FILE = "rifa_db.json"

# --- CLIENTE HTTP GLOBAL PARA ENVIAR MENSAJES A WHATSAPP ---
async def enviar_mensaje_whatsapp(session, destino_id, text_body, interactive_buttons=None):
    """Envía un mensaje de texto o interactivo a un usuario privado o a un grupo de WhatsApp."""
    url = f"https://graph.facebook.com/v17.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": destino_id,
        "type": "text"
    }

    # Si el destino es un grupo (termina en @g.us), quitamos 'recipient_type' porque Meta lo rechaza en grupos
    if "@g.us" in str(destino_id):
        payload.pop("recipient_type", None)

    if interactive_buttons:
        payload["type"] = "interactive"
        payload["interactive"] = {
            "type": "button",
            "body": {"text": text_body},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": btn["id"], "title": btn["title"][:20]}}
                    for btn in interactive_buttons[:3]
                ]
            }
        }
    else:
        payload["text"] = {"body": text_body, "preview_url": False}

    try:
        async with session.post(url, headers=headers, json=payload) as resp:
            if resp.status != 200:
                body_err = await resp.text()
                print(f"Error al enviar mensaje WhatsApp a {destino_id} ({resp.status}): {body_err}")
    except Exception as e:
        print(f"Excepción enviando mensaje a WhatsApp: {e}")

# --- SERVIDOR WEB Y WEBHOOK PARA RENDER ---
async def handle_get_webhook(request):
    hub_mode = request.query.get("hub.mode")
    hub_challenge = request.query.get("hub.challenge")
    hub_verify_token = request.query.get("hub.verify_token")

    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        return web.Response(text=hub_challenge, status=200)
    return web.Response(text="Fallo de verificación de token", status=403)

async def handle_post_webhook(request):
    try:
        body = await request.json()
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                
                contacts = value.get("contacts", [])
                nombre_contacto = "Usuario"
                if contacts:
                    nombre_contacto = contacts[0].get("profile", {}).get("name", "Usuario")

                messages = value.get("messages", [])
                if messages:
                    msg = messages[0]
                    from_phone = msg.get("from")  
                    msg_type = msg.get("type")
                    
                    # Verificamos si el mensaje viene de un grupo o de un chat privado
                    chat_id_or_sender = msg.get("chat_id") or from_phone
                    # Si el mensaje viene de un grupo, el 'from' suele ser el usuario pero el chat de origen es el grupo.
                    # Meta Cloud API envía el ID del grupo en el campo 'to' o en contextos de grupo. 
                    # Lo más seguro es procesar el texto y responder al usuario en privado o al grupo según corresponda.
                    
                    async with aiohttp.ClientSession() as session:
                        if msg_type == "text":
                            text_content = msg.get("text", {}).get("body", "").strip()
                            await procesar_mensaje_entrante(session, from_phone, nombre_contacto, text_content)
                        elif msg_type == "interactive":
                            interactive_data = msg.get("interactive", {})
                            if interactive_data.get("type") == "button_reply":
                                btn_id = interactive_data.get("button_reply", {}).get("id")
                                await procesar_callback_btn(session, from_phone, btn_id)
                                
        return web.Response(text="EVENT_RECEIVED", status=200)
    except Exception as e:
        print(f"Error procesando webhook POST: {e}")
        return web.Response(text="OK", status=200)

async def handle_web(request):
    return web.Response(text="Bot de Rifa WhatsApp Activo y en Línea 24/7!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_web)
    app.router.add_get("/webhook", handle_get_webhook)
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
            f"• 1 núm = {VALOR_POR_NUMERO} reales | • 5 núm = {int(VALOR_POR_NUMERO * 4)} reais (Promoción 1ra jogada).\n"
            f"⚠️ A partir de tu 2da jogada, cada número cuesta exactamente {VALOR_POR_NUMERO} reales.\n"
            "Envía `lista` para ver los disponibles y escribe los que deseas separados por coma (ej: *7, 14*).\n"
            "3️⃣ El sorteo se realiza cuando los 100 números estén ocupados y pagados.\n"
            "4️⃣ Garantía de devolución íntegra con el administrador.\n"
            f"5️⃣ Premio de *{premio_actual} reales* (vía PIX o CUP en Cuba).\n"
            "6️⃣ Basado en la Lotería de Florida (Pick 3) nocturna."
        )

# --- PROCESADOR DE MENSAJES ---
async def procesar_mensaje_entrante(session, from_phone, nombre_contacto, mensaje_texto):
    comando = mensaje_texto.lower()
    data_rifa = obtener_data_completa()
    idiomas = data_rifa.get("idiomas_usuarios", {})
    lang_usuario = idiomas.get(from_phone, "es")

    # Comandos de Administrador
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

    # Comandos generales
    if comando in ["hola", "buenas", "lista", "inicio", "rifa", "sorteo", "reglas"]:
        if comando == "reglas":
            texto_resp = obtener_texto_reglas(lang_usuario)
        else:
            texto_resp = f"Estado actual de Gran Sorteo 100:\n\n{generar_texto_lista(lang_usuario)}"
        
        await enviar_mensaje_whatsapp(session, from_phone, texto_resp, interactive_buttons=generar_teclado_idioma())
        return

    # Selección de números separados por coma
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
                "nombre": nombre_contacto,
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

            # Notificar al Administrador con botones interactivos
            botones_admin = [
                {"id": f"conf_{req_id}", "title": "🟢 Aprobar"},
                {"id": f"rech_{req_id}", "title": "🔴 Rechazar"}
            ]
            msg_admin = (
                f"📥 *NUEVA SOLICITUD* (ID: `{req_id}`)\n"
                f"👤 *Cliente:* {nombre_contacto} ({from_phone})\n"
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
    user_nombre = sol["nombre"]
    user_nums = sol["numeros"]
    nums_formatted = ", ".join([n.zfill(2) for n in user_nums])

    if accion == "conf":
        for n in user_nums:
            rifa[n]["estado"] = "ocupado"
            rifa[n]["nombre"] = user_nombre
            rifa[n]["user_id"] = user_phone

        del solicitudes[req_id]
        data_rifa["numeros"] = rifa
        data_rifa["solicitudes_pendientes"] = solicitudes

        if all(rifa[str(n)]["estado"] == "ocupado" for n in range(1, 101)):
            data_rifa["estado_rifa"] = "finalizada"

        guardar_data_completa(data_rifa)
        await enviar_mensaje_whatsapp(session, ADMIN_PHONE, f"✅ Aprobado con éxito. Números: {nums_formatted}")

        # Mensaje al privado del usuario
        msg_confirmacion = f"🎉 *¡PAGO CONFIRMADO!* 🎉\n\nTus números ({nums_formatted}) ya están oficiales. ¡Muchas felicidades y mucha suerte! 🤝"
        await enviar_mensaje_whatsapp(session, user_phone, msg_confirmacion)

        # Enviar aviso público al grupo configurado en GRUPO_JID en Render
        if GRUPO_JID:
            msg_grupo = f"🎉 *¡NUEVA JUGADA APROBADA!* 🎉\n\n👤 *Participante:* {user_nombre}\n🎟️ *Números asignados:* {nums_formatted}\n\n{generar_texto_lista('es')}"
            await enviar_mensaje_whatsapp(session, GRUPO_JID, msg_grupo)

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
    await start_web_server()

    stop_signal = asyncio.Event()
    await stop_signal.wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot detenido correctamente.")
