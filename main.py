import os
import json
import uuid
import re
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

EVOLUTION_API_URL = "https://mi-whatsapp-api-pobo.onrender.com"
EVOLUTION_API_KEY = "55725d7c0b0fb17cb5e6564edac38c1f"
INSTANCE_NAME = "mi-bot"
ADMIN_PHONE = "5511948824359"
BOT_PHONE = "5562993984530"
PORT = int(os.environ.get("PORT", 10000))
DB_FILE = "rifa_db.json"

PRECIO_1_NUMERO = 10.0
PRECIO_2_NUMEROS = 18.0
PRECIO_3_NUMEROS = 25.0
PRECIO_4_NUMEROS = 32.0
PRECIO_5_NUMEROS = 40.0


def inicializar_rifa():
    try:
        if not os.path.exists(DB_FILE):
            data_inicial = {
                "estado_rifa": "activa",
                "numeros": {
                    str(i): {
                        "estado": "disponible",
                        "nombre": "",
                        "user_id": "",
                        "jid_completo": "",
                        "telefono_real": ""
                    }
                    for i in range(1, 101)
                },
                "solicitudes_pendientes": {},
                "usuarios_bloqueados": []
            }
            guardar_data_completa(data_inicial)
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
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        data.setdefault("estado_rifa", "activa")
        data.setdefault("solicitudes_pendientes", {})
        data.setdefault("usuarios_bloqueados", [])
        data.setdefault("numeros", {})

        for i in range(1, 101):
            n = str(i)
            data["numeros"].setdefault(n, {
                "estado": "disponible",
                "nombre": "",
                "user_id": "",
                "jid_completo": "",
                "telefono_real": ""
            })
            data["numeros"][n].setdefault("telefono_real", "")

        return data
    except Exception as e:
        print(f"Error leyendo base de datos: {e}")
        borrar_y_recrear_base_datos()
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)


def guardar_data_completa(data):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Error al guardar JSON: {e}")


def enviar_whatsapp(numero, texto, mencion_jid=None):
    """Envía texto a Evolution con timeout para que un fallo de la API no deje bloqueado el webhook."""
    url = f"{EVOLUTION_API_URL}/message/sendText/{INSTANCE_NAME}"
    headers = {
        "apikey": EVOLUTION_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "number": str(numero).strip(),
        "text": texto
    }

    if mencion_jid:
        if isinstance(mencion_jid, list):
            payload["mentioned"] = [
                m if "@" in str(m) else f"{m}@s.whatsapp.net"
                for m in mencion_jid
                if m
            ]
        else:
            m = str(mencion_jid).strip()
            payload["mentioned"] = [m if "@" in m else f"{m}@s.whatsapp.net"]

    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=15
        )
        try:
            return response.json()
        except ValueError:
            return {"status_code": response.status_code, "text": response.text}
    except requests.RequestException as e:
        print(f"Error enviando WhatsApp a {numero}: {e}")
        return None


def limpiar_jid(jid):
    if not jid:
        return ""
    return str(jid).split("@")[0].split(":")[0]


def es_lid(jid):
    return bool(jid) and "@lid" in str(jid)


def formatear_telefono(telefono):
    """Devuelve el teléfono con + y código de país, sin espacios ni caracteres extra."""
    if not telefono:
        return ""
    telefono = str(telefono).strip()
    telefono = re.sub(r"[^0-9+]", "", telefono)
    if telefono.startswith("00"):
        telefono = "+" + telefono[2:]
    elif not telefono.startswith("+"):
        telefono = "+" + telefono
    return telefono


def obtener_identificacion_usuario(msg_data, remote_jid, is_group):
    """Obtiene JID para menciones y, cuando Evolution lo proporciona, el teléfono real."""
    key_data = msg_data.get("key", {}) or {}
    candidatos = []

    if is_group:
        candidatos += [
            msg_data.get("participant", ""),
            msg_data.get("participantAlt", ""),
            key_data.get("participant", ""),
            key_data.get("participantAlt", ""),
            key_data.get("senderPn", ""),
            key_data.get("senderLid", "")
        ]
    else:
        candidatos += [
            remote_jid,
            msg_data.get("participant", ""),
            msg_data.get("participantAlt", ""),
            key_data.get("participant", ""),
            key_data.get("participantAlt", ""),
            key_data.get("senderPn", ""),
            key_data.get("senderLid", "")
        ]

    jid_telefono = ""
    for candidato in candidatos:
        if candidato and "@s.whatsapp.net" in str(candidato):
            jid_telefono = str(candidato).strip()
            break

    if not jid_telefono:
        for candidato in candidatos:
            if candidato and "@" in str(candidato) and not es_lid(candidato):
                jid_telefono = str(candidato).strip()
                break

    if jid_telefono:
        telefono_real = limpiar_jid(jid_telefono)
        return jid_telefono, telefono_real, telefono_real

    fallback_jid = next((str(c).strip() for c in candidatos if c), remote_jid)
    return fallback_jid, limpiar_jid(fallback_jid), ""


