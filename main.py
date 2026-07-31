from flask import Flask, request
import os
import requests
import sqlite3
import random
from datetime import datetime

app = Flask(name)
WHAPI_TOKEN = os.environ.get("WHAPI_TOKEN")
WHAPI_URL = "https://gate.whapi.cloud"

# --- BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect('rifa.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS participantes
                 (id INTEGER PRIMARY KEY, numero TEXT UNIQUE, nombre TEXT, fecha TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

def agregar_participante(numero, nombre):
    conn = sqlite3.connect('rifa.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO participantes (numero, nombre, fecha) VALUES (?,?,?)",
                  (numero, nombre, datetime.now()))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def obtener_participantes():
    conn = sqlite3.connect('rifa.db')
    c = conn.cursor()
    c.execute("SELECT numero, nombre FROM participantes")
    datos = c.fetchall()
    conn.close()
    return datos

def sortear_ganador():
    participantes = obtener_participantes()
    if not participantes:
        return None
    ganador = random.choice(participantes)
    return ganador

# --- ENVIAR MENSAJE WHAPI ---
def send_message(to, body):
    headers = {"Authorization": f"Bearer {WHAPI_TOKEN}", "Content-Type": "application/json"}
    data = {"to": to, "body": body}
    requests.post(f"{WHAPI_URL}/messages/text", json=data, headers=headers)

# --- WEBHOOK ---
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if 'messages' in data:
        msg = data['messages'][0]
        numero = msg['from']
        texto = msg['text']['body'].lower().strip()
        nombre = msg.get('from_name', 'Participante')

        if texto == 'hola' or texto == '1':
            respuesta = "🎟️ *BIENVENIDO A LA RIFA BRASIL* 🎟️\n\nResponde con tu NOMBRE COMPLETO para registrarte.\n\nEjemplo: Juan Perez"
            send_message(numero, respuesta)

        elif texto == 'sortear':
            ganador = sortear_ganador()
            if ganador:
                respuesta = f"🏆 *SORTEO REALIZADO* 🏆\n\nEl ganador es:\n*Nombre:* {ganador[1]}\n*Numero:* {ganador[0]}\n\n¡Felicidades!"
            else:
                respuesta = "Aún no hay participantes para sortear 😅"
            send_message(numero, respuesta)

        else: # Registramos como participante
            if agregar_participante(numero, texto.title()):
                respuesta = f"✅ *Registrado con éxito {texto.title()}*\n\nYa estás participando. Mucha suerte!"
            else:
                respuesta = f"Ya estás registrado {texto.title()} 😉"
            send_message(numero, respuesta)

    return "ok", 200

@app.route('/')
def home():
    return "Bot de Rifa Activo"

if name == 'main':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
