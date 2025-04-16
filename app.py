from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
import json, os, re
from datetime import datetime
from twilio.rest import Client
from apscheduler.schedulers.background import BackgroundScheduler
from pytz import timezone
import openai

app = Flask(__name__)
DB_FILE = "recordatorios.json"

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

def interpretar_con_gpt(mensaje):
    prompt = (
        "Actuá como un asistente de salud para personas mayores. Interpretá el mensaje, detectá si se trata de una cita médica o una medicación diaria y devolvé SOLO un JSON con:
"
        "- tipo: 'diario' o 'puntual'
"
        "- hora: en formato HH:MM (24 horas)
"
        "- fecha: formato YYYY-MM-DD o null si no aplica
"
        "- mensaje: el texto a recordar
"
        "Ejemplo: {"tipo": "diario", "hora": "08:30", "fecha": null, "mensaje": "tomar pastilla de la tensión"}
"
        f"Mensaje: {mensaje}"
    )

    try:
        respuesta = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=150
        )
        contenido = respuesta.choices[0].message.content.strip()
        print("🧠 GPT respondió:", contenido)
        contenido = re.sub(r"^[^{]*", "", contenido)
        contenido = re.sub(r"[^}]*$", "", contenido)
        return json.loads(contenido)
    except Exception as e:
        print("❌ Error usando OpenAI:", e)
        return None

def revisar_recordatorios():
    print("⏰ [Scheduler activo] Revisando recordatorios...")
    data = cargar_datos()
    zona_local = timezone("Europe/Madrid")
    ahora = datetime.now(zona_local).strftime("%H:%M")
    hoy = datetime.now(zona_local).strftime("%Y-%m-%d")

    for numero, recordatorios in data.items():
        for r in recordatorios.get("diarios", []):
            if r["hora"] == ahora:
                enviar_whatsapp(numero, f"💊 Recordatorio diario: {r['mensaje']}")
        for r in recordatorios.get("puntuales", []):
            if r["fecha"] == hoy and r["hora"] == ahora:
                enviar_whatsapp(numero, f"📅 Cita médica: {r['mensaje']}")

@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    mensaje = request.form.get("Body").strip()
    numero = request.form.get("From").strip().lower()
    data = cargar_datos()

    if numero not in data:
        data[numero] = {"diarios": [], "puntuales": []}
        guardar_datos(data)

    if mensaje.lower() in ["hola", "hi"]:
        bienvenida = (
            "👋 ¡Hola! Soy tu asistente personal de salud.
"
            "🎉 ¿Qué puedo hacer?
"
            "- Recordarte tomar tu medicación diaria
"
            "- Recordarte citas médicas en un día y hora puntual
"
            "- Mostrar tus recordatorios escribiendo 'ver'
"
            "📝 Escribí por ejemplo:
"
            "- pastilla tensión a las 9
"
            "- médico 17 abril a las 10
"
            "- ver"
        )
        r = MessagingResponse()
        r.message(bienvenida)
        return Response(str(r), mimetype="application/xml")

    if mensaje.lower() == "ver":
        diarios = data[numero]["diarios"]
        puntuales = data[numero]["puntuales"]
        respuesta = "🧠 Tus recordatorios:

💊 Diarios:
"
        if diarios:
            for r in diarios:
                respuesta += f"🕒 {r['hora']} - {r['mensaje']}
"
        else:
            respuesta += "Nada guardado.
"
        respuesta += "
📅 Puntuales:
"
        if puntuales:
            for r in puntuales:
                respuesta += f"📆 {r['fecha']} {r['hora']} - {r['mensaje']}
"
        else:
            respuesta += "Nada guardado."
    else:
        parsed = interpretar_con_gpt(mensaje)
        if parsed and "hora" in parsed and "mensaje" in parsed and parsed.get("tipo"):
            if parsed["tipo"] == "puntual" and parsed.get("fecha"):
                data[numero]["puntuales"].append({
                    "fecha": parsed["fecha"],
                    "hora": parsed["hora"],
                    "mensaje": parsed["mensaje"]
                })
                respuesta = f"📅 Guardado puntual para el {parsed['fecha']} a las {parsed['hora']}: {parsed['mensaje']}"
            else:
                data[numero]["diarios"].append({
                    "hora": parsed["hora"],
                    "mensaje": parsed["mensaje"]
                })
                respuesta = f"💉 Guardado diario a las {parsed['hora']}: {parsed['mensaje']}"
            guardar_datos(data)
        else:
            respuesta = (
                "❌ No entendí el mensaje. Probá con frases como:
"
                "- pastilla tensión a las 9
"
                "- médico el 18 de abril a las 10"
            )

    r = MessagingResponse()
    r.message(respuesta)
    return Response(str(r), mimetype="application/xml")

print("✅ Asistente GPT activo")
scheduler = BackgroundScheduler()
scheduler.add_job(revisar_recordatorios, "interval", minutes=1)
scheduler.start()
port = int(os.environ.get("PORT", 5000))
app.run(host="0.0.0.0", port=port)