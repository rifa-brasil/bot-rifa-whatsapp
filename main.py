import os
import json
import uuid
import requests
from flask import Flask, request, jsonify

# --- CONFIGURACIÓN DE FLASK PARA RENDER ---
app = Flask(__name__)

# --- TUS DATOS CONFIGURADOS ---
EVOLUTION_API_URL = "https://mi-whatsapp-api-pobo.onrender.com"
EVOLUTION_API_KEY = "55725d7c0b0fb17cb5e6564edac38c1f"
INSTANCE_NAME = "mi-bot"

ADMIN_PHONE = "5511948824359"
BOT_PHONE = "5562993984530"

PORT = int(os.environ.get("PORT", 10000))

DB_FILE = "rifa_db.json"


# ============================================================
# PRECIOS Y PROMOCIONES
# ============================================================

PRECIO_1_NUMERO = 10.0
PRECIO_2_NUMEROS = 18.0
PRECIO_3_NUMEROS = 25.0
PRECIO_4_NUMEROS = 32.0
PRECIO_5_NUMEROS = 40.0


# ============================================================
# BASE DE DATOS
# ============================================================

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

            if "estado_rifa" not in data:
                data["estado_rifa"] = "activa"

            if "solicitudes_pendientes" not in data:
                data["solicitudes_pendientes"] = {}

            if "usuarios_bloqueados" not in data:
                data["usuarios_bloqueados"] = []

            # Compatibilidad con números creados por versiones anteriores
            for i in range(1, 101):
                numero = str(i)

                if numero not in data.get("numeros", {}):
                    data.setdefault("numeros", {})[numero] = {
                        "estado": "disponible",
                        "nombre": "",
                        "user_id": "",
                        "jid_completo": "",
                        "telefono_real": ""
                    }

                info = data["numeros"][numero]

                if "telefono_real" not in info:
                    info["telefono_real"] = ""

            return data

    except Exception as e:
        print(f"Error leyendo base de datos: {e}")

        borrar_y_recrear_base_datos()

        with open(DB_FILE, "r") as f:
            return json.load(f)


def guardar_data_completa(data):
    try:
        with open(DB_FILE, "w") as f:
            json.dump(data, f, indent=4)

    except Exception as e:
        print(f"Error al guardar JSON: {e}")


# ============================================================
# ENVÍO DE WHATSAPP
# ============================================================

def enviar_whatsapp(numero, texto, mencion_jid=None):

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
                m if "@" in m else f"{m}@s.whatsapp.net"
                for m in mencion_jid
            ]

        else:

            if "@" not in mencion_jid:
                mencion_jid = f"{mencion_jid}@s.whatsapp.net"

            payload["mentioned"] = [mencion_jid]

    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers
        )

        return response.json()

    except Exception as e:
        print(f"Error enviando WhatsApp a {numero}: {e}")
        return None


# ============================================================
# IDENTIFICACIÓN DEL USUARIO
# ============================================================

def limpiar_jid(jid):
    """
    Devuelve solamente la parte numérica/identificador antes de @.
    """

    if not jid:
        return ""

    return str(jid).split("@")[0].split(":")[0]


def es_lid(jid):
    """
    Detecta si un JID pertenece al sistema @lid de WhatsApp.
    """

    if not jid:
        return False

    return "@lid" in str(jid)


