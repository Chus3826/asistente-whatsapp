from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
import json
import os
from datetime import datetime
from twilio.rest import Client
from apscheduler.schedulers.background import BackgroundScheduler
from pytz import timezone
from dateparser.search import search_dates
import openai
import re

import sys
import logging
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

app = Flask(__name__)
DB_FILE = "recordatorios.json"
TEMP_FILE = "esperando_hora.json"

openai.api_key = os.environ.get("OPENAI_API_KEY")
TWILIO_PHONE = os.environ.get("TWILIO_PHONE")
client = Client(os.environ.get("TWILIO_SID"), os.environ.get("TWILIO_AUTH_TOKEN"))

def cargar_datos():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return json.load(f)
    return {}

def guardar_datos(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f)

def cargar_temporal():
    if os.path.exists(TEMP_FILE):
        with open(TEMP_FILE, "r") as f:
            return json.load(f)
    return {}

def guardar_temporal(data):
    with open(TEMP_FILE, "w") as f:
        json.dump(data, f)

def enviar_whatsapp(to, body):
    try:
        client.messages.create(from_=TWILIO_PHONE, to=to, body=body)
        print(f"✅ Enviado a {to}: {body}")
    except Exception as e:
        print(f"❌ Error al enviar a {to}: {e}")

def revisar_recordatorios():
    print("⏰ [Scheduler activo] Revisando recordatorios...")
    data = cargar_datos()
    zona_local = timezone("Europe/Madrid")
    ahora = datetime.now(zona_local).strftime("%H:%M")
    hoy = datetime.now(zona_local).strftime("%Y-%m-%d")

    for numero, recordatorios in data.items():
        for r in recordatorios.get("diarios", []):
            if r["hora"] == ahora:
                enviar_whatsapp(numero, f"⏰ Recordatorio diario: {r['mensaje']}")
        for r in recordatorios.get("puntuales", []):
            if r["fecha"] == hoy and r["hora"] == ahora:
                enviar_whatsapp(numero, f"📅 Recordatorio de cita: {r['mensaje']}")

def interpretar_con_gpt(mensaje):
    prompt = f"Extraé la hora y el mensaje de este texto para un recordatorio. Respondé solo en JSON con claves 'hora', 'mensaje', y opcionalmente 'fecha'. Texto: {mensaje}"
    try:
        respuesta = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.3
        )
        contenido = respuesta.choices[0].message.content.strip()
        print("🧠 GPT respondió:", contenido)
        contenido = re.sub(r"^[^\{]*", "", contenido)
        contenido = re.sub(r"[^\}]*$", "", contenido)
        return json.loads(contenido)
    except Exception as e:
        print("❌ Error usando OpenAI:", e)
        return None

@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    mensaje = request.form.get("Body").strip()
    numero = request.form.get("From").strip().lower()
    data = cargar_datos()
    temp = cargar_temporal()

    if numero not in data:
        data[numero] = {"diarios": [], "puntuales": []}

    respuesta = ""

    # Si estaba esperando hora
    if numero in temp:
        tipo = temp[numero]["tipo"]
        msg = temp[numero]["mensaje"]
        fecha = temp[numero].get("fecha")
        fechas = search_dates(mensaje, languages=["es"], settings={"PREFER_DATES_FROM": "future"})

        if fechas:
            _, fecha_hora = fechas[0]
            hora = fecha_hora.strftime("%H:%M")
            if tipo == "diario":
                data[numero]["diarios"].append({"hora": hora, "mensaje": msg})
                respuesta = f"💊 Guardado diario a las {hora}: {msg}"
            else:
                data[numero]["puntuales"].append({"hora": hora, "fecha": fecha, "mensaje": msg})
                respuesta = f"📅 Guardado puntual para el {fecha} a las {hora}: {msg}"
            guardar_datos(data)
        else:
            respuesta = "❌ No entendí la hora. Probá algo como 'a las 9'."
        temp.pop(numero)
        guardar_temporal(temp)
    else:
        parsed = interpretar_con_gpt(mensaje)
        if parsed and "mensaje" in parsed:
            msg = parsed["mensaje"]
            hora = parsed.get("hora")
            fecha = parsed.get("fecha")

            if hora:
                if fecha:
                    data[numero]["puntuales"].append({"hora": hora, "fecha": fecha, "mensaje": msg})
                    respuesta = f"📅 Guardado puntual para el {fecha} a las {hora}: {msg}"
                else:
                    data[numero]["diarios"].append({"hora": hora, "mensaje": msg})
                    respuesta = f"💊 Guardado diario a las {hora}: {msg}"
                guardar_datos(data)
            else:
                tipo = "puntual" if "fecha" in parsed else "diario"
                temp[numero] = {"tipo": tipo, "mensaje": msg}
                if "fecha" in parsed:
                    temp[numero]["fecha"] = parsed["fecha"]
                guardar_temporal(temp)
                respuesta = "⏰ ¿A qué hora querés que te lo recuerde?"
        elif mensaje.lower() == "ver":
            diarios = data[numero]["diarios"]
            puntuales = data[numero]["puntuales"]
            respuesta = "🧠 Tus recordatorios:💊 Diarios:"
            for r in diarios:
                respuesta += f"🕒 {r['hora']} - {r['mensaje']}"
            respuesta += "📅 Puntuales:"
            for r in puntuales:
                respuesta += f"📆 {r['fecha']} {r['hora']} - {r['mensaje']}"
        else:
            respuesta = (
                "🤖 Comandos:"
                "- tomar pastilla a las 10"
                "- ver"
            )

    r = MessagingResponse()
    r.message(respuesta)
    return Response(str(r), mimetype="application/xml")

print("✅ Asistente actualizado y esperando mensajes.")
scheduler = BackgroundScheduler()
scheduler.add_job(revisar_recordatorios, "interval", minutes=1)
scheduler.start()

port = int(os.environ.get("PORT", 5000))
app.run(host="0.0.0.0", port=port)
