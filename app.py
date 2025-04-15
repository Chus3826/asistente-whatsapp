
from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
import json
import os
from datetime import datetime
from twilio.rest import Client
from apscheduler.schedulers.background import BackgroundScheduler
from pytz import timezone
import openai
import re

app = Flask(__name__)
DB_FILE = "recordatorios.json"
TEMP_FILE = "esperando_contexto.json"

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

def interpretar_completo_gpt(mensaje):
    prompt = f"""Extraé la hora (formato 24h HH:MM), el mensaje y la fecha (si se menciona) desde este texto para un recordatorio. Respondé solo en JSON con claves: 'hora', 'mensaje', 'fecha' (si hay).
Texto: {mensaje}"""
    try:
        respuesta = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.3
        )
        contenido = respuesta.choices[0].message.content.strip()
        contenido = re.sub(r"^[^{]*", "", contenido)
        contenido = re.sub(r"[^}]*$", "", contenido)
        return json.loads(contenido)
    except Exception as e:
        print("❌ Error con OpenAI:", e)
        return None

@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    mensaje = request.form.get("Body").strip()
    numero = request.form.get("From").strip().lower()
    data = cargar_datos()
    if numero not in data:
        data[numero] = {"diarios": [], "puntuales": []}
    respuesta = ""

    comandos_ver = ["ver", "ver recordatorios", "qué tengo", "mostrar", "recordatorios"]
    comandos_cancelar = ["cancelar", "salir", "olvidalo", "anular"]

    if mensaje.lower() in comandos_cancelar:
        return responder("🧼 Operación cancelada. Decime si querés guardar un nuevo recordatorio o ver los que ya tenés.")

    if mensaje.lower() in comandos_ver:
        diarios = data[numero]["diarios"]
        puntuales = data[numero]["puntuales"]
        respuesta = "🧠 Tus recordatorios:\n 💊 Diarios:\n "
        if diarios:
            for r in diarios:
                respuesta += f"🕒 {r['hora']} - {r['mensaje']}"
        else:
            respuesta += "Nada guardado."
        respuesta += "📅 Puntuales:"
        if puntuales:
            for r in puntuales:
                respuesta += f"📆 {r['fecha']} {r['hora']} - {r['mensaje']}"
        else:
            respuesta += "Nada guardado."
        return responder(respuesta)

    parsed = interpretar_completo_gpt(mensaje)
    if parsed and "hora" in parsed and "mensaje" in parsed:
        hora = parsed["hora"]
        msg = parsed["mensaje"]
        fecha = parsed.get("fecha")

        if fecha:
            data[numero]["puntuales"].append({"hora": hora, "fecha": fecha, "mensaje": msg})
            respuesta = f"📅 Guardado puntual para el {fecha} a las {hora}: {msg}"
        else:
            data[numero]["diarios"].append({"hora": hora, "mensaje": msg})
            respuesta = f"💊 Guardado diario a las {hora}: {msg}"
        guardar_datos(data)
        return responder(respuesta)

    return responder("🤖 No entendí tu mensaje como un recordatorio. Puedes decir:\n - 'recordame el médico el 18 a las 9'\n - 'tomar pastilla a las 10'\n - o decime 'ver' para mostrar tus recordatorios.")

def responder(texto):
    r = MessagingResponse()
    r.message(texto)
    return Response(str(r), mimetype="application/xml")

print("✅ Asistente v5 iniciado (solo GPT para interpretar horas).")
scheduler = BackgroundScheduler()
scheduler.add_job(revisar_recordatorios, "interval", minutes=1)
scheduler.start()

port = int(os.environ.get("PORT", 5000))
app.run(host="0.0.0.0", port=port)
