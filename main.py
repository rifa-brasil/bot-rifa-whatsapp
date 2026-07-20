import os
import json
import requests
import re
import uuid
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

app = Flask(__name__)

# 🔑 TU TOKEN DEL CANAL SANDBOX DE WHAPI
WHAPI_TOKEN = "zL78J7yS7OM8I3ml5Ybvps1rkcxbKV7K" 
WHAPI_API_URL = "https://gate.whapi.cloud/messages/text"

# 🔑 ID DE RESPALDO DE TU GRUPO
GRUPO_CHAT_ID_RESPALDO = "DyI3ISDPZjyKw3w0cD8elC@g.us"

# 🔐 FILTRO DE SEGURIDAD MÁSTER: Tus últimos 8 dígitos (São Paulo)
NUMERO_ADMIN_SEGURO = "48824359"

# 🔑 TU CLAVE SECRETA DE ADMINISTRADOR PARA RESETEAR
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
        print(f"📤 Envío a {chat_id}: Estado {r.status_code}")
    except Exception as e:
        print(f"Error al enviar a Whapi: {e}")

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

        # 🛑 EVITAR BUCLE
        if "lista oficial de la rifa" in comando or "participantes convocados" in comando or "tenemos un ganador" in comando:
            return "Ignored loop", 200

        chat_id_actual = msg.get("chat_id", "")
        raw_from = msg.get("from", "")
        
        if not raw_from:
            raw_from = msg.get("sender_id", chat_id_actual)

        id_antes_del_arroba = raw_from.split("@")[0]
        numero_persona = re.sub(r'\D', '', id_antes_del_arroba)
        link_directo = f"wa.me/{numero_persona}"
        
        nombre_usuario = msg.get("from_name", "").strip() or msg.get("sender_name", "").strip() or f"+{numero_persona}"

        data_rifa = obtener_data_completa()
        rifa = data_rifa["numeros"]
        solicitudes = data_rifa.get("solicitudes_pendientes", {})
        estado_actual_rifa = data_rifa.get("estado_rifa", "activa")
        
        respuesta = ""
        es_admin_real = NUMERO_ADMIN_SEGURO in numero_persona or msg.get("from_me") is True or msg.get("outbound") is True

        # 🔄 COMANDO RESET
        if comando == CLAVE_RESET:
            if not es_admin_real:
                return "OK", 200
            borrar_y_recrear_base_datos()
            respuesta = "🔄 *¡La rifa ha sido reseteada con éxito!* Todos los 100 números vuelven a estar disponibles y el sistema está abierto.\n\n" + generar_texto_lista()

        # ✅/❌ APROBACIÓN MANUAL DEL ADMINISTRADOR
        elif comando.startswith("confirmar ") or comando.startswith("rechazar "):
            if not es_admin_real:
                return "OK", 200
            
            partes_cmd = comando.split()
            accion = partes_cmd[0]
            req_id = partes_cmd[1] if len(partes_cmd) > 1 else ""

            if req_id in solicitudes:
                sol = solicitudes[req_id]
                user_nombre = sol["nombre"]
                user_phone = sol["telefono"]
                user_nums = sol["numeros"]
                grupo_origen = sol["grupo_id"]

                nums_formatted = ", ".join([n.zfill(2) for n in user_nums])

                if accion == "confirmar":
                    # Pasar de pendiente a ocupado definitivamente
                    for n in user_nums:
                        rifa[n]["estado"] = "ocupado"
                        rifa[n]["nombre"] = user_nombre
                        rifa[n]["telefono"] = user_phone
                        rifa[n]["enlace"] = f"wa.me/{user_phone.replace('+', '').strip()}"

                    del solicitudes[req_id]
                    data_rifa["numeros"] = rifa
                    data_rifa["solicitudes_pendientes"] = solicitudes

                    # Verificar si la lista se completó (100 ocupados)
                    todos_ocupados = all(rifa[str(n)]["estado"] == "ocupado" for n in range(1, 101))
                    if todos_ocupados:
                        data_rifa["estado_rifa"] = "finalizada"

                    guardar_data_completa(data_rifa)

                    # Confirmar al administrador
                    enviar_mensaje_whapi(chat_id_actual, f"✅ *Solicitud {req_id} APROBADA.* Los números ({nums_formatted}) fueron asignados a {user_nombre}.")

                    # Notificar al Grupo
                    msg_grupo = f"🎉 *¡PAGO CONFIRMADO!* 🎉\n\n👤 *Usuario:* {user_nombre}\n🎟️ *Números asignados:* {nums_formatted}\n\n¡Gracias por tu compra! 🤝\n\n" + generar_texto_lista()
                    enviar_mensaje_whapi(grupo_origen, msg_grupo)

                elif accion == "rechazar":
                    # Liberar los números nuevamente
                    for n in user_nums:
                        rifa[n] = {"estado": "disponible", "nombre": "", "telefono": "", "enlace": "", "solicitud_id": ""}

                    del solicitudes[req_id]
                    data_rifa["numeros"] = rifa
                    data_rifa["solicitudes_pendientes"] = solicitudes
                    guardar_data_completa(data_rifa)

                    # Confirmar al administrador
                    enviar_mensaje_whapi(chat_id_actual, f"❌ *Solicitud {req_id} RECHAZADA.* Los números ({nums_formatted}) vuelven a estar disponibles.")

                    # Notificar al Grupo
                    msg_grupo = f"⚠️ *SOLICITUD CANCELADA* ⚠️\n\nHola {user_nombre}, tu solicitud para el/los número(s) *{nums_formatted}* no ha sido aprobada. Los números vuelven a estar 🟢 *Disponibles* para los demás participantes."
                    enviar_mensaje_whapi(grupo_origen, msg_grupo)

            else:
                enviar_mensaje_whapi(chat_id_actual, f"⚠️ No se encontró la solicitud ID: `{req_id}` o ya fue procesada.")
            return "OK", 200

        # 🏆 DETECTAR GANADOR AUTOMÁTICAMENTE
        elif comando.startswith("resultado de florida con"):
            if not es_admin_real:
                return "OK", 200

            try:
                numeros_encontrados = re.findall(r'\d+', comando)
                if numeros_encontrados:
                    num_ganador = str(int(numeros_encontrados[0]))
                    
                    if num_ganador in rifa:
                        info_ganador = rifa[num_ganador]
                        
                        if info_ganador["estado"] == "ocupado":
                            nombre_ganador = info_ganador["nombre"]
                            telefono_ganador = info_ganador["telefono"].replace("+", "").strip()
                            chat_privado_ganador = f"{telefono_ganador}@c.us"
                            
                            grupo_destino = chat_id_actual if "@g.us" in chat_id_actual else GRUPO_CHAT_ID_RESPALDO
                            
                            data_rifa["estado_rifa"] = "finalizada"
                            guardar_data_completa(data_rifa)
                            
                            texto_grupo = (
                                f"🎉🎉 *¡TENEMOS UN GANADOR EN LA RIFA!* 🎉🎉\n\n"
                                f"El número premiado en el tiro de la Florida fue el *{num_ganador.zfill(2)}*.\n\n"
                                f"🥇 *¡Felicidades {nombre_ganador}!* (+{telefono_ganador}) Eres el ganador de los *400 reales* 💵✨.\n\n"
                                f"🔒 *La lista ha sido cerrada de forma definitiva.*"
                            )
                            enviar_mensaje_whapi(grupo_destino, texto_grupo)
                            
                            texto_privado = (
                                f"¡Hola {nombre_ganador}! 👋\n\n"
                                f"🎉 *¡MUCHAS FELICIDADES!* 🎉\n\n"
                                f"Tu número *{num_ganador.zfill(2)}* salió premiado en el resultado de la Florida y has ganado los *400 reales* de la rifa. 🏆💵\n\n"
                                f"👉 Por favor, ponte en contacto con el administrador lo antes posible para coordinar tu pago."
                            )
                            enviar_mensaje_whapi(chat_privado_ganador, texto_privado)
                        else:
                            respuesta = f"🎫 El número *{num_ganador.zfill(2)}* salió premiado en la Florida, pero lamentablemente quedó *Disponible*.\n\n🔒 La rifa se ha dado por finalizada."
                            data_rifa["estado_rifa"] = "finalizada"
                            guardar_data_completa(data_rifa)
                    else:
                        respuesta = "⚠️ El número ingresado no está en el rango correcto (1 al 100)."
                else:
                    respuesta = "⚠️ Por favor, escribe el número ganador al final de la frase."
            except Exception as e_ganador:
                print(f"🔴 Error interno procesando ganador: {e_ganador}")

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

        # 🛒 PROCESO DE RESERVAS DE NÚMEROS (CON VERIFICACIÓN Y PENDIENTES)
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

                # Si intentó pedir números que ya están ocupados o en proceso
                mensajes_conflicto = []
                if ocupados:
                    mensajes_conflicto.append(f"🔴 El/los número(s) {', '.join(ocupados)} ya está(n) *OCUPADO(S)* por otro participante.")
                if pendientes:
                    mensajes_conflicto.append(f"🟡 El/los número(s) {', '.join(pendientes)} ya fue(ron) solicitado(s) por alguien más y está(n) *EN PROCESO DE VERIFICACIÓN DE PAGO*.")
                if invalidos:
                    mensajes_conflicto.append(f"⚠️ El/los número(s) {', '.join(invalidos)} está(n) fuera del rango (1 al 100).")

                if mensajes_conflicto and not validos_para_reservar:
                    # Responder directamente avisando por qué no se pudo
                    respuesta = f"Hola {nombre_usuario}:\n" + "\n".join(mensajes_conflicto)
                    enviar_mensaje_whapi(chat_id_actual, respuesta)
                    return "OK", 200

                # Si tiene números válidos para reservar
                if validos_para_reservar:
                    # Crear ID único corto de solicitud (ej: R102)
                    req_id = "R" + str(uuid.uuid4().int)[:4]

                    # Marcar temporalmente como pendiente
                    for n in validos_para_reservar:
                        rifa[n]["estado"] = "pendiente"
                        rifa[n]["solicitud_id"] = req_id

                    # Guardar solicitud en la cola del admin
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
                        f"⏳ *SOLICITUD EN PROCESO* ⏳\n\n"
                        f"Hola {nombre_usuario}, hemos recibido tu pedido para el/los número(s): *{nums_solicitados_txt}*.\n\n"
                        f"🟡 Quedan *reservados temporalmente* mientras el administrador verifica tu transferencia. Te avisaremos por aquí tan pronto sea confirmado."
                    )
                    if mensajes_conflicto:
                        txt_grupo += "\n\n📌 *Nota:* " + " ".join(mensajes_conflicto)

                    enviar_mensaje_whapi(chat_id_actual, txt_grupo)

                    # 2. Notificar en privado al Administrador
                    admin_chat_id = f"{NUMERO_ADMIN_SEGURO}@c.us"
                    # Si el número seguro son 8 dígitos, reconstruimos con 55119
                    if len(NUMERO_ADMIN_SEGURO) == 8:
                        admin_chat_id = f"55119{NUMERO_ADMIN_SEGURO}@c.us"

                    txt_admin = (
                        f"📥 *NUEVA SOLICITUD DE COMPRA* (ID: `{req_id}`)\n\n"
                        f"👤 *Cliente:* {nombre_usuario}\n"
                        f"📱 *Teléfono:* wa.me/{numero_persona}\n"
                        f"🎟️ *Números:* *{nums_solicitados_txt}*\n\n"
                        f"-----------------------------------\n"
                        f"👉 Para APROBAR responde:\n`confirmar {req_id}`\n\n"
                        f"👉 Para RECHAZAR responde:\n`rechazar {req_id}`"
                    )
                    enviar_mensaje_whapi(admin_chat_id, txt_admin)
                    return "OK", 200

        if respuesta:
            enviar_mensaje_whapi(chat_id_actual, respuesta)

    except Exception as e_global:
        print(f"💥 ERROR CRÍTICO CRASH EVITADO: {e_global}")

    return "OK", 200

if __name__ == "__main__":
    inicializar_rifa()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
