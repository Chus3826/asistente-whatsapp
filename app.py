
from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
import json
import os
from datetime import datetime
from twilio.rest import Client
from apscheduler.schedulers.background import BackgroundScheduler
from pytz import timezone
from dateparser.search import search_dates
import dateparser

app = Flask(__name__)
DB_FILE = "recordatorios.json"

def cargar_datos():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return json.load(f)
    return {}

def guardar_datos(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f)

TWILIO_PHONE = os.environ.get("TWILIO_PHONE")
client = Client(os.environ.get("TWILIO_SID"), os.environ.get("TWILIO_AUTH_TOKEN"))

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
    print(f"🕒 Hora actual: {ahora} | 📅 Fecha: {hoy}")

    for numero, recordatorios in data.items():
        for r in recordatorios.get("diarios", []):
            if r["hora"] == ahora:
                enviar_whatsapp(numero, f"⏰ Recordatorio diario: {r['mensaje']}")
        for r in recordatorios.get("puntuales", []):
            if r["fecha"] == hoy and r["hora"] == ahora:
                enviar_whatsapp(numero, f"📅 Recordatorio de cita: {r['mensaje']}")

@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    mensaje = request.form.get("Body").strip().lower()
    numero = request.form.get("From").strip().lower()
    data = cargar_datos()
    if numero not in data:
        data[numero] = {"diarios": [], "puntuales": []}
    respuesta = ""

if "medicacion" in mensaje or "tomar" in mensaje or "pastilla" in mensaje:
    try:
        fechas = search_dates(mensaje, languages=['es'])
        if fechas:
            _, fecha_hora = fechas[0]
            hora = fecha_hora.strftime("%H:%M")
            texto = mensaje.replace(hora, "").strip()
            data[numero]["diarios"].append({"hora": hora, "mensaje": texto})
            guardar_datos(data)
            respuesta = f"💊 Recordatorio diario guardado para las {hora}: {texto}"
        else:
            respuesta = "❌ No entendí la hora. Escribilo así: tomar pastilla a las 9"
    except:
        respuesta = "❌ No pude procesar eso. Probá con una frase sencilla."


    elif mensaje == "ver":
        diarios = data[numero]["diarios"]
        puntuales = data[numero]["puntuales"]
        respuesta = "🧠 Tus recordatorios:\n\n💊 Diarios:\n"
        if diarios:
            for r in diarios:
                respuesta += f"🕒 {r['hora']} - {r['mensaje']}\n"
        else:
            respuesta += "Nada guardado.\n"
        respuesta += "\n📅 Puntuales:\n"
        if puntuales:
            for r in puntuales:
                respuesta += f"📆 {r['fecha']} {r['hora']} - {r['mensaje']}\n"
        else:
            respuesta += "Nada guardado."

    else:
        respuesta = (
            "🤖 Comandos disponibles:\n"
            "- escribir: tengo que tomar algo a las 10\n"
            "- escribir: ver\n"
            "(no necesitás seguir un formato exacto)"
        )


    r = MessagingResponse()
    r.message(respuesta)
    return Response(str(r), mimetype="application/xml")

if __name__ == "__main__":
    print("✅ Iniciando asistente Flask (versión NLP)...")
    scheduler = BackgroundScheduler()
    scheduler.add_job(revisar_recordatorios, "interval", minutes=1)
    scheduler.start()
    print("✅ Programador de recordatorios iniciado.")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