def obtener_identificacion_usuario(msg_data, remote_jid, is_group):
    """
    Busca el JID telefónico real del participante.

    WhatsApp/Evolution puede entregar actualmente identificadores
    @lid. Por eso NO debemos asumir que cualquier identificador
    antes de @ es un número de teléfono.

    Devuelve:

    sender_full_jid
        JID que usaremos para la mención.

    sender_id
        Identificador principal.

    telefono_real
        Número telefónico real cuando Evolution lo proporciona.
    """

    key_data = msg_data.get("key", {}) or {}

    candidatos = []

    if is_group:

        # Campo tradicional de Evolution
        candidatos.append(msg_data.get("participant", ""))

        # Algunas versiones pueden ponerlo aquí
        candidatos.append(msg_data.get("participantAlt", ""))

        # Campos del key
        candidatos.append(key_data.get("participant", ""))
        candidatos.append(key_data.get("participantAlt", ""))

        # Campos relacionados con addressing/LID
        candidatos.append(key_data.get("senderPn", ""))
        candidatos.append(key_data.get("senderLid", ""))

    else:

        candidatos.append(remote_jid)
        candidatos.append(msg_data.get("participant", ""))
        candidatos.append(msg_data.get("participantAlt", ""))

        candidatos.append(key_data.get("participant", ""))
        candidatos.append(key_data.get("participantAlt", ""))

        candidatos.append(key_data.get("senderPn", ""))
        candidatos.append(key_data.get("senderLid", ""))

    # --------------------------------------------------------
    # PRIMERO BUSCAMOS UN JID REAL @s.whatsapp.net
    # --------------------------------------------------------

    jid_telefono = ""

    for candidato in candidatos:

        if not candidato:
            continue

        candidato = str(candidato).strip()

        if "@s.whatsapp.net" in candidato:

            jid_telefono = candidato
            break

    # --------------------------------------------------------
    # SI NO ENCONTRAMOS @s.whatsapp.net, BUSCAMOS CUALQUIER
    # JID QUE NO SEA @lid
    # --------------------------------------------------------

    if not jid_telefono:

        for candidato in candidatos:

            if not candidato:
                continue

            candidato = str(candidato).strip()

            if "@" in candidato and not es_lid(candidato):

                jid_telefono = candidato
                break

    # --------------------------------------------------------
    # SI ENCONTRAMOS TELÉFONO REAL
    # --------------------------------------------------------

    if jid_telefono:

        telefono_real = limpiar_jid(jid_telefono)

        sender_full_jid = jid_telefono
        sender_id = telefono_real

        return sender_full_jid, sender_id, telefono_real

    # --------------------------------------------------------
    # SI NO HAY TELÉFONO REAL, CONSERVAMOS EL JID DISPONIBLE
    # PARA NO ROMPER LA MENCIÓN.
    # --------------------------------------------------------

    fallback_jid = ""

    for candidato in candidatos:

        if candidato:
            fallback_jid = str(candidato).strip()
            break

    if not fallback_jid:
        fallback_jid = remote_jid

    sender_full_jid = fallback_jid
    sender_id = limpiar_jid(fallback_jid)

    # Si es @lid, NO lo presentamos como teléfono real.
    telefono_real = ""

    return sender_full_jid, sender_id, telefono_real


# ============================================================
# TEXTO PARA MOSTRAR USUARIO + TELÉFONO
# ============================================================

def texto_usuario(nombre, user_id, telefono_real):
    """
    Devuelve una representación visible del usuario.

    Si tenemos teléfono real:

    @usuario (5511999999999)

    Si no tenemos teléfono:

    @usuario

    El @usuario continúa siendo texto para la mención,
    mientras que el teléfono aparece como información adicional.
    """

    nombre_limpio = str(nombre or "Usuario").strip()

    if telefono_real:
        return f"@{user_id} ({telefono_real})"

    if user_id:
        return f"@{user_id}"

    return nombre_limpio


# ============================================================
# PRECIOS
# ============================================================

def calcular_total_promocion(cantidad):

    if cantidad <= 0:
        return 0.0, "Sin números"

    elif cantidad == 1:
        return PRECIO_1_NUMERO, "Precio estándar (1 número)"

    elif cantidad == 2:
        return PRECIO_2_NUMEROS, "¡Promoción aplicada por 2 números!"

    elif cantidad == 3:
        return PRECIO_3_NUMEROS, "¡Promoción aplicada por 3 números!"

    elif cantidad == 4:
        return PRECIO_4_NUMEROS, "¡Promoción aplicada por 4 números!"

    elif cantidad == 5:
        return PRECIO_5_NUMEROS, "¡Promoción aplicada por 5 números (Súper Paquete)!"

    else:

        adicionales = cantidad - 5

        total = PRECIO_5_NUMEROS + (
            adicionales * PRECIO_1_NUMERO
        )

        return total, (
            f"¡Paquete de 5 + {adicionales} número(s) adicional(es)!"
        )


