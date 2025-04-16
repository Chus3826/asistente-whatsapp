from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
import json, os, re
from datetime import datetime
from twilio.rest import Client
from apscheduler.schedulers.background import BackgroundScheduler
from pytz import timezone
from dateparser.search import search_dates
import openai

app = Flask(__name__)
DB_FILE = "recordatorios.json"
openai.api_key = os.environ.get("OPENAI_API_KEY")

TWILIO_PHONE = os.environ.get("TWILIO_PHONE")
client = Client(os.environ.get("TWILIO_SID"), os.environ.get("TWILIO_AUTH_TOKEN"))

# -----------------------------------------
def cargar_datos():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return json.load(f)
    return {}

def guardar_datos(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f)

# -----------------------------------------
def enviar_whatsapp(to, body):
    try:
        client.messages.create(from_=TWILIO_PHONE, to=to, body=body)
        print(f"✅ Enviado a {to}: {body}")
    except Exception as e:
        print(f"❌ Error al enviar a {to}: {e}")

# -----------------------------------------
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

# -----------------------------------------
def interpretar_con_gpt(mensaje):
    prompt = f"Extraé fecha, hora y mensaje de esta cita médica. Respondé solo en JSON con 'fecha', 'hora' y 'mensaje'. Texto: {mensaje}"
    try:
        respuesta = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.3
        )
        contenido = respuesta.choices[0].message.content.strip()
        contenido = re.sub(r"^[^\{]*", "", contenido)
        contenido = re.sub(r"[^\}]*$", "", contenido)
        return json.loads(contenido)
    except Exception as e:
        print("❌ Error usando OpenAI:", e)
        return None

# -----------------------------------------
@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    mensaje = request.form.get("Body").strip()
    numero = request.form.get("From").strip().lower()
    data = cargar_datos()
    bienvenida = ""

    if numero not in data:
        data[numero] = {"diarios": [], "puntuales": [], "saludo": True}
        guardar_datos(data)

    if data[numero].get("saludo"):
        bienvenida = (
            "👋 ¡Hola! Soy tu asistente personal de salud.\n"
            "🎉 ¿Qué puedo hacer?\n"
            "- Recordarte tomar tu medicación diaria\n"
            "- Recordarte citas médicas en un día y hora puntual\n"
            "- Mostrar tus recordatorios escribiendo 'ver'\n"
            "🔹 Por ejemplo:\n"
            "- Tomar la pastilla de la tensión todos los días a las 9\n"
            "- Cita con el médico el 18 de abril a las 10:30\n"
            "- ver para tus recordatorios"
        )
        data[numero]["saludo"] = False
        guardar_datos(data)

    # --------------------------
    if mensaje.lower() == "ver":
        diarios = data[numero]["diarios"]
        puntuales = data[numero]["puntuales"]
        respuesta = "\U0001f9e0 Tus recordatorios:\n\n💉 Diarios:\n"
        respuesta += "\n".join([f"🕒 {r['hora']} - {r['mensaje']}" for r in diarios]) if diarios else "Nada guardado."
        respuesta += "\n\n📅 Puntuales:\n"
        respuesta += "\n".join([f"🗓️ {r['fecha']} {r['hora']} - {r['mensaje']}" for r in puntuales]) if puntuales else "Nada guardado."

    elif "cita" in mensaje.lower():
        parsed = interpretar_con_gpt(mensaje)
        if parsed and "hora" in parsed and "fecha" in parsed and "mensaje" in parsed:
            data[numero]["puntuales"].append(parsed)
            guardar_datos(data)
            respuesta = f"📅 Cita guardada para el {parsed['fecha']} a las {parsed['hora']}: {parsed['mensaje']}"
        else:
            respuesta = "⚠️ No entendí la cita. Intentá de otra forma."

    elif any(k in mensaje.lower() for k in ["pastilla", "medicina", "tengo que", "me toca", "recordame"]):
        fechas = search_dates(mensaje, languages=["es"], settings={"PREFER_DATES_FROM": "future"})
        if fechas:
            _, fh = fechas[0]
            hora = fh.strftime("%H:%M")
            texto = mensaje.replace(fechas[0][0], "").strip()
            data[numero]["diarios"].append({"hora": hora, "mensaje": texto})
            guardar_datos(data)
            respuesta = f"💉 Guardado diario a las {hora}: {texto}"
        else:
            respuesta = "⚠️ No entendí la hora. Probá algo como 'a las 9'."

    else:
        respuesta = "🤖 Solo puedo ayudarte con recordatorios de medicación diaria y citas médicas. Escribí 'ver' para ver los tuyos."

    r = MessagingResponse()
    if bienvenida:
        r.message(bienvenida)
    r.message(respuesta)
    return Response(str(r), mimetype="application/xml")

# --------------------------
print("✅ Asistente listo")
scheduler = BackgroundScheduler()
scheduler.add_job(revisar_recordatorios, "interval", minutes=1)
scheduler.start()
port = int(os.environ.get("PORT", 5000))
app.run(host="0.0.0.0", port=port)
