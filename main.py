import os
import json
import requests
import re
import uuid
from flask import Flask, request, jsonify

app = Flask(__name__)

# -------------------------------------------------------------
# ⚙️ CONFIGURACIÓN DE NÚMEROS Y ROLES
# -------------------------------------------------------------
BOT_ASISTENTE_PHONE = "5353215119"      # Bot Encargado (+5353215119)
WHATSAPP_ADMIN_PHONE = "5511948824359"  # Tu WhatsApp Personal (+5511948824359)
NUMERO_ADMIN_SEGURO = "48824359"       # Filtro de tus últimos dígitos

GRUPO_CHAT_ID_RESPALDO = "DyI3ISDPZjyKw3w0cD8elC@g.us"
CLAVE_RESET = "admin.resetear.rifa.99"
DB_FILE = "rifa_db.json"

# -------------------------------------------------------------
# 🔑 CREDENCIALES DE LA API DEL BOT CUBANO (+5353215119)
# -------------------------------------------------------------
# ⚠️ Reemplaza la URL y el Token con los datos de la instancia del +5353215119
API_BOT_CUBANO_URL = "https://tu-api-de-whatsapp.com/v1/messages"
API_BOT_CUBANO_TOKEN = "TOKEN_DE_TU_INSTANCIA_5353215119"

# 1. Función para enviar mensajes generales (Atención al grupo / respuestas)
def enviar_mensaje_whatsapp(destino, texto):
    """
    Envío de mensajes general hacia el grupo o clientes.
    """
    print(f"Out [ENVIANDO A {destino}]:\n{texto}\n{'-'*30}")
    # Adapta esta llamada POST según los parámetros que exige tu API
    # payload = {"to": destino, "body": texto}
    # headers = {"Authorization": f"Bearer {API_BOT_CUBANO_TOKEN}"}
    # requests.post(API_BOT_CUBANO_URL, json=payload, headers=headers)
    return True

# 2. Función EXCLUSIVA para notificar a tu chat privado desde el +5353215119
def enviar_mensaje_desde_bot_cubano(destino_admin, texto):
    """
    Envía las solicitudes directamente desde la sesión del +5353215119 hacia tu teléfono.
    Al ser un número externo, tu teléfono reproducirá el sonido de notificación.
    """
    print(f"🔔 [NOTIFICACIÓN PRIVADA DESDE +5353215119 A {destino_admin}]:\n{texto}\n{'-'*30}")
    
    payload = {
        "to": destino_admin,    # O "number" / "chat_id" según tu proveedor
        "body": texto           # O "text" / "message"
    }
    headers = {
        "Authorization": f"Bearer {API_BOT_CUBANO_TOKEN}",
        "Content-Type": "application/json"
    }
    try:
        r = requests.post(API_BOT_CUBANO_URL, json=payload, headers=headers)
        return r.status_code in [200, 201]
    except Exception as e:
        print(f"🔴 Error enviando notificación privada desde el bot cubano: {e}")
        return False

# -------------------------------------------------------------
# 💾 GESTIÓN DE BASE DE DATOS LOCAL
# -------------------------------------------------------------
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
            link = info.get("enlace", "")
            if link:
                texto += f"🔴 *{num_str}*: Ocupado por {info['nombre']} 👉 {link}\n"
            else:
                texto += f"🔴 *{num_str}*: Ocupado por {info['nombre']}\n"
            
    texto += f"\n📊 *Resumen:* Quedan {disponibles} números disponibles."
    if data.get("estado_rifa") == "finalizada":
        texto += "\n\n🔒 *ESTADO:* Rifa cerrada/finalizada."
    return texto

