
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

app = Flask(__name__)
DB_FILE = "recordatorios.json"

openai.api_key = os.environ.get("OPENAI_API_KEY")

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

    for numero, recordatorios in data.items():
        for r in recordatorios.get("diarios", []):
            if r["hora"] == ahora:
                enviar_whatsapp(numero, f"⏰ Recordatorio diario: {r['mensaje']}")
        for r in recordatorios.get("puntuales", []):
            if r["fecha"] == hoy and r["hora"] == ahora:
                enviar_whatsapp(numero, f"📅 Recordatorio de cita: {r['mensaje']}")

def interpretar_con_gpt(mensaje):
    prompt = f"Extraé la hora y el mensaje de este texto para un recordatorio diario. Respondé solo en JSON (ej: {{'hora': '09:00', 'mensaje': 'tomar pastilla'}}). Texto: {mensaje}"
    try:
        respuesta = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=80,
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
    if numero not in data:
        data[numero] = {"diarios": [], "puntuales": []}
    respuesta = ""

    intenciones = ["recordame", "recordar", "tomar", "pastilla", "medicina", "me toca", "tengo que", "a las"]

    if any(p in mensaje.lower() for p in intenciones):
        try:
            fechas = search_dates(mensaje, languages=["es"], settings={"PREFER_DATES_FROM": "future"})
            print("🔍 Resultado de search_dates:", fechas)

            if fechas:
                _, fecha_hora = fechas[0]
                hora = fecha_hora.strftime("%H:%M")
                texto = mensaje.replace(fechas[0][0], "").strip()
                data[numero]["diarios"].append({"hora": hora, "mensaje": texto})
                guardar_datos(data)
                respuesta = f"💊 Guardado para las {hora}: {texto}"
            else:
                print("⚠️ No se detectó hora. Usando GPT...")
                parsed = interpretar_con_gpt(mensaje)
                print("🧪 Resultado de GPT:", parsed)
                if parsed and "hora" in parsed and "mensaje" in parsed:
                    data[numero]["diarios"].append({
                        "hora": parsed["hora"],
                        "mensaje": parsed["mensaje"]
                    })
                    guardar_datos(data)
                    respuesta = f"💊 Guardado (GPT) {parsed['hora']}: {parsed['mensaje']}"
                else:
                    respuesta = "❌ No pude entender el mensaje ni con ayuda. Probá de otra forma."
        except Exception as e:
            respuesta = f"❌ Error al procesar: {e}"
    elif mensaje.lower() == "ver":
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
            "🤖 Comandos:
"
            "- tomar pastilla a las 10
"
            "- ver"
        )

    r = MessagingResponse()
    r.message(respuesta)
    return Response(str(r), mimetype="application/xml")

print("✅ Asistente híbrido iniciado.")
scheduler = BackgroundScheduler()
scheduler.add_job(revisar_recordatorios, "interval", minutes=1)
scheduler.start()

port = int(os.environ.get("PORT", 5000))
app.run(host="0.0.0.0", port=port)