def texto_usuario(nombre, user_id, telefono_real=""):
    """Solo devuelve el nombre de la mención; el teléfono se muestra en una línea separada."""
    # Para que WhatsApp convierta la mención en interactiva, el texto usa el ID
    # que corresponde al JID incluido en 'mentioned'. WhatsApp puede mostrar
    # el nombre guardado/perfil del contacto al renderizar la mención.
    if user_id:
        return f"@{user_id}"
    nombre_limpio = str(nombre or "Usuario").strip().lstrip("@")
    return f"@{nombre_limpio}"


def calcular_total_promocion(cantidad):
    if cantidad <= 0:
        return 0.0, "Sin números"
    if cantidad == 1:
        return PRECIO_1_NUMERO, "Precio estándar (1 número)"
    if cantidad == 2:
        return PRECIO_2_NUMEROS, "¡Promoción aplicada por 2 números!"
    if cantidad == 3:
        return PRECIO_3_NUMEROS, "¡Promoción aplicada por 3 números!"
    if cantidad == 4:
        return PRECIO_4_NUMEROS, "¡Promoción aplicada por 4 números!"
    if cantidad == 5:
        return PRECIO_5_NUMEROS, "¡Promoción aplicada por 5 números (Súper Paquete)!"
    adicionales = cantidad - 5
    return (
        PRECIO_5_NUMEROS + adicionales * PRECIO_1_NUMERO,
        f"¡Paquete de 5 + {adicionales} número(s) adicional(es)!"
    )


def generar_texto_lista():
    data = obtener_data_completa()
    rifa = data["numeros"]
    texto = "🎟️ *LISTA OFICIAL DE LA RIFA* 🎟️\n\n"
    disponibles = 0
    menciones_lista = []

    for i in range(1, 101):
        num_str = str(i).zfill(2)
        info = rifa[str(i)]
        estado = info.get("estado", "disponible")

        if estado == "disponible":
            texto += f"🟢 *{num_str}*: Disponible\n"
            disponibles += 1
            continue

        user_id = info.get("user_id", "")
        jid_completo = info.get("jid_completo", "")
        telefono_real = info.get("telefono_real", "")
        usuario_visible = texto_usuario(
            info.get("nombre", "Usuario"), user_id, telefono_real
        )

        if estado == "pendiente":
            if user_id and jid_completo:
                texto += f"🟡 *{num_str}*: En verificación de pago {usuario_visible}...\n"
                menciones_lista.append(jid_completo)
            else:
                texto += f"🟡 *{num_str}*: En verificación de pago...\n"
        else:
            if user_id and jid_completo:
                texto += f"🔴 *{num_str}*: Ocupado por {usuario_visible}\n"
                menciones_lista.append(jid_completo)
            else:
                texto += f"🔴 *{num_str}*: Ocupado por {info.get('nombre', 'Usuario')}\n"

    texto += f"\n📊 *Resumen:* Quedan {disponibles} números disponibles."
    if data.get("estado_rifa") == "finalizada":
        texto += "\n\n🔒 *ESTADO:* RIFA cerrada/finalizada."
    return texto, menciones_lista


