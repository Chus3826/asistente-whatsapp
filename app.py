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

# ------------------ Utilidades ------------------
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

# ------------------ Lógica GPT ------------------
def interpretar_mensaje_con_gpt(texto):
    prompt = f"""
Actuá como un asistente que guarda recordatorios médicos. Analizá este mensaje y devolvé SOLO un JSON con los siguientes campos:
- tipo: 'diario' o 'puntual'
- hora: en formato HH:MM
- fecha: solo si es puntual, en formato YYYY-MM-DD (o null)
- mensaje: el contenido del recordatorio

Mensaje: "{texto}"

Ejemplo de respuesta:
{{"tipo": "diario", "hora": "09:00", "fecha": null, "mensaje": "tomar pastilla de la tensión"}}
"""
    try:
        respuesta = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.3
        )
        texto_json = respuesta.choices[0].message.content.strip()
        print("🧠 GPT:", texto_json)
        return json.loads(re.sub(r".*?(\{.*\})", r"\1", texto_json, flags=re.DOTALL))
    except Exception as e:
        print("❌ Error con GPT:", e)
        return None

# ------------------ Revisar recordatorios ------------------
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

# ------------------ Ruta principal ------------------
@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    mensaje = request.form.get("Body").strip()
    numero = request.form.get("From").strip().lower()
    data = cargar_datos()

    if numero not in data:
        data[numero] = {"diarios": [], "puntuales": []}
        guardar_datos(data)
        bienvenida = (
            "👋 ¡Hola! Soy tu asistente personal de salud.\n"
            "🎉 ¿Qué puedo hacer?\n"
            "- Recordarte tomar tu medicación diaria\n"
            "- Recordarte citas médicas en un día y hora puntual\n"
            "- Mostrar tus recordatorios escribiendo 'ver'\n"
            "🔷 Por ejemplo:\n"
            "- Tomar la pastilla de la tensión todos los días a las 9\n"
            "- Cita con el médico el 18 de abril a las 10:30\n"
            "- ver para tus recordatorios"
        )
        r = MessagingResponse()
        r.message(bienvenida)
        return Response(str(r), mimetype="application/xml")

    if mensaje.lower() == "ver":
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
        resultado = interpretar_mensaje_con_gpt(mensaje)
        if resultado and "hora" in resultado and "mensaje" in resultado and resultado.get("tipo") in ["diario", "puntual"]:
            if resultado["tipo"] == "diario":
                data[numero]["diarios"].append({"hora": resultado["hora"], "mensaje": resultado["mensaje"]})
                respuesta = f"💊 Guardado diario a las {resultado['hora']}: {resultado['mensaje']}"
            else:
                data[numero]["puntuales"].append({"fecha": resultado["fecha"], "hora": resultado["hora"], "mensaje": resultado["mensaje"]})
                respuesta = f"📅 Guardado puntual para el {resultado['fecha']} a las {resultado['hora']}: {resultado['mensaje']}"
            guardar_datos(data)
        else:
            respuesta = "🤖 Solo puedo ayudarte con recordatorios de medicación diaria y citas médicas. Escribí 'ver' para ver los tuyos."

    r = MessagingResponse()
    r.message(respuesta)
    return Response(str(r), mimetype="application/xml")

print("✅ Asistente GPT activo")
scheduler = BackgroundScheduler()
scheduler.add_job(revisar_recordatorios, "interval", minutes=1)
scheduler.start()
port = int(os.environ.get("PORT", 5000))
app.run(host="0.0.0.0", port=port)
