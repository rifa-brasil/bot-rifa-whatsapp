import os
import json
import requests
import re
import uuid
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
 
app = Flask(__name__)
 
# 🔑 TOKEN DE WHAPI (Asegúrate de que en Whapi esté escaneado el QR del +5353215119)
WHAPI_TOKEN = "zL78J7yS7OM8I3ml5Ybvps1rkcxbKV7K" 
WHAPI_API_URL = "https://gate.whapi.cloud/messages/text"
 
# 🔑 ID DE RESPALDO DE TU GRUPO
GRUPO_CHAT_ID_RESPALDO = "DyI3ISDPZjyKw3w0cD8elC@g.us"
 
# 👑 1. ADMINISTRADOR GENERAL (ÚNICO AUTORIZADO A CONFIRMAR/RECHAZAR PAGOS)
WHATSAPP_ADMIN_PHONE = "5511948824359" 
WHATSAPP_ADMIN_CHAT_ID = f"{WHATSAPP_ADMIN_PHONE}@s.whatsapp.net"
NUMERO_ADMIN_SEGURO = "48824359" # Tus últimos 8 dígitos
 
# 🤖 2. BOT ASISTENTE ENCARGADO (+5353215119)
BOT_ASISTENTE_PHONE = "5353215119"
 
# 🔑 CLAVE SECRETA DE ADMINISTRADOR
CLAVE_RESET = "admin.resetear.rifa.99"
 
DB_FILE = "rifa_db.json"
 
def inicializar_rifa():
    try:
        if not os.path.exists(DB_FILE):
            data_inicial = {
                "estado_rifa": "activa",
                "numeros": {str(i): {"estado": "disponible", "nombre": "", "telefono": "", "enlace": "", "solicitud_id": ""} for i in range(1, 101)},
                "solicitudes_pendientes": {}
            }
            with open(DB_FILE, "w") as f:
                json.dump(data_inicial, f, indent=4)
    except Exception as e:
        print(f"🔴 Error al inicializar JSON: {e}")
 
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
            if "estado_rifa" not in data:
                data["estado_rifa"] = "activa"
            if "solicitudes_pendientes" not in data:
                data["solicitudes_pendientes"] = {}
            return data
    except Exception as e:
        print(f"🔴 Error al leer JSON (recreando base): {e}")
        borrar_y_recrear_base_datos()
        with open(DB_FILE, "r") as f:
            return json.load(f)
 
def guardar_data_completa(data):
    try:
        with open(DB_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"🔴 Error al guardar JSON: {e}")
 
def generar_texto_lista():
    data = obtener_data_completa()
    rifa = data["numeros"]
    texto = "🎟️ *LISTA OFICIAL DE LA RIFA (1 al 100)* 🎟️\n\n"
    disponibles = 0
    for i in range(1, 101):
        num_str = str(i).zfill(2)
        info = rifa[str(i)]
        estado = info.get("estado", "disponible")
 
        if estado == "disponible":
            texto += f"🟢 *{num_str}*: Disponible\n"
            disponibles += 1
        elif estado == "pendiente":
            texto += f"🟡 *{num_str}*: En verificación de pago...\n"
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
    if data.get("estado_rifa") == "finalizada":
        texto += "\n\n🔒 *ESTADO:* Rifa cerrada/finalizada. No se permiten más modificaciones."
    return texto
 
def enviar_mensaje_whapi(chat_id, texto, menciones=[]):
    payload = {"to": chat_id, "body": texto}
    if menciones:
        payload["mentions"] = menciones
 
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Bearer {WHAPI_TOKEN}"
    }
    try:
        r = requests.post(WHAPI_API_URL, json=payload, headers=headers)
        print(f"📤 Envío a {chat_id}: Estado {r.status_code} -> Respuesta: {r.text}")
        return r.status_code == 200 or r.status_code == 201
    except Exception as e:
        print(f"🔴 Error al enviar a Whapi: {e}")
        return False
 