@app.route("/", methods=["GET"])
def index():
    return "Bot de LA RIFA para WhatsApp Activo y en Línea 24/7!", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error"}), 400

    try:
        if data.get("event") != "messages.upsert":
            return jsonify({"status": "ignored"}), 200

        msg_data = data.get("data", {}) or {}
        if msg_data.get("key", {}).get("fromMe", False):
            return jsonify({"status": "ignored"}), 200

        remote_jid = msg_data.get("key", {}).get("remoteJid", "")
        is_group = "@g.us" in remote_jid
        sender_full_jid, sender_id, telefono_real = obtener_identificacion_usuario(
            msg_data, remote_jid, is_group
        )

        message_content = msg_data.get("message", {}) or {}
        mensaje_texto = ""
        if "conversation" in message_content:
            mensaje_texto = message_content.get("conversation", "")
        elif "extendedTextMessage" in message_content:
            mensaje_texto = message_content.get("extendedTextMessage", {}).get("text", "")

        if not mensaje_texto:
            return jsonify({"status": "no_text"}), 200

        mensaje_texto = " ".join(str(mensaje_texto).strip().split())
        comando = mensaje_texto.lower()
        push_name = msg_data.get("pushName", "Usuario") or "Usuario"

        data_rifa = obtener_data_completa()
        rifa = data_rifa["numeros"]
        solicitudes = data_rifa.get("solicitudes_pendientes", {})
        bloqueados = data_rifa.get("usuarios_bloqueados", [])
        estado_actual_rifa = data_rifa.get("estado_rifa", "activa")

        if sender_id in bloqueados and sender_id != ADMIN_PHONE:
            return jsonify({"status": "blocked"}), 200

        # ====================================================
        # COMANDOS DE ADMINISTRADOR
        # ====================================================
        if sender_id == ADMIN_PHONE:
            if comando.startswith("/reset"):
                borrar_y_recrear_base_datos()
                texto_lista, _ = generar_texto_lista()
                enviar_whatsapp(
                    sender_id,
                    "🔄 *¡LA RIFA ha sido reseteado con éxito!* "
                    "Todos los números vuelven a estar disponibles.\n\n" + texto_lista
                )
                return jsonify({"status": "success"}), 200

            elif comando.startswith("/ganador"):
                partes_cmd = comando.split()
                if len(partes_cmd) < 2:
                    enviar_whatsapp(sender_id, "⚠️ Por favor indica el número ganador. Ejemplo: `/ganador 14`")
                    return jsonify({"status": "success"}), 200

                num_ingresado = partes_cmd[1].strip()
                if not num_ingresado.isdigit() or not 1 <= int(num_ingresado) <= 100:
                    enviar_whatsapp(sender_id, "⚠️ El número debe estar entre 1 y 100.")
                    return jsonify({"status": "success"}), 200

                num_str = str(int(num_ingresado))
                info_num = rifa.get(num_str, {})
                if info_num.get("estado") != "ocupado":
                    enviar_whatsapp(sender_id, f"⚠️ El número *{num_ingresado.zfill(2)}* no está ocupado.")
                    return jsonify({"status": "success"}), 200

                ganador_tel = info_num.get("user_id")
                ganador_jid = info_num.get("jid_completo")
                ganador_telefono = info_num.get("telefono_real", "")
                num_formateado = num_str.zfill(2)
                usuario_ganador = texto_usuario(info_num.get("nombre", "Usuario"), ganador_tel, ganador_telefono)

                msg_anuncio = (
                    "🏆 *¡RESULTADO OFICIAL DE LA RIFA!* 🏆\n\n"
                    f"🎯 El Resultado de la Florida Pick 3 es el: *{num_formateado}*\n\n"
                    f"🎉 ¡El usuario {usuario_ganador} es el ganador de este número! Muchas felicidades. 🥳"
                )
                enviar_whatsapp(remote_jid, msg_anuncio, mencion_jid=ganador_jid)

                if ganador_jid:
                    enviar_whatsapp(
                        ganador_tel,
                        f"🎉 *¡FELICIDADES!* 🎉\n\n"
                        f"¡Has ganado LA RIFA con tu número *{num_formateado}*! 🏆\n\n"
                        "Por favor, ponte en contacto con la administración para recibir tu premio. 🤝"
                    )
                return jsonify({"status": "success"}), 200

            elif comando.startswith("/liberar"):
                partes_cmd = comando.split()
                if len(partes_cmd) > 1 and partes_cmd[1].isdigit() and 1 <= int(partes_cmd[1]) <= 100:
                    n_str = str(int(partes_cmd[1]))
                    rifa[n_str] = {
                        "estado": "disponible", "nombre": "", "user_id": "",
                        "jid_completo": "", "telefono_real": ""
                    }
                    data_rifa["numeros"] = rifa
                    guardar_data_completa(data_rifa)
                    enviar_whatsapp(sender_id, f"🟢 El número {n_str.zfill(2)} ha sido liberado.")
                return jsonify({"status": "success"}), 200

            elif comando.startswith("conf_") or comando.startswith("rech_"):
                partes_cb = comando.split("_", 1)
                accion = partes_cb[0]
                req_id = partes_cb[1] if len(partes_cb) > 1 else ""

                if req_id in solicitudes:
                    sol = solicitudes[req_id]
                    user_nombre = sol.get("nombre", "Usuario")
                    user_tel = sol.get("user_id", "")
                    user_nums = sol.get("numeros", [])
                    chat_origen = sol.get("chat_origen", "")
                    jid_completo = sol.get("jid_completo", "")
                    telefono_real = sol.get("telefono_real", "")
                    nums_formatted = ", ".join(n.zfill(2) for n in user_nums)
                    usuario_visible = texto_usuario(user_nombre, user_tel, telefono_real)
                    telefono_mostrado = formatear_telefono(telefono_real)

                    if accion == "conf":
                        for n in user_nums:
                            rifa[n].update({
                                "estado": "ocupado",
                                "nombre": user_nombre,
                                "user_id": user_tel,
                                "jid_completo": jid_completo,
                                "telefono_real": telefono_real
                            })

                        del solicitudes[req_id]
                        data_rifa["numeros"] = rifa
                        data_rifa["solicitudes_pendientes"] = solicitudes

                        if all(rifa[str(n)]["estado"] == "ocupado" for n in range(1, 101)):
                            data_rifa["estado_rifa"] = "finalizada"

                        guardar_data_completa(data_rifa)
                        enviar_whatsapp(sender_id, f"✅ *Aprobado.* Números: {nums_formatted}")

                        texto_pago_confirmado = (
                            f"🎉 *¡Hola {usuario_visible}!* 🎉\n\n"
                            f"Tu pago fue verificado. Tus números *({nums_formatted})* ya están registrados a tu nombre."
                        )
                        if telefono_mostrado:
                            texto_pago_confirmado += f"\n\n📱 *Teléfono:* {telefono_mostrado}"

                        enviar_whatsapp(user_tel, texto_pago_confirmado, mencion_jid=jid_completo)
                        if chat_origen != user_tel:
                            enviar_whatsapp(chat_origen, texto_pago_confirmado, mencion_jid=jid_completo)

                    elif accion == "rech":
                        for n in user_nums:
                            rifa[n] = {
                                "estado": "disponible", "nombre": "", "user_id": "",
                                "jid_completo": "", "telefono_real": ""
                            }

                        del solicitudes[req_id]
                        data_rifa["numeros"] = rifa
                        data_rifa["solicitudes_pendientes"] = solicitudes
                        guardar_data_completa(data_rifa)
                        enviar_whatsapp(sender_id, f"❌ *Rechazado el ID {req_id}.*")

                        texto_rechazo = (
                            f"❌ Lo sentimos {usuario_visible}, tu solicitud para los números "
                            f"*{nums_formatted}* fue rechazada. Los números vuelven a estar disponibles."
                        )
                        if telefono_mostrado:
                            texto_rechazo += f"\n\n📱 *Teléfono:* {telefono_mostrado}"

                        enviar_whatsapp(user_tel, texto_rechazo, mencion_jid=jid_completo)
                        if chat_origen != user_tel:
                            enviar_whatsapp(chat_origen, texto_rechazo, mencion_jid=jid_completo)

                return jsonify({"status": "success"}), 200

        # ====================================================
        # COMANDOS GENERALES
        # ====================================================
        if comando in ("lista", "listas", "/lista", "/listas"):
            print(f"LISTA recibida desde {remote_jid}")
            texto_lista, menciones_lista = generar_texto_lista()
            respuesta = f"¡Hola {push_name}! Estado actual de LA RIFA:\n\n{texto_lista}"
            if estado_actual_rifa == "activa":
                respuesta += "\n\n👉 *¿Cómo comprar?* Envía los números que deseas separados por coma (ej: *7, 14*)."

            resultado = enviar_whatsapp(
                remote_jid,
                respuesta,
                mencion_jid=menciones_lista if menciones_lista else None
            )
            print(f"LISTA enviada: {resultado}")
            return jsonify({"status": "success"}), 200

        elif comando == "/reglas":
            texto_reglas = (
                "📌 *Reglas de LA RIFA:*\n"
                "1. Escribe `lista` para ver los números disponibles (del 01 al 100).\n"
                "2. Envía los números que deseas separados por comas (ejemplo: `7, 14`).\n"
                "3. Revisa el total calculado con promoción y haz tu transferencia.\n"
                "4. El ganador se define mediante la Lotería de Florida."
            )
            enviar_whatsapp(remote_jid, texto_reglas)
            return jsonify({"status": "success"}), 200

        # ====================================================
        # PROCESAMIENTO DE NÚMEROS
        # ====================================================
        partes = [p.strip() for p in mensaje_texto.replace(" ", "").split(",") if p.strip()]
        es_lista_numeros = all(p.isdigit() for p in partes) if partes else False

        if es_lista_numeros:
            if estado_actual_rifa == "finalizada":
                enviar_whatsapp(remote_jid, "🔒 *Lo sentimos, el sistema está cerrado.*")
                return jsonify({"status": "success"}), 200

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

            mensajes_conflicto = []
            if ocupados:
                mensajes_conflicto.append(f"🔴 El/los número(s) {', '.join(ocupados)} ya está(n) *OCUPADO(S)*.")
            if pendientes:
                mensajes_conflicto.append(f"🟡 El/los número(s) {', '.join(pendientes)} está(n) *EN PROCESO DE VERIFICACIÓN*.")
            if invalidos:
                mensajes_conflicto.append(f"⚠️ El/los número(s) {', '.join(invalidos)} está(n) fuera del rango (1 al 100).")

            if mensajes_conflicto and not validos_para_reservar:
                enviar_whatsapp(remote_jid, f"Hola {push_name}:\n" + "\n".join(mensajes_conflicto))
                return jsonify({"status": "success"}), 200

            if validos_para_reservar:
                req_id = "r" + str(uuid.uuid4().int)[:4]

                for n in validos_para_reservar:
                    rifa[n].update({
                        "estado": "pendiente",
                        "nombre": push_name,
                        "user_id": sender_id,
                        "jid_completo": sender_full_jid,
                        "telefono_real": telefono_real
                    })

                solicitudes[req_id] = {
                    "nombre": push_name,
                    "user_id": sender_id,
                    "jid_completo": sender_full_jid,
                    "telefono_real": telefono_real,
                    "numeros": validos_para_reservar,
                    "chat_origen": remote_jid
                }

                data_rifa["numeros"] = rifa
                data_rifa["solicitudes_pendientes"] = solicitudes
                guardar_data_completa(data_rifa)

                nums_solicitados_txt = ", ".join(n.zfill(2) for n in validos_para_reservar)
                cantidad_nums = len(validos_para_reservar)
                total_a_pagar, promo_txt = calcular_total_promocion(cantidad_nums)
                usuario_cliente = texto_usuario(push_name, sender_id, telefono_real)
                telefono_mostrado = formatear_telefono(telefono_real)

                msg_cliente = (
                    f"⏳ *SOLICITUD RECIBIDA* ⏳\n\n"
                    f"Hola {usuario_cliente}, recibimos tu pedido para el/los número(s): *{nums_solicitados_txt}*."
                )
                if telefono_mostrado:
                    msg_cliente += f"\n\n📱 *Teléfono:* {telefono_mostrado}"
                msg_cliente += f"\n\n💰 *Total a transferir:* ${total_a_pagar:.2f}\n"
                if promo_txt:
                    msg_cliente += f"🔥 *Promoción:* {promo_txt}\n"
                msg_cliente += "\n🟡 Quedan *reservados temporalmente* mientras el administrador verifica tu pago."

                enviar_whatsapp(remote_jid, msg_cliente, mencion_jid=sender_full_jid)

                link_aprobar = f"https://wa.me/{BOT_PHONE}?text=conf_{req_id}"
                link_rechazar = f"https://wa.me/{BOT_PHONE}?text=rech_{req_id}"
                cliente_admin = texto_usuario(push_name, sender_id, telefono_real)

                txt_admin = (
                    f"📥 *NUEVA SOLICITUD DE COMPRA* (ID: `{req_id}`)\n\n"
                    f"👤 *Cliente:* {cliente_admin}\n"
                )
                if telefono_mostrado:
                    txt_admin += f"📱 *Teléfono real:* {telefono_mostrado}\n"
                txt_admin += (
                    f"🎟️ *Números:* *{nums_solicitados_txt}* ({cantidad_nums} nums)\n"
                    f"💰 *Total Calculado:* ${total_a_pagar:.2f}\n\n"
                    "Haz clic para gestionar:\n"
                    f"👉 *APROBAR:* {link_aprobar}\n\n"
                    f"👉 *RECHAZAR:* {link_rechazar}"
                )

                enviar_whatsapp(ADMIN_PHONE, txt_admin, mencion_jid=sender_full_jid)

            return jsonify({"status": "success"}), 200

        return jsonify({"status": "ignored_text"}), 200

    except Exception as e:
        print(f"Error procesando webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    inicializar_rifa()
    app.run(host="0.0.0.0", port=PORT)
