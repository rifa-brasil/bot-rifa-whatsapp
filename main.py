from flask import Flask, request
import os
import requests
import sqlite3
import random
from datetime import datetime

app = Flask(name)

# Token de Whapi - lo toma de las variables de Render
WHAPI_TOKEN = os.environ.get("WHAPI_TOKEN")
WHAPI_URL = "https://gate.whapi.cloud"

# --- BASE DE DATOS SQLITE ---
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
    except sqlite3.IntegrityError:
        return False # Ya existe
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

# --- ENVIAR MENSAJE POR WHAPI ---
def send_message(to, body):
    if not WHAPI_TOKEN:
        print("ERROR: WHAPI_TOKEN no configurado")
        return
    headers = {"Authorization": f"Bearer {WHAPI_TOKEN}", "Content-Type": "application/json"}
    data = {"to": to, "body": body}
    requests.post(f"{WHAPI_URL}/messages/text", json=data, headers=headers)

# --- WEBHOOK PRINCIPAL ---
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if 'messages' in data and len(data['messages']) > 0:
        msg = data['messages'][0]
        numero = msg
