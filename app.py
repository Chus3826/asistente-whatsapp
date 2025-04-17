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

# ------------------ Interpretación con GPT ------------------
def interpretar_con_gpt(mensaje):
    print(f"📤 Enviando a GPT: {mensaje}")

    prompt = (
        "Actuá como un asistente para personas mayores que necesita guardar recordatorios médicos. "
        "Tu tarea es analizar el siguiente mensaje y devolver SOLO un JSON con:\n\n"
        "- tipo: 'diario' o 'puntual'\n"
        "- hora: formato HH:MM en 24h (incluso si dicen 'y media', 'y cuarto', 'por la mañana', etc.)\n"
        "- fecha: YYYY-MM-DD si es puntual, null si no aplica (usa la fecha si se menciona, o si dicen 'mañana', etc.)\n"
        "- mensaje: lo que hay que recordar\n\n"
        "⚠️ Si el mensaje no tiene suficiente información como la hora o la fecha, devolvé ese campo como null.\n\n"
        f"Mensaje: {mensaje}\n\n"
        "Ejemplo de respuesta:\n"
        "{\"tipo\": \"puntual\", \"hora\": \"15:30\", \"fecha\": \"2025-04-20\", \"mensaje\": \"cita con el cardiólogo\"}"
    )

    try:
        respuesta = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=250
        )
        contenido = respuesta.choices[0].message.content.strip()
        print("🧠 GPT respondió:", contenido)
        contenido = re.sub(r"^[^{]*", "", contenido)
        contenido = re.sub(r"[^}]*$", "", contenido)
        return json.loads(contenido)
    except Exception as e:
        print("❌ Error usando OpenAI:", e)
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
                enviar_whatsapp(numero, f"🗓️ Cita médica: {r['mensaje']}")

# ------------------ Ruta principal ------------------
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
            "👋 ¡Hola! Soy tu asistente personal de salud.\n"
            "🎉 ¿Qué puedo hacer?\n"
            "- Recordarte tomar tu medicación diaria\n"
            "- Recordarte citas médicas en un día y hora puntual\n"
            "- Mostrar tus recordatorios escribiendo 'ver'\n"
            "📜 Escribí por ejemplo:\n"
            "- pastilla tensión a las 9\n"
            "- médico 17 abril a las 10\n"
            "- ver\n"
            "- eliminar todos o eliminar pastilla\n"
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
        respuesta += "\n🗓️ Puntuales:\n"
        if puntuales:
            for r in puntuales:
                respuesta += f"🗓️ {r['fecha']} {r['hora']} - {r['mensaje']}\n"
        else:
            respuesta += "Nada guardado."

    elif mensaje.lower().startswith("eliminar"):
        partes = mensaje.lower().split(" ", 1)
        if len(partes) == 2 and partes[1] != "todos":
            clave = partes[1]
            prev_diarios = data[numero]["diarios"]
            prev_puntuales = data[numero]["puntuales"]
            data[numero]["diarios"] = [r for r in prev_diarios if clave not in r["mensaje"].lower()]
            data[numero]["puntuales"] = [r for r in prev_puntuales if clave not in r["mensaje"].lower()]
            guardar_datos(data)
            respuesta = f"🔍 Eliminado lo relacionado con '{clave}' si existía."
        else:
            data[numero] = {"diarios": [], "puntuales": []}
            guardar_datos(data)
            respuesta = "🗑️ Todos tus recordatorios fueron eliminados."

    else:
        parsed = interpretar_con_gpt(mensaje)
        if parsed:
            if not parsed.get("hora"):
                respuesta = "🕐 ¿A qué hora querés que te lo recuerde?"
            elif parsed["tipo"] == "puntual" and not parsed.get("fecha"):
                respuesta = "📅 ¿Para qué día es esta cita médica?"
            elif parsed["tipo"] == "puntual":
                data[numero]["puntuales"].append({
                    "fecha": parsed["fecha"],
                    "hora": parsed["hora"],
                    "mensaje": parsed["mensaje"]
                })
                guardar_datos(data)
                respuesta = f"🗓️ Guardado puntual para el {parsed['fecha']} a las {parsed['hora']}: {parsed['mensaje']}"
            else:
                data[numero]["diarios"].append({
                    "hora": parsed["hora"],
                    "mensaje": parsed["mensaje"]
                })
                guardar_datos(data)
                respuesta = f"💊 Guardado diario a las {parsed['hora']}: {parsed['mensaje']}"
        else:
            respuesta = (
                "❓ Disculpá, no entendí bien el mensaje. ¿Podrías decirlo con algo como:\n"
                "- pastilla tensión a las 9\n"
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