# ============================================================
# GENERAR LISTA
# ============================================================

def generar_texto_lista():

    data = obtener_data_completa()

    rifa = data["numeros"]

    texto = "🎟️ *LISTA OFICIAL DE LA RIFA* 🎟️\n\n"

    disponibles = 0

    menciones_lista = []

    for i in range(1, 101):

        num_str = str(i).zfill(2)

        info = rifa[str(i)]

        estado = info.get(
            "estado",
            "disponible"
        )

        if estado == "disponible":

            texto += (
                f"🟢 *{num_str}*: Disponible\n"
            )

            disponibles += 1

        elif estado == "pendiente":

            user_id = info.get(
                "user_id",
                ""
            )

            jid_completo = info.get(
                "jid_completo",
                ""
            )

            telefono_real = info.get(
                "telefono_real",
                ""
            )

            usuario_visible = texto_usuario(
                info.get("nombre", "Usuario"),
                user_id,
                telefono_real
            )

            if user_id and jid_completo:

                texto += (
                    f"🟡 *{num_str}*: "
                    f"En verificación de pago "
                    f"({usuario_visible})...\n"
                )

                menciones_lista.append(
                    jid_completo
                )

            else:

                texto += (
                    f"🟡 *{num_str}*: "
                    f"En verificación de pago...\n"
                )

        else:

            user_id = info.get(
                "user_id",
                ""
            )

            jid_completo = info.get(
                "jid_completo",
                ""
            )

            telefono_real = info.get(
                "telefono_real",
                ""
            )

            usuario_visible = texto_usuario(
                info.get("nombre", "Usuario"),
                user_id,
                telefono_real
            )

            if user_id and jid_completo:

                texto += (
                    f"🔴 *{num_str}*: "
                    f"Ocupado por {usuario_visible}\n"
                )

                menciones_lista.append(
                    jid_completo
                )

            else:

                nombre = info.get(
                    "nombre",
                    "Usuario"
                )

                texto += (
                    f"🔴 *{num_str}*: "
                    f"Ocupado por {nombre}\n"
                )

    texto += (
        f"\n📊 *Resumen:* "
        f"Quedan {disponibles} números disponibles."
    )

    if data.get("estado_rifa") == "finalizada":

        texto += (
            "\n\n🔒 *ESTADO:* "
            "RIFA cerrada/finalizada."
        )

    return texto, menciones_lista


# ============================================================
# PÁGINA PRINCIPAL
# ============================================================

@app.route("/", methods=["GET"])
def index():

    return (
        "Bot de LA RIFA para WhatsApp "
        "Activo y en Línea 24/7!",
        200
    )


# ============================================================
# WEBHOOK
# ============================================================

