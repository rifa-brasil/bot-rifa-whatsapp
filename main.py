import os
import json
import requests
import re
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

app = Flask(__name__)

# Tu Token de Whapi configurado de forma segura
WHAPI_TOKEN = "zL78J7yS7OM8I3ml5Ybvps1rkcxbKV7K" 
WHAPI_API_URL = "https://gate.whapi.cloud/messages/text"

# 🔑 TU CLAVE SECRETA DE ADMINISTRADOR PARA RESETEAR
CLAVE_RESET = "admin.resetear.rifa.99"

DB_FILE = "rifa_db.json"

def inicializar_rifa():
    if not os.path.exists(DB_FILE):
        rifa = {str(i): {"estado": "disponible", "nombre": "", "telefono": "", "enlace": ""} for i in range(1, 101)}
        with open(DB_FILE, "w") as f:
            json.dump(rifa, f, indent=4)

def borrar_y_recrear_base_datos():
    try:
        if os.path.exists(DB_FILE):
            os.remove(DB_FILE)
    except Exception as e:
        print(f"Error al eliminar archivo: {e}")
    inicializar_rifa()

def obtener_rifa():
    inicializar_rifa()
    with open(DB_FILE, "r") as f:
        return json.load(f)

def guardar_rifa(rifa):
    with open(DB_FILE, "w") as f:
        json.dump(rifa, f, indent=4)

def generar_texto_lista():
    rifa = obtener_rifa()
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
    return texto

def enviar_mensaje_whapi(chat_id, texto, menciones=[]):
    payload = {
        "to": chat_id,
        "body": texto
    }
    if menciones:
        payload["mentions"] = menciones

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Bearer {WHAPI_TOKEN}"
    }
    try:
        requests.post(WHAPI_API_URL, json=payload, headers=headers)
    except Exception as e:
        print(f"Error al enviar a Whapi: {e}")

