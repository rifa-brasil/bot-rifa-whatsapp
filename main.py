import os
import json
from flask import Flask, request, jsonify

app = Flask(__name__)

# Archivo local para simular la base de datos de la rifa
DB_FILE = "rifa_db.json"

def inicializar_rifa():
    if not os.path.exists(DB_FILE):
        # Creamos los 100 números libres por defecto
        rifa = {str(i): {"estado": "disponible", "nombre": "", "telefono": ""} for i in range(1, 101)}
        with open(DB_FILE, "w") as f:
            json.dump(rifa, f, indent=4)

def obtener_rifa():
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
            texto += f"🔴 *{num_str}*: Ocupado por {info['nombre']} ({info['telefono']})\n"
            
    texto += f"\n📊 *Resumen:* Quedan {disponibles} números disponibles."
    return texto

@app.route("/", methods=["GET"])
def home():
    return "El servidor del bot de la Rifa está activo y corriendo en la nube.", 200

# Endpoint que recibirá los mensajes simulados de WhatsApp mediante un Webhook estándar
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "No data received"}), 400
        
    # Extraemos datos del mensaje entrante
    telefono = data.get("from", "")
    nombre_usuario = data.get("name", "Participante")
    mensaje_texto = data.get("text", "").strip()
    
    inicializar_rifa()
    rifa = obtener_rifa()
    
    # Lógica del bot
    if mensaje_texto.lower() in ["hola", "buenas", "lista", "inicio", "rifa"]:
        respuesta = f"¡Hola {nombre_usuario}! Bienvenido a la Rifa Automática. ✨\n\n" + generar_texto_lista() + "\n\n👉 *¿Cómo comprar?* Solo responde escribiendo el número que deseas (ejemplo: si quieres el 7, escribe solo el número *7*)."
        return jsonify({"reply": respuesta})
        
    # Validamos si el usuario intenta ingresar un número del 1 al 100
    if mensaje_texto.isdigit():
        num_elegido = int(mensaje_texto)
        if 1 <= num_elegido <= 100:
            num_str = str(num_elegido)
            info = rifa[num_str]
            
            if info["estado"] == "disponible":
                # Asignamos el número al usuario
                rifa[num_str] = {
                    "estado": "ocupado",
                    "nombre": nombre_usuario,
                    "telefono": telefono
                }
                guardar_rifa(rifa)
                
                respuesta = f"✅ ¡Felicidades {nombre_usuario}! Has reservado con éxito el número *{num_str.zfill(2)}*.\n\n" + generar_texto_lista()
                return jsonify({"reply": respuesta})
            else:
                respuesta = f"❌ Lo siento, el número *{num_str.zfill(2)}* ya fue seleccionado por {info['nombre']}. Por favor, elige otro número disponible.\n\n" + generar_texto_lista()
                return jsonify({"reply": respuesta})
                
    respuesta = "⚠️ Opción no válida. Escribe *lista* para ver los números disponibles o escribe directamente el número que deseas comprar (del 1 al 100)."
    return jsonify({"reply": respuesta})

if __name__ == "__main__":
    inicializar_rifa()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