# -------------------------------------------------------------
# 🌐 WEBHOOK PRINCIPAL
# -------------------------------------------------------------
@app.route("/", methods=["GET"])
def home():
    return "Servidor Rifa Activo.", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data_webhook = request.get_json(force=True, silent=True) or {}

        # 1. Extraer mensaje y datos según la estructura de tu payload
        mensaje_texto = data_webhook.get("body", "") or data_webhook.get("message", "") or ""
        chat_id_actual = data_webhook.get("chat_id", "") or data_webhook.get("from", "")
        
        comando = mensaje_texto.strip().lower()

        if not comando:
            return "No text", 200

        # Prevenir bucles de auto-respuesta
        if "lista oficial de la rifa" in comando or "solicitud recibida" in comando or "pago confirmado" in comando:
            return "Ignored loop", 200

        numero_persona = re.sub(r'\D', '', chat_id_actual.split("@")[0])
        nombre_usuario = data_webhook.get("from_name", f"+{numero_persona}")

        data_rifa = obtener_data_completa()
        rifa = data_rifa["numeros"]
        solicitudes = data_rifa.get("solicitudes_pendientes", {})
        
        # Filtro de Seguridad Máster (Sólo tú +5511948824359 apruebas o rechazas)
        es_admin_general = (NUMERO_ADMIN_SEGURO in numero_persona) or (WHATSAPP_ADMIN_PHONE in numero_persona)

        # -----------------------------------------------------
        # COMANDO: RESETEAR RIFA
        # -----------------------------------------------------
        if comando == CLAVE_RESET:
            if not es_admin_general:
                return "OK", 200
            borrar_y_recrear_base_datos()
            respuesta = "🔄 *¡Rifa reseteada!* Todos los números están disponibles.\n\n" + generar_texto_lista()
            enviar_mensaje_whatsapp(chat_id_actual, respuesta)
            return "OK", 200

        # -----------------------------------------------------
        # COMANDO: CONFIRMAR / RECHAZAR SOLICITUD
        # -----------------------------------------------------
        elif comando.startswith("confirmar ") or comando.startswith("rechazar "):
            if not es_admin_general:
                print(f"⛔ DENEGADO: El número {numero_persona} no es el Administrador General.")
                return "OK", 200
            
            partes_cmd = mensaje_texto.strip().split()
            accion = partes_cmd[0].lower()
            req_id_input = partes_cmd[1].strip() if len(partes_cmd) > 1 else ""

            # Búsqueda flexible de ID (insensible a mayúsculas/minúsculas)
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

                    if all(rifa[str(n)]["estado"] == "ocupado" for n in range(1, 101)):
                        data_rifa["estado_rifa"] = "finalizada"

                    guardar_data_completa(data_rifa)

                    # Respuesta de confirmación a tu chat
                    enviar_mensaje_whatsapp(chat_id_actual, f"✅ *Solicitud {req_id_encontrado} APROBADA.* Números ({nums_formatted}) asignados a {user_nombre}.")

                    # Notificación al grupo de la rifa marcando los números como OCUPADOS
                    msg_grupo = f"🎉 *¡PAGO CONFIRMADO!* 🎉\n\n👤 *Usuario:* {user_nombre}\n🎟️ *Números asignados:* {nums_formatted}\n\n¡Gracias por tu compra! 🤝\n\n" + generar_texto_lista()
                    enviar_mensaje_whatsapp(grupo_origen, msg_grupo)

                elif accion == "rechazar":
                    for n in user_nums:
                        rifa[n] = {"estado": "disponible", "nombre": "", "telefono": "", "enlace": "", "solicitud_id": ""}

                    del solicitudes[req_id_encontrado]
                    data_rifa["numeros"] = rifa
                    data_rifa["solicitudes_pendientes"] = solicitudes
                    guardar_data_completa(data_rifa)

                    enviar_mensaje_whatsapp(chat_id_actual, f"❌ *Solicitud {req_id_encontrado} RECHAZADA.* Números ({nums_formatted}) liberados.")

                    msg_grupo = f"⚠️ *SOLICITUD CANCELADA* ⚠️\n\nHola {user_nombre}, la solicitud para los números *{nums_formatted}* fue rechazada. Vuelven a estar 🟢 *Disponibles*."
                    enviar_mensaje_whatsapp(grupo_origen, msg_grupo)

            else:
                enviar_mensaje_whatsapp(chat_id_actual, f"⚠️ No se encontró la solicitud ID: `{req_id_input}` o ya fue procesada.")
            
            return "OK", 200

        # -----------------------------------------------------
        # INTENTO DE COMPRA DE NÚMEROS (Ejemplo: "7" o "7, 14, 25")
        # -----------------------------------------------------
        partes = [p.strip() for p in mensaje_texto.split(",")]
        es_lista_numeros = all(p.isdigit() for p in partes) if partes and mensaje_texto else False

        if es_lista_numeros:
            validos_para_reservar = []
            for p in partes:
                num_elegido = int(p)
                if 1 <= num_elegido <= 100:
                    num_str = str(num_elegido)
                    if rifa[num_str]["estado"] == "disponible":
                        validos_para_reservar.append(num_str)

            if validos_para_reservar:
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

                nums_txt = ", ".join([n.zfill(2) for n in validos_para_reservar])

                # 1. Notificación enviada al grupo
                enviar_mensaje_whatsapp(chat_id_actual, f"⏳ *SOLICITUD RECIBIDA*\n\nHola {nombre_usuario}, tus números *{nums_txt}* quedan en 🟡 *Verificación de Pago*.")

                # 2. Enlaces apuntando directamente al chat del Bot Cubano (+5353215119)
                link_confirmar = f"wa.me/{BOT_ASISTENTE_PHONE}?text=confirmar%20{req_id}"
                link_rechazar = f"wa.me/{BOT_ASISTENTE_PHONE}?text=rechazar%20{req_id}"

                txt_admin = (
                    f"📥 *NUEVA COMPRA* (ID: `{req_id}`)\n\n"
                    f"👤 *Cliente:* {nombre_usuario}\n"
                    f"📱 *Tel:* wa.me/{numero_persona}\n"
                    f"🎟️ *Números:* *{nums_txt}*\n\n"
                    f"-----------------------------------\n"
                    f"🟢 *CONFIRMAR:* {link_confirmar}\n\n"
                    f"🔴 *RECHAZAR:* {link_rechazar}"
                )
                
                # 📌 ENVÍO DESDE LA INSTANCIA DE CUBANO HACIA TU WHATSAPP PERSONAL
                # Esto garantiza que lo recibas como mensaje privado y suene la alerta.
                enviar_mensaje_desde_bot_cubano(f"{WHATSAPP_ADMIN_PHONE}@s.whatsapp.net", txt_admin)
                return "OK", 200

        # -----------------------------------------------------
        # RESPUESTA GENERAL / LISTA
        # -----------------------------------------------------
        respuesta = (
            f"¡Hola {nombre_usuario}! Aquí tienes el estado actualizado de la Rifa. ✨\n\n"
            f"💵 *Compra tus números por 10 reales y gana 400 reales.*\n"
            f"🏆 Premio entregado por PIX en Brasil o en CUP en Cuba.\n\n"
            f"{generar_texto_lista()}\n\n"
            f"👉 *¿Cómo comprar?* Responde en este chat escribiendo los números que deseas (ejemplo: *7, 14, 25*)."
        )
        enviar_mensaje_whatsapp(chat_id_actual, respuesta)

    except Exception as e:
        print(f"💥 Error crítico en webhook: {e}")

    return "OK", 200

if __name__ == "__main__":
    inicializar_rifa()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
