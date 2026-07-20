import os
import json
import requests
import re
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

app = Flask(__name__)

# 🔑 TU TOKEN DEL CANAL SANDBOX DE WHAPI
WHAPI_TOKEN = "zL78J7yS7OM8I3ml5Ybvps1rkcxbKV7K" 
WHAPI_API_URL = "https://gate.whapi.cloud/messages/text"

# 🔑 ID DE RESPALDO DE TU GRUPO
GRUPO_CHAT_ID_RESPALDO = "DyI3ISDPZjyKw3w0cD8elC@g.us"

# 🔐 FILTRO DE SEGURIDAD MÁSTER: Tus últimos 8 dígitos (así reconoce con 55119..., 5511... o sin código)
NUMERO_ADMIN_SEGURO = "48824359"

# 🔑 TU CLAVE SECRETA DE ADMINISTRADOR PARA RESETEAR
CLAVE_RESET = "resetlist"

DB_FILE = "rifa_db.json"

def inicializar_rifa():
    try:
        if not os.path.exists(DB_FILE):
            data_inicial = {
                "estado_rifa": "activa",
                "numeros": {str(i): {"estado": "disponible", "nombre": "", "telefono": "", "enlace": ""} for i in range(1, 101)}
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
                data = {"estado_rifa": "activa", "numeros": data}
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
        if info["estado"] == "disponible":
            texto += f"🟢 *{num_str}*: Disponible\n"
            disponibles += 1
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

        # 🛑 EVITAR BUCLE: Ignorar mensajes que el propio bot envió automáticamente
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
        estado_actual_rifa = data_rifa.get("estado_rifa", "activa")
        
        respuesta = ""
        # Reconoce el admin si contiene la secuencia de tu número de São Paulo
        es_admin_real = NUMERO_ADMIN_SEGURO in numero_persona or msg.get("from_me") is True or msg.get("outbound") is True

        # 🔄 COMANDO RESET
        if comando == CLAVE_RESET:
            if not es_admin_real:
                return "OK", 200
            borrar_y_recrear_base_datos()
            respuesta = "🔄 *¡La rifa ha sido reseteada con éxito!* Todos los 100 números vuelven a estar disponibles y el sistema está abierto.\n\n" + generar_texto_lista()

        # 🏆 DETECTAR GANADOR AUTOMÁTICAMENTE
        elif comando.startswith("resultado de florida con"):
            if not es_admin_real:
                print(f"⛔ Intento de comando ganador rechazado por no ser admin.")
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
                                f"🔒 *La lista ha sido cerrada de forma definitiva.* Ya no se pueden ocupar más números libres hasta el próximo sorteo.\n\n"
                                f"📩 Le hemos enviado un mensaje privado automáticamente para coordinar su premio."
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
        elif comando in ["lista"]:
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
                # 🛡️ REBOTE SI ESTÁ FINALIZADA / CONGELADA
                if estado_actual_rifa == "finalizada":
                    respuesta = "🔒 *Lo sentimos, el sistema está cerrado.* Todos los números están congelados o el sorteo ya concluyó. Esperando reinicio del administrador."
                    enviar_mensaje_whapi(chat_id_actual, respuesta)
                    return "OK", 200

                exitos, ocupados, invalidos = [], [], []

                for p in partes:
                    num_elegido = int(p)
                    if 1 <= num_elegido <= 100:
                        num_str = str(num_elegido)
                        info = rifa[num_str]
                        if info["estado"] == "disponible":
                            rifa[num_str] = {
                                "estado": "ocupado",
                                "nombre": nombre_usuario,
                                "telefono": f"+{numero_persona}",
                                "enlace": link_directo
                            }
                            exitos.append(num_str.zfill(2))
                        else:
                            ocupados.append(f"*{num_str.zfill(2)}*")
                    else:
                        invalidos.append(p)

                if exitos:
                    data_rifa["numeros"] = rifa
                    guardar_data_completa(data_rifa)

                # Verificar inmediatamente después de guardar si se alcanzó el total
                todos_ocupados = all(rifa[str(n)]["estado"] == "ocupado" for n in range(1, 101))
                
                if todos_ocupados:
                    data_rifa["estado_rifa"] = "finalizada"
                    guardar_data_completa(data_rifa)

                    lista_completa_final = generar_texto_lista()
                    
                    # 🕒 Cálculo de hora en vivo de Brasil (UTC-3)
                    hora_actual_brasil = datetime.utcnow() - timedelta(hours=3)
                    hora_int = hora_actual_brasil.hour

                    if hora_int < 22:
                        texto_tiro = "🚨 *¡El resultado será esta misma noche en el tiro de la Florida!* Mucha suerte a todos. 🍀"
                    else:
                        texto_tiro = "🚨 *¡Los números se completaron pasadas las 22:00h! El resultado será mañana por la noche en el tiro de la Florida.* Mucha suerte a todos. 🍀"

                    grupo_destino_cierre = chat_id_actual if "@g.us" in chat_id_actual else GRUPO_CHAT_ID_RESPALDO
                    
                    respuesta_cierre = (
                        "🔥 *¡ATENCIÓN A TODOS LOS PARTICIPANTES!* 🔥\n\n"
                        "¡Todos los 100 números de la rifa han sido completamente ocupados! El sistema se ha cerrado y congelado automáticamente para nuevas compras o ediciones.\n\n"
                        f"{lista_completa_final}\n\n"
                        f"{texto_tiro}"
                    )
                    enviar_mensaje_whapi(grupo_destino_cierre, respuesta_cierre)
                    return "OK", 200
                
                mensajes_resultado = []
                if exitos: mensajes_resultado.append(f"✅ Reservaste con éxito: {', '.join(exitos)}.")
                if ocupados: mensajes_resultado.append(f"❌ Ya ocupados: {', '.join(ocupados)}.")
                if invalidos: mensajes_resultado.append(f"⚠️ Fuera de rango: {', '.join(invalidos)}.")

                respuesta = "\n".join(mensajes_resultado) + "\n\n" + generar_texto_lista()

        if respuesta:
            enviar_mensaje_whapi(chat_id_actual, respuesta)

    except Exception as e_global:
        print(f"💥 ERROR CRÍTICO CRASH EVITADO: {e_global}")

    return "OK", 200

if __name__ == "__main__":
    inicializar_rifa()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