@app.route("/", methods=["GET"])
def home():
    return "Servidor conectado con Whapi listo.", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    if not data:
        return "No data", 400

    messages = data.get("messages", [])
    if not messages:
        return "No messages", 200

    msg = messages[0]
    
    if msg.get("from_me", False):
        return "Sent by me", 200

    chat_id = msg.get("chat_id", "")
    raw_from = msg.get("from", "")
    
    if not raw_from:
        raw_from = msg.get("sender_id", chat_id)
        
    text_obj = msg.get("text", {})
    mensaje_texto = text_obj.get("body", "").strip() if text_obj else ""
    comando = mensaje_texto.lower()

    id_antes_del_arroba = raw_from.split("@")[0]
    numero_persona = re.sub(r'\D', '', id_antes_del_arroba)
    link_directo = f"wa.me/{numero_persona}"
    
    nombre_usuario = msg.get("from_name", "").strip()
    if not nombre_usuario:
        nombre_usuario = msg.get("sender_name", "").strip()
    if not nombre_usuario:
        nombre_usuario = msg.get("contact", {}).get("name", "").strip()
    if not nombre_usuario:
        nombre_usuario = f"+{numero_persona}"

    inicializar_rifa()
    rifa = obtener_rifa()
    respuesta = ""
    lista_menciones = []

    # 🔐 REINICIO POR FRASE MÁSTER
    if comando == CLAVE_RESET:
        borrar_y_recrear_base_datos()
        respuesta = "🔄 *¡La rifa ha sido reseteada con éxito!* Todos los 100 números vuelven a estar disponibles.\n\n" + generar_texto_lista()

    # 🏆 DETECTAR GANADOR AUTOMÁTICAMENTE
    elif comando.startswith("resultado de florida con"):
        # Extraemos solo los dígitos numéricos que escribiste al final de la frase
        numeros_encontrados = re.findall(r'\d+', comando)
        if numeros_encontrados:
            num_ganador = str(int(numeros_encontrados[0])) # Lo pasa a entero y luego a string para quitar ceros extras (ej: "07" -> "7")
            
            if num_ganador in rifa:
                info_ganador = rifa[num_ganador]
                
                if info_ganador["estado"] == "ocupado":
                    nombre_ganador = info_ganador["nombre"]
                    telefono_ganador = info_ganador["telefono"].replace("+", "").strip()
                    chat_privado_ganador = f"{telefono_ganador}@c.us"
                    
                    # 1. Armamos el anuncio para el grupo de WhatsApp
                    respuesta = (
                        f"🎉🎉 *¡TENEMOS UN GANADOR EN LA RIFA!* 🎉🎉\n\n"
                        f"El número premiado en el tiro de la Florida fue el *{num_ganador.zfill(2)}*.\n\n"
                        f"🥇 *¡Felicidades {nombre_ganador}!* (@{telefono_ganador}) Eres el ganador de los *400 reales* 💵✨.\n\n"
                        f"📩 Le hemos enviado un mensaje privado automáticamente para coordinar su premio."
                    )
                    lista_menciones = [chat_privado_ganador]
                    
                    # 2. Enviamos el mensaje al PRIVADO del ganador de forma automática
                    texto_privado = (
                        f"¡Hola {nombre_ganador}! 👋\n\n"
                        f"🎉 *¡MUCHAS FELICIDADES!* 🎉\n\n"
                        f"Tu número *{num_ganador.zfill(2)}* salió premiado en el resultado de la Florida y has ganado los *400 reales* de la rifa. 🏆💵\n\n"
                        f"👉 Por favor, ponte en contacto con el administrador lo antes posible para coordinar tu pago (ya sea transferencia PIX aquí en Brasil o entrega en Cuba en CUP)."
                    )
                    enviar_mensaje_whapi(chat_privado_ganador, texto_privado)
                else:
                    respuesta = f"🎫 El número *{num_ganador.zfill(2)}* salió premiado en la Florida, pero lamentablemente quedó *Disponible* (nadie lo compró)."
            else:
                respuesta = "⚠️ El número ingresado no está en el rango correcto (debe ser del 1 al 100)."
        else:
            respuesta = "⚠️ Por favor, escribe el número ganador al final de la frase. Ejemplo: *resultado de florida con 25*"

    # ✨ SALUDO ACTUALIZADO
    elif comando in ["hola", "buenas", "lista", "inicio", "rifa"]:
        respuesta = (
            f"¡Hola {nombre_usuario}! Bienvenido a la Rifa Automática. ✨\n\n"
            f"💵 *Compra uno o varios números por un valor de 10 reales y gana 400 reales.*\n"
            f"🏆 El premio se entregará aquí en Brasil mediante transferencia PIX o al familiar en Cuba en CUP.\n\n"
            f"{generar_texto_lista()}\n\n"
            f"👉 *¿Cómo comprar?* Responde escribiendo el número que deseas (puedes separar varios por comas, ej: *7, 14, 25*)."
        )

    else:
        partes = [p.strip() for p in mensaje_texto.split(",")]
        es_lista_numeros = all(p.isdigit() for p in partes) if partes and mensaje_texto else False

        if es_lista_numeros:
            exitos = []
            ocupados = []
            invalidos = []

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
                        ocupados.append(f"*{num_str.zfill(2)}* (de {info['nombre']})")
                else:
                    invalidos.append(p)

            if exitos:
                guardar_rifa(rifa)

            mensajes_resultado = []
            if exitos:
                mensajes_resultado.append(f"✅ ¡Felicidades! Reservaste con éxito: {', '.join(exitos)}.")
            if ocupados:
                mensajes_resultado.append(f"❌ Los siguientes números ya estaban ocupados: {', '.join(ocupados)}.")
            if invalidos:
                mensajes_resultado.append(f"⚠️ Los números fuera de rango (1 al 100) fueron ignorados: {', '.join(invalidos)}.")

            respuesta = "\n".join(mensajes_resultado) + "\n\n" + generar_texto_lista()

            # CONTROL DE COBERTURA DE LOS 100 NÚMEROS
            todos_ocupados = all(rifa[str(n)]["estado"] == "ocupado" for n in range(1, 101))
            
            if todos_ocupados:
                telefonos_participantes = set()
                for n in range(1, 101):
                    tel = rifa[str(n)].get("telefono", "").replace("+", "").strip()
                    if tel:
                        telefonos_participantes.add(f"{tel}@c.us")
                
                lista_menciones = list(telefonos_participantes)
                hora_actual_brasil = datetime.utcnow() - timedelta(hours=3)
                hora_int = hora_actual_brasil.hour

                if hora_int < 22:
                    texto_tiro = "🚨 *¡El resultado será esta misma noche en el tiro de la Florida!* Mucha suerte a todos. 🍀"
                else:
                    texto_tiro = "🚨 *¡Los números se completaron tarde! El resultado será mañana en el tiro de la Florida.* Mucha suerte a todos. 🍀"

                respuesta_cierre = (
                    "🔥 *¡ATENCIÓN A TODOS LOS PARTICIPANTES!* 🔥\n\n"
                    "¡Todos los 100 números de la rifa han sido ocupados! El sistema se ha cerrado para nuevas compras.\n\n"
                    f"{texto_tiro}\n\n"
                    "👥 *Participantes convocados:* "
                )
                
                menciones_texto = " ".join([f"@{t.split('@')[0]}" for t in lista_menciones])
                respuesta_cierre += menciones_texto

                enviar_mensaje_whapi(chat_id, respuesta)
                enviar_mensaje_whapi(chat_id, respuesta_cierre, menciones=lista_menciones)
                return "OK", 200

    if respuesta:
        enviar_mensaje_whapi(chat_id, respuesta, menciones=lista_menciones)

    return "OK", 200

if __name__ == "__main__":
    inicializar_rifa()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
