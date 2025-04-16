from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
import json, os, re
from datetime import datetime
from twilio.rest import Client
from apscheduler.schedulers.background import BackgroundScheduler
from pytz import timezone
from dateparser.search import search_dates
import dateparser

app = Flask(__name__)
DB_FILE = "recordatorios.json"

# Configurar cliente Twilio y claves API
TWILIO_PHONE = os.environ.get("TWILIO_PHONE")
client = Client(os.environ.get("TWILIO_SID"), os.environ.get("TWILIO_AUTH_TOKEN"))

# ---------------------------- Funciones auxiliares ----------------------------
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

# ------------------------- Revisión periódica -------------------------------
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
                enviar_whatsapp(numero, f"📅 Cita médica: {r['mensaje']}")

# -------------------------- Mensaje de bienvenida ----------------------------
def bienvenida():
    return ("👋 ¡Hola! Soy tu asistente personal de salud.\n"
            "🎉 ¿Qué puedo hacer?\n"
            "- Recordarte tomar tu medicación diaria\n"
            "- Recordarte citas médicas en un día y hora puntual\n"
            "- Mostrar tus recordatorios escribiendo 'ver'\n"
            "🔹 Por ejemplo:\n"
            "- Tomar la pastilla de la tensión todos los días a las 9\n"
            "- Cita con el médico el 18 de abril a las 10:30\n"
            "- ver para tus recordatorios")

# ------------------------- Ruta principal WhatsApp ---------------------------
@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    mensaje = request.form.get("Body").strip()
    numero = request.form.get("From").strip().lower()
    data = cargar_datos()
    nueva_conversacion = False

    if numero not in data:
        data[numero] = {"diarios": [], "puntuales": []}
        nueva_conversacion = True

    respuesta = ""

    if nueva_conversacion:
        respuesta += bienvenida() + "\n\n"

    if mensaje.lower() == "ver":
        diarios = data[numero]["diarios"]
        puntuales = data[numero]["puntuales"]
        respuesta += "🧠 Tus recordatorios:\n\n💉 Diarios:\n"
        if diarios:
            for r in diarios:
                respuesta += f"🕒 {r['hora']} - {r['mensaje']}\n"
        else:
            respuesta += "Nada guardado.\n"
        respuesta += "\n📅 Puntuales:\n"
        if puntuales:
            for r in puntuales:
                respuesta += f"🗓️ {r['fecha']} {r['hora']} - {r['mensaje']}\n"
        else:
            respuesta += "Nada guardado."

    elif any(k in mensaje.lower() for k in ["pastilla", "medicina", "recordame", "cita", "tengo que", "me toca"]):
        fechas = search_dates(mensaje, languages=["es"], settings={"PREFER_DATES_FROM": "future"})
        if fechas:
            _, fh = fechas[0]
            hora = fh.strftime("%H:%M")
            texto = mensaje.replace(fechas[0][0], "").strip()

            if re.search(r"\d{1,2} de \w+", mensaje.lower()) or "cita" in mensaje.lower():
                fecha = fh.strftime("%Y-%m-%d")
                data[numero]["puntuales"].append({"fecha": fecha, "hora": hora, "mensaje": texto})
                respuesta += f"📅 Guardado puntual para el {fecha} a las {hora}: {texto}"
            else:
                data[numero]["diarios"].append({"hora": hora, "mensaje": texto})
                respuesta += f"💉 Guardado diario a las {hora}: {texto}"
            guardar_datos(data)
        else:
            respuesta += "⚠️ No entendí la hora. Probá algo como 'a las 9'."

    else:
        respuesta += "🤖 Solo puedo ayudarte con recordatorios de medicación diaria y citas médicas. Escribí 'ver' para ver los tuyos."

    r = MessagingResponse()
    r.message(respuesta)
    return Response(str(r), mimetype="application/xml")

# --------------------------- Iniciar Flask + Scheduler ------------------------
print("✅ Asistente listo")
scheduler = BackgroundScheduler()
scheduler.add_job(revisar_recordatorios, "interval", minutes=1)
scheduler.start()
port = int(os.environ.get("PORT", 5000))
app.run(host="0.0.0.0", port=port)