@app.route("/", methods=["GET"])
def home():
    return "Servidor conectado con Whapi listo.", 200
 
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data_webhook = request.get_json()
        if not data_webhook:
            return "No data", 200
 
        messages = data_webhook.get("messages", [])
        if not messages:
            return "No messages", 200
 
        msg = messages[0]
        
        text_obj = msg.get("text", {})
        mensaje_texto = text_obj.get("body", "").strip() if text_obj else ""
        comando = mensaje_texto.lower()
 
        # 🛑 EVITAR BUCLE DE AUTO-RESPUESTA
        if "lista oficial de la rifa" in comando or "participantes convocados" in comando or "tenemos un ganador" in comando:
            return "Ignored loop", 200
 
        chat_id_actual = msg.get("chat_id", "")
        raw_from = msg.get("from", "")
        
        if not raw_from:
            raw_from = msg.get("sender_id", chat_id_actual)
 
        id_antes_del_arroba = raw_from.split("@")[0]
        numero_persona = re.sub(r'\D', '', id_antes_del_arroba)
        
        nombre_usuario = msg.get("from_name", "").strip() or msg.get("sender_name", "").strip() or f"+{numero_persona}"
 
        data_rifa = obtener_data_completa()
        rifa = data_rifa["numeros"]
        solicitudes = data_rifa.get("solicitudes_pendientes", {})
        estado_actual_rifa = data_rifa.get("estado_rifa", "activa")
        
        respuesta = ""
 
        # 🔒 FILTRO MÁSTER DE SEGURIDAD (Exclusivo para ti +5511948824359)
        es_admin_general = (NUMERO_ADMIN_SEGURO in numero_persona) or (WHATSAPP_ADMIN_PHONE in numero_persona)
 
        # 🔄 COMANDO RESET
        if comando == CLAVE_RESET:
            if not es_admin_general:
                return "OK", 200
            borrar_y_recrear_base_datos()
            respuesta = "🔄 *¡La rifa ha sido reseteada con éxito!* Todos los 100 números vuelven a estar disponibles y el sistema está abierto.\n\n" + generar_texto_lista()
 
        # ✅/❌ APROBACIÓN MANUAL (BÚSQUEDA FLEXIBLE DE ID)
        elif comando.startswith("confirmar ") or comando.startswith("rechazar "):
            if not es_admin_general:
                print(f"⛔ DENEGADO: El número {numero_persona} no es el Administrador General.")
                return "OK", 200
            
            partes_cmd = mensaje_texto.strip().split()
            accion = partes_cmd[0].lower()
            req_id_input = partes_cmd[1].strip() if len(partes_cmd) > 1 else ""
 
            # Buscar la clave coincidente ignorando mayúsculas/minúsculas
            req_id_encontrado = None
            for key in solicitudes.keys():
                if key.lower() == req_id_input.lower():
                    req_id_encontrado = key
                    break
 
            if req_id_encontrado:
                sol = solicitudes[req_id_encontrado]
                user_nombre = sol["nombre"]
                user_phone = sol["telefono"]
                user_nums = sol["numeros"]
                grupo_origen = sol["grupo_id"]
 
                nums_formatted = ", ".join([n.zfill(2) for n in user_nums])
 
                if accion == "confirmar":
                    for n in user_nums:
                        rifa[n]["estado"] = "ocupado"
                        rifa[n]["nombre"] = user_nombre
                        rifa[n]["telefono"] = user_phone
                        rifa[n]["enlace"] = f"wa.me/{user_phone.replace('+', '').strip()}"
 
                    del solicitudes[req_id_encontrado]
                    data_rifa["numeros"] = rifa
                    data_rifa["solicitudes_pendientes"] = solicitudes
 
                    todos_ocupados = all(rifa[str(n)]["estado"] == "ocupado" for n in range(1, 101))
                    if todos_ocupados:
                        data_rifa["estado_rifa"] = "finalizada"
 
                    guardar_data_completa(data_rifa)
 
                    # 🔹 PREPARAR ID Y NÚMERO DEL USUARIO PARA MENCIÓN Y MENSAJE PRIVADO
                    numero_limpio = user_phone.replace("+", "").strip()
                    user_chat_id = f"{numero_limpio}@s.whatsapp.net"

                    # 1. Respuesta al Administrador (Para ti)
                    enviar_mensaje_whapi(chat_id_actual, f"✅ *Solicitud {req_id_encontrado} APROBADA.* Los números ({nums_formatted}) fueron asignados exitosamente a {user_nombre}.")

                    # 2. Notificación Oficial al Grupo (Mencionando al usuario y SIN la lista completa)
                    msg_grupo = f"🎉 *¡PAGO CONFIRMADO!* 🎉\n\n👤 *Usuario:* @{numero_limpio}\n🎟️ *Números asignados:* *{nums_formatted}*\n\n¡Gracias por tu compra y mucha suerte! 🤝"
                    enviar_mensaje_whapi(grupo_origen, msg_grupo, menciones=[user_chat_id])
                    
                    # 3. Mensaje Automático al Privado del Usuario (Redacción adaptada)
                    msg_privado = (
                        f"🎉 *¡Hola {user_nombre}!* 🎉\n\n"
                        f"Soy el bot asistente de la rifa. El *Administrador General* acaba de verificar tu pago "
                        f"y me ha pedido que te confirme tu jugada.\n\n"
                        f"Tus números (*{nums_formatted}*) ya están registrados oficialmente a tu nombre.\n\n"
                        f"Si tienes alguna consulta, puedes contactar al administrador aquí: wa.me/{WHATSAPP_ADMIN_PHONE}\n\n"
                        f"¡Mucha suerte! 🍀"
                    )
                    enviar_mensaje_whapi(user_chat_id, msg_privado)
 
                elif accion == "rechazar":
                    for n in user_nums:
                        rifa[n] = {"estado": "disponible", "nombre": "", "telefono": "", "enlace": "", "solicitud_id": ""}
 
                    del solicitudes[req_id_encontrado]
                    data_rifa["numeros"] = rifa
                    data_rifa["solicitudes_pendientes"] = solicitudes
                    guardar_data_completa(data_rifa)
 
                    enviar_mensaje_whapi(chat_id_actual, f"❌ *Solicitud {req_id_encontrado} RECHAZADA.* Los números ({nums_formatted}) vuelven a estar disponibles.")
 
                    # Notificación de cancelación al grupo
                    msg_grupo = f"⚠️ *SOLICITUD CANCELADA* ⚠️\n\nHola {user_nombre}, tu solicitud para el/los número(s) *{nums_formatted}* fue rechazada. Los números vuelven a estar 🟢 *Disponibles* para los demás participantes."
                    enviar_mensaje_whapi(grupo_origen, msg_grupo)
 
            else:
                enviar_mensaje_whapi(chat_id_actual, f"⚠️ No se encontró la solicitud ID: `{req_id_input}` o ya fue procesada.")
            return "OK", 200
 
        # ✨ SALUDO / LISTA
        elif comando in ["hola", "buenas", "lista", "inicio", "rifa"]:
            respuesta = (
                f"¡Hola {nombre_usuario}! Aquí tienes el estado actual de la Rifa. ✨\n\n"
                f"💵 *Compra uno o varios números por un valor de 10 reales y gana 400 reales.*\n"
                f"🏆 El premio se entregará aquí en Brasil mediante transferencia PIX o al familiar en Cuba en CUP.\n\n"
                f"{generar_texto_lista()}"
            )
            if estado_actual_rifa == "activa":
                respuesta += "\n\n👉 *¿Cómo comprar?* Responde escribiendo el número que deseas (ej: *7, 14*)."
 
        # 🛒 PROCESO DE RESERVAS DE NÚMEROS
        else:
            partes = [p.strip() for p in mensaje_texto.split(",")]
            es_lista_numeros = all(p.isdigit() for p in partes) if partes and mensaje_texto else False
 
            if es_lista_numeros:
                if estado_actual_rifa == "finalizada":
                    respuesta = "🔒 *Lo sentimos, el sistema está cerrado.* El sorteo ya concluyó o está congelado."
                    enviar_mensaje_whapi(chat_id_actual, respuesta)
                    return "OK", 200
 
                ocupados, pendientes, validos_para_reservar, invalidos = [], [], [], []
 
                for p in partes:
                    num_elegido = int(p)
                    if 1 <= num_elegido <= 100:
                        num_str = str(num_elegido)
                        info = rifa[num_str]
                        est = info.get("estado", "disponible")
 
                        if est == "ocupado":
                            ocupados.append(f"*{num_str.zfill(2)}*")
                        elif est == "pendiente":
                            pendientes.append(f"*{num_str.zfill(2)}*")
                        else:
                            validos_para_reservar.append(num_str)
                    else:
                        invalidos.append(p)
 
                mensajes_conflicto = []
                if ocupados:
                    mensajes_conflicto.append(f"🔴 El/los número(s) {', '.join(ocupados)} ya está(n) *OCUPADO(S)*.")
                if pendientes:
                    mensajes_conflicto.append(f"🟡 El/los número(s) {', '.join(pendientes)} está(n) *EN PROCESO DE VERIFICACIÓN DE PAGO* por otro participante.")
                if invalidos:
                    mensajes_conflicto.append(f"⚠️ El/los número(s) {', '.join(invalidos)} está(n) fuera del rango (1 al 100).")
 
                if mensajes_conflicto and not validos_para_reservar:
                    respuesta = f"Hola {nombre_usuario}:\n" + "\n".join(mensajes_conflicto)
                    enviar_mensaje_whapi(chat_id_actual, respuesta)
                    return "OK", 200
 
                if validos_para_reservar:
                    # Generar ID en minúsculas para evitar descalce
                    req_id = "r" + str(uuid.uuid4().int)[:4]
 
                    for n in validos_para_reservar:
                        rifa[n]["estado"] = "pendiente"
                        rifa[n]["solicitud_id"] = req_id
 
                    solicitudes[req_id] = {
                        "nombre": nombre_usuario,
                        "telefono": f"+{numero_persona}",
                        "numeros": validos_para_reservar,
                        "grupo_id": chat_id_actual if "@g.us" in chat_id_actual else GRUPO_CHAT_ID_RESPALDO
                    }
 
                    data_rifa["numeros"] = rifa
                    data_rifa["solicitudes_pendientes"] = solicitudes
                    guardar_data_completa(data_rifa)
 
                    nums_solicitados_txt = ", ".join([n.zfill(2) for n in validos_para_reservar])
 
                    # 1. Notificar en el grupo
                    txt_grupo = (
                        f"⏳ *SOLICITUD RECIBIDA* ⏳\n\n"
                        f"Hola {nombre_usuario}, recibimos tu pedido para el/los número(s): *{nums_solicitados_txt}*.\n\n"
                        f"🟡 Quedan *reservados temporalmente* mientras el administrador verifica tu transferencia."
                    )
                    if mensajes_conflicto:
                        txt_grupo += "\n\n📌 *Nota:* " + " \n".join(mensajes_conflicto)
 
                    enviar_mensaje_whapi(chat_id_actual, txt_grupo)
 
                    # 2. Notificación al chat privado del Administrador General (+5511948824359)
                    link_confirmar = f"wa.me/{BOT_ASISTENTE_PHONE}?text=confirmar%20{req_id}"
                    link_rechazar = f"wa.me/{BOT_ASISTENTE_PHONE}?text=rechazar%20{req_id}"
 
                    txt_admin = (
                        f"📥 *NUEVA SOLICITUD DE COMPRA* (ID: `{req_id}`)\n\n"
                        f"👤 *Cliente:* {nombre_usuario}\n"
                        f"📱 *Teléfono:* wa.me/{numero_persona}\n"
                        f"🎟️ *Números:* *{nums_solicitados_txt}*\n\n"
                        f"-----------------------------------\n"
                        f"Toca una opción para responder:\n\n"
                        f"🟢 *[ CONFIRMAR PAGO ]*\n{link_confirmar}\n\n"
                        f"🔴 *[ RECHAZAR PAGO ]*\n{link_rechazar}"
                    )
                    
                    enviar_mensaje_whapi(WHATSAPP_ADMIN_CHAT_ID, txt_admin)
                    return "OK", 200
 
        if respuesta:
            enviar_mensaje_whapi(chat_id_actual, respuesta)
 
    except Exception as e_global:
        print(f"💥 ERROR CRÍTICO: {e_global}")
 
    return "OK", 200
 
if __name__ == "__main__":
    inicializar_rifa()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
     