@app.route("/webhook", methods=["POST"])
def webhook():

    data = request.get_json()

    if not data:
        return jsonify({
            "status": "error"
        }), 400

    try:

        event = data.get("event")

        if event != "messages.upsert":

            return jsonify({
                "status": "ignored"
            }), 200

        msg_data = data.get(
            "data",
            {}
        )

        # ----------------------------------------------------
        # IGNORAR MENSAJES ENVIADOS POR EL PROPIO BOT
        # ----------------------------------------------------

        if msg_data.get(
            "key",
            {}
        ).get(
            "fromMe",
            False
        ):

            return jsonify({
                "status": "ignored"
            }), 200

        # ----------------------------------------------------
        # CHAT DE ORIGEN
        # ----------------------------------------------------

        remote_jid = msg_data.get(
            "key",
            {}
        ).get(
            "remoteJid",
            ""
        )

        is_group = "@g.us" in remote_jid

        # ----------------------------------------------------
        # OBTENER IDENTIFICACIÓN REAL DEL PARTICIPANTE
        # ----------------------------------------------------

        (
            sender_full_jid,
            sender_id,
            telefono_real
        ) = obtener_identificacion_usuario(
            msg_data,
            remote_jid,
            is_group
        )

        # ----------------------------------------------------
        # TEXTO DEL MENSAJE
        # ----------------------------------------------------

        message_content = msg_data.get(
            "message",
            {}
        )

        mensaje_texto = ""

        if "conversation" in message_content:

            mensaje_texto = message_content[
                "conversation"
            ]

        elif "extendedTextMessage" in message_content:

            mensaje_texto = message_content[
                "extendedTextMessage"
            ].get(
                "text",
                ""
            )

        if not mensaje_texto:

            return jsonify({
                "status": "no_text"
            }), 200

        mensaje_texto = mensaje_texto.strip()

        comando = mensaje_texto.lower()

        push_name = msg_data.get(
            "pushName",
            "Usuario"
        )

        # ----------------------------------------------------
        # DATOS DE LA RIFA
        # ----------------------------------------------------

        data_rifa = obtener_data_completa()

        rifa = data_rifa[
            "numeros"
        ]

        solicitudes = data_rifa.get(
            "solicitudes_pendientes",
            {}
        )

        bloqueados = data_rifa.get(
            "usuarios_bloqueados",
            []
        )

        estado_actual_rifa = data_rifa.get(
            "estado_rifa",
            "activa"
        )

        # ----------------------------------------------------
        # BLOQUEADOS
        # ----------------------------------------------------

        if (
            sender_id in bloqueados
            and sender_id != ADMIN_PHONE
        ):

            return jsonify({
                "status": "blocked"
            }), 200

        # ====================================================
        # COMANDOS DE ADMINISTRADOR
        # ====================================================

        if sender_id == ADMIN_PHONE:

            # ------------------------------------------------
            # RESET
            # ------------------------------------------------

            if comando.startswith("/reset"):

                borrar_y_recrear_base_datos()

                texto_lista, _ = (
                    generar_texto_lista()
                )

                enviar_whatsapp(
                    sender_id,
                    "🔄 *¡LA RIFA ha sido "
                    "reseteado con éxito!* "
                    "Todos los números vuelven "
                    "a estar disponibles.\n\n"
                    + texto_lista
                )

                return jsonify({
                    "status": "success"
                }), 200

            # ------------------------------------------------
            # GANADOR
            # ------------------------------------------------

            elif comando.startswith("/ganador"):

                partes_cmd = comando.split(" ")

                if len(partes_cmd) < 2:

                    enviar_whatsapp(
                        sender_id,
                        "⚠️ Por favor indica el "
                        "número ganador. "
                        "Ejemplo: `/ganador 14`"
                    )

                    return jsonify({
                        "status": "success"
                    }), 200

                num_ingresado = (
                    partes_cmd[1].strip()
                )

                if (
                    not num_ingresado.isdigit()
                    or not (
                        1 <= int(num_ingresado) <= 100
                    )
                ):

                    enviar_whatsapp(
                        sender_id,
                        "⚠️ El número debe "
                        "estar entre 1 y 100."
                    )

                    return jsonify({
                        "status": "success"
                    }), 200

                num_str = str(
                    int(num_ingresado)
                )

                info_num = rifa.get(
                    num_str,
                    {}
                )

                estado = info_num.get(
                    "estado"
                )

                if estado != "ocupado":

                    enviar_whatsapp(
                        sender_id,
                        f"⚠️ El número "
                        f"*{num_ingresado.zfill(2)}* "
                        f"no está ocupado."
                    )

                    return jsonify({
                        "status": "success"
                    }), 200

                ganador_tel = info_num.get(
                    "user_id"
                )

                ganador_jid = info_num.get(
                    "jid_completo"
                )

                ganador_telefono = info_num.get(
                    "telefono_real",
                    ""
                )

                num_formateado = (
                    num_str.zfill(2)
                )

                usuario_ganador = texto_usuario(
                    info_num.get(
                        "nombre",
                        "Usuario"
                    ),
                    ganador_tel,
                    ganador_telefono
                )

                msg_anuncio = (
                    "🏆 *¡RESULTADO OFICIAL "
                    "DE LA RIFA!* 🏆\n\n"
                    f"🎯 El Resultado de la "
                    f"Florida Pick 3 es el: "
                    f"*{num_formateado}*\n\n"
                    f"🎉 ¡El usuario "
                    f"{usuario_ganador} "
                    f"es el ganador de este "
                    f"número! Muchas "
                    f"felicidades. 🥳"
                )

                enviar_whatsapp(
                    remote_jid,
                    msg_anuncio,
                    mencion_jid=ganador_jid
                )

                if ganador_jid:

                    msg_privado = (
                        "🎉 *¡FELICIDADES!* 🎉\n\n"
                        f"¡Has ganado LA RIFA "
                        f"con tu número "
                        f"*{num_formateado}*! 🏆\n\n"
                        "Por favor, ponte en "
                        "contacto con la "
                        "administración para "
                        "recibir tu premio. 🤝"
                    )

                    enviar_whatsapp(
                        ganador_tel,
                        msg_privado
                    )

                return jsonify({
                    "status": "success"
                }), 200

            # ------------------------------------------------
            # LIBERAR
            # ------------------------------------------------

            elif comando.startswith("/liberar"):

                partes_cmd = comando.split(" ")

                if len(partes_cmd) > 1:

                    num_lib = (
                        partes_cmd[1].strip()
                    )

                    if (
                        num_lib.isdigit()
                        and 1 <= int(num_lib) <= 100
                    ):

                        n_str = str(
                            int(num_lib)
                        )

                        rifa[n_str] = {
                            "estado": "disponible",
                            "nombre": "",
                            "user_id": "",
                            "jid_completo": "",
                            "telefono_real": ""
                        }

                        data_rifa[
                            "numeros"
                        ] = rifa

                        guardar_data_completa(
                            data_rifa
                        )

                        enviar_whatsapp(
                            sender_id,
                            f"🟢 El número "
                            f"{n_str.zfill(2)} "
                            f"ha sido liberado."
                        )

                return jsonify({
                    "status": "success"
                }), 200

            # ------------------------------------------------
            # CONFIRMAR / RECHAZAR
            # ------------------------------------------------

            elif (
                comando.startswith("conf_")
                or comando.startswith("rech_")
            ):

                partes_cb = comando.split(
                    "_",
                    1
                )

                accion = partes_cb[0]

                req_id = (
                    partes_cb[1]
                    if len(partes_cb) > 1
                    else ""
                )

                if req_id in solicitudes:

                    sol = solicitudes[
                        req_id
                    ]

                    user_nombre = sol[
                        "nombre"
                    ]

                    user_tel = sol[
                        "user_id"
                    ]

                    user_nums = sol[
                        "numeros"
                    ]

                    chat_origen = sol[
                        "chat_origen"
                    ]

                    jid_completo = sol[
                        "jid_completo"
                    ]

                    telefono_real = sol.get(
                        "telefono_real",
                        ""
                    )

                    nums_formatted = ", ".join(
                        [
                            n.zfill(2)
                            for n in user_nums
                        ]
                    )

                    usuario_visible = texto_usuario(
                        user_nombre,
                        user_tel,
                        telefono_real
                    )

                    # ----------------------------------------
                    # APROBAR
                    # ----------------------------------------

                    if accion == "conf":

                        for n in user_nums:

                            rifa[n][
                                "estado"
                            ] = "ocupado"

                            rifa[n][
                                "nombre"
                            ] = user_nombre

                            rifa[n][
                                "user_id"
                            ] = user_tel

                            rifa[n][
                                "jid_completo"
                            ] = jid_completo

                            rifa[n][
                                "telefono_real"
                            ] = telefono_real

                        del solicitudes[
                            req_id
                        ]

                        data_rifa[
                            "numeros"
                        ] = rifa

                        data_rifa[
                            "solicitudes_pendientes"
                        ] = solicitudes

                        if all(
                            rifa[str(n)][
                                "estado"
                            ] == "ocupado"
                            for n in range(1, 101)
                        ):

                            data_rifa[
                                "estado_rifa"
                            ] = "finalizada"

                        guardar_data_completa(
                            data_rifa
                        )

                        enviar_whatsapp(
                            sender_id,
                            f"✅ *Aprobado.* "
                            f"Números: "
                            f"{nums_formatted}"
                        )

                        texto_pago_confirmado = (
                            f"🎉 *¡Hola "
                            f"{usuario_visible}!* 🎉\n\n"
                            f"Tu pago fue verificado. "
                            f"Tus números "
                            f"*({nums_formatted})* "
                            f"ya están registrados "
                            f"a tu nombre.\n\n"
                            f"📱 Teléfono: "
                            f"*{telefono_real}*"
                            if telefono_real
                            else
                            f"🎉 *¡Hola "
                            f"{usuario_visible}!* 🎉\n\n"
                            f"Tu pago fue verificado. "
                            f"Tus números "
                            f"*({nums_formatted})* "
                            f"ya están registrados "
                            f"a tu nombre."
                        )

                        try:

                            enviar_whatsapp(
                                user_tel,
                                texto_pago_confirmado,
                                mencion_jid=jid_completo
                            )

                        except Exception as e:

                            print(
                                "Error enviando "
                                f"confirmación al "
                                f"privado: {e}"
                            )

                        try:

                            if (
                                chat_origen
                                != user_tel
                            ):

                                enviar_whatsapp(
                                    chat_origen,
                                    texto_pago_confirmado,
                                    mencion_jid=jid_completo
                                )

                        except Exception as e:

                            print(
                                "Error enviando "
                                f"confirmación al "
                                f"grupo: {e}"
                            )

                    # ----------------------------------------
                    # RECHAZAR
                    # ----------------------------------------

                    elif accion == "rech":

                        for n in user_nums:

                            rifa[n] = {
                                "estado": "disponible",
                                "nombre": "",
                                "user_id": "",
                                "jid_completo": "",
                                "telefono_real": ""
                            }

                        del solicitudes[
                            req_id
                        ]

                        data_rifa[
                            "numeros"
                        ] = rifa

                        data_rifa[
                            "solicitudes_pendientes"
                        ] = solicitudes

                        guardar_data_completa(
                            data_rifa
                        )

                        enviar_whatsapp(
                            sender_id,
                            f"❌ *Rechazado "
                            f"el ID {req_id}.*"
                        )

                        texto_rechazo = (
                            f"❌ Lo sentimos "
                            f"{usuario_visible}, "
                            f"tu solicitud para "
                            f"los números "
                            f"*{nums_formatted}* "
                            f"fue rechazada. "
                            f"Los números vuelven "
                            f"a estar disponibles."
                        )

                        try:

                            enviar_whatsapp(
                                user_tel,
                                texto_rechazo,
                                mencion_jid=jid_completo
                            )

                        except Exception as e:

                            print(
                                "Error notificando "
                                f"rechazo al privado: "
                                f"{e}"
                            )

                        try:

                            if (
                                chat_origen
                                != user_tel
                            ):

                                enviar_whatsapp(
                                    chat_origen,
                                    texto_rechazo,
                                    mencion_jid=jid_completo
                                )

                        except Exception as e:

                            print(
                                "Error notificando "
                                f"rechazo al grupo: "
                                f"{e}"
                            )

                return jsonify({
                    "status": "success"
                }), 200

        # ====================================================
        # COMANDOS GENERALES
        # ====================================================

        if comando in [
            "lista",
            "listas"
        ]:

            texto_lista, menciones_lista = (
                generar_texto_lista()
            )

            respuesta = (
                f"¡Hola {push_name}! "
                f"Estado actual de LA RIFA:\n\n"
                f"{texto_lista}"
            )

            if estado_actual_rifa == "activa":

                respuesta += (
                    "\n\n👉 *¿Cómo comprar?* "
                    "Envía los números que "
                    "deseas separados por "
                    "coma (ej: *7, 14*)."
                )

            enviar_whatsapp(
                remote_jid,
                respuesta,
                mencion_jid=(
                    menciones_lista
                    if menciones_lista
                    else None
                )
            )

            return jsonify({
                "status": "success"
            }), 200

        # ====================================================
        # REGLAS
        # ====================================================

        elif comando == "/reglas":

            texto_reglas = (
                "📌 *Reglas de LA RIFA:*\n"
                "1. Escribe `lista` para ver "
                "los números disponibles "
                "(del 01 al 100).\n"
                "2. Envía los números que "
                "deseas separados por comas "
                "(ejemplo: `7, 14`).\n"
                "3. Revisa el total calculado "
                "con promoción y haz tu "
                "transferencia.\n"
                "4. El ganador se define "
                "mediante la Lotería de Florida."
            )

            enviar_whatsapp(
                remote_jid,
                texto_reglas
            )

            return jsonify({
                "status": "success"
            }), 200

        # ====================================================
        # PROCESAMIENTO DE NÚMEROS
        # ====================================================

        partes = [
            p.strip()
            for p in mensaje_texto
            .replace(" ", "")
            .split(",")
            if p.strip()
        ]

        es_lista_numeros = (
            all(
                p.isdigit()
                for p in partes
            )
            if partes
            else False
        )

        if es_lista_numeros:

            if estado_actual_rifa == "finalizada":

                enviar_whatsapp(
                    remote_jid,
                    "🔒 *Lo sentimos, "
                    "el sistema está cerrado.*"
                )

                return jsonify({
                    "status": "success"
                }), 200

            ocupados = []
            pendientes = []
            validos_para_reservar = []
            invalidos = []

            for p in partes:

                num_elegido = int(p)

                if 1 <= num_elegido <= 100:

                    num_str = str(
                        num_elegido
                    )

                    info = rifa[
                        num_str
                    ]

                    est = info.get(
                        "estado",
                        "disponible"
                    )

                    if est == "ocupado":

                        ocupados.append(
                            f"*{num_str.zfill(2)}*"
                        )

                    elif est == "pendiente":

                        pendientes.append(
                            f"*{num_str.zfill(2)}*"
                        )

                    else:

                        validos_para_reservar.append(
                            num_str
                        )

                else:

                    invalidos.append(p)

            mensajes_conflicto = []

            if ocupados:

                mensajes_conflicto.append(
                    f"🔴 El/los número(s) "
                    f"{', '.join(ocupados)} "
                    f"ya está(n) "
                    f"*OCUPADO(S)*."
                )

            if pendientes:

                mensajes_conflicto.append(
                    f"🟡 El/los número(s) "
                    f"{', '.join(pendientes)} "
                    f"está(n) *EN PROCESO "
                    f"DE VERIFICACIÓN*."
                )

            if invalidos:

                mensajes_conflicto.append(
                    f"⚠️ El/los número(s) "
                    f"{', '.join(invalidos)} "
                    f"está(n) fuera del "
                    f"rango (1 al 100)."
                )

            if (
                mensajes_conflicto
                and not validos_para_reservar
            ):

                enviar_whatsapp(
                    remote_jid,
                    f"Hola {push_name}:\n"
                    + "\n".join(
                        mensajes_conflicto
                    )
                )

                return jsonify({
                    "status": "success"
                }), 200

            # ------------------------------------------------
            # RESERVAR NÚMEROS
            # ------------------------------------------------

            if validos_para_reservar:

                req_id = (
                    "r"
                    + str(
                        uuid.uuid4().int
                    )[:4]
                )

                for n in validos_para_reservar:

                    rifa[n][
                        "estado"
                    ] = "pendiente"

                    rifa[n][
                        "nombre"
                    ] = push_name

                    rifa[n][
                        "user_id"
                    ] = sender_id

                    rifa[n][
                        "jid_completo"
                    ] = sender_full_jid

                    rifa[n][
                        "telefono_real"
                    ] = telefono_real

                solicitudes[
                    req_id
                ] = {

                    "nombre": push_name,

                    "user_id": sender_id,

                    "jid_completo": sender_full_jid,

                    "telefono_real": telefono_real,

                    "numeros": validos_para_reservar,

                    "chat_origen": remote_jid
                }

                data_rifa[
                    "numeros"
                ] = rifa

                data_rifa[
                    "solicitudes_pendientes"
                ] = solicitudes

                guardar_data_completa(
                    data_rifa
                )

                nums_solicitados_txt = (
                    ", ".join(
                        [
                            n.zfill(2)
                            for n in validos_para_reservar
                        ]
                    )
                )

                cantidad_nums = len(
                    validos_para_reservar
                )

                total_a_pagar, promo_txt = (
                    calcular_total_promocion(
                        cantidad_nums
                    )
                )

                # ------------------------------------------------
                # MENSAJE PARA EL CLIENTE
                # ------------------------------------------------

                usuario_cliente = texto_usuario(
                    push_name,
                    sender_id,
                    telefono_real
                )

                msg_cliente = (
                    "⏳ *SOLICITUD RECIBIDA* ⏳\n\n"
                    f"Hola {usuario_cliente}, "
                    f"recibimos tu pedido para "
                    f"el/los número(s): "
                    f"*{nums_solicitados_txt}*.\n\n"
                    f"📱 *Teléfono:* "
                    f"{telefono_real}"
                    if telefono_real
                    else
                    "⏳ *SOLICITUD RECIBIDA* ⏳\n\n"
                    f"Hola {usuario_cliente}, "
                    f"recibimos tu pedido para "
                    f"el/los número(s): "
                    f"*{nums_solicitados_txt}*.\n\n"
                )

                msg_cliente += (
                    f"\n💰 *Total a transferir:* "
                    f"${total_a_pagar:.2f}\n"
                )

                if promo_txt:

                    msg_cliente += (
                        f"🔥 *Promoción:* "
                        f"{promo_txt}\n"
                    )

                msg_cliente += (
                    "\n🟡 Quedan *reservados "
                    "temporalmente* mientras "
                    "el administrador verifica "
                    "tu pago."
                )

                enviar_whatsapp(
                    remote_jid,
                    msg_cliente,
                    mencion_jid=sender_full_jid
                )

                # ------------------------------------------------
                # ENLACES PARA ADMINISTRADOR
                # ------------------------------------------------

                link_aprobar = (
                    f"https://wa.me/"
                    f"{BOT_PHONE}"
                    f"?text=conf_{req_id}"
                )

                link_rechazar = (
                    f"https://wa.me/"
                    f"{BOT_PHONE}"
                    f"?text=rech_{req_id}"
                )

                # ------------------------------------------------
                # CLIENTE VISIBLE PARA ADMIN
                # ------------------------------------------------

                cliente_admin = texto_usuario(
                    push_name,
                    sender_id,
                    telefono_real
                )

                # ------------------------------------------------
                # MENSAJE AL ADMINISTRADOR
                # ------------------------------------------------

                txt_admin = (
                    "📥 *NUEVA SOLICITUD "
                    "DE COMPRA* "
                    f"(ID: `{req_id}`)\n\n"
                    f"👤 *Cliente:* "
                    f"{cliente_admin}\n"
                    f"📱 *Teléfono real:* "
                    f"{telefono_real}"
                    if telefono_real
                    else
                    "📥 *NUEVA SOLICITUD "
                    "DE COMPRA* "
                    f"(ID: `{req_id}`)\n\n"
                    f"👤 *Cliente:* "
                    f"{cliente_admin}"
                )

                txt_admin += (
                    f"\n"
                    f"🎟️ *Números:* "
                    f"*{nums_solicitados_txt}* "
                    f"({cantidad_nums} nums)\n"
                    f"💰 *Total Calculado:* "
                    f"${total_a_pagar:.2f}\n\n"
                    f"Haz clic para gestionar:\n"
                    f"👉 *APROBAR:* "
                    f"{link_aprobar}\n\n"
                    f"👉 *RECHAZAR:* "
                    f"{link_rechazar}"
                )

                enviar_whatsapp(
                    ADMIN_PHONE,
                    txt_admin,
                    mencion_jid=sender_full_jid
                )

            return jsonify({
                "status": "success"
            }), 200

        return jsonify({
            "status": "ignored_text"
        }), 200

    except Exception as e:

        print(
            f"Error procesando webhook: {e}"
        )

        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


# ============================================================
# INICIAR SERVIDOR
# ============================================================

if __name__ == "__main__":

    inicializar_rifa()

    app.run(
        host="0.0.0.0",
        port=PORT
    )
