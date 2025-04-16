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
def interpretar_con_gpt(mensaje):
    prompt = (
        "Analizá este texto y extraé si se trata de una cita médica puntual o un recordatorio diario. "
        "Devuelve un JSON con las claves: tipo ('puntual' o 'diario'), hora (formato HH:MM), "
        "fecha (formato YYYY-MM-DD o null si no aplica), y mensaje (lo que hay que recordar).\n"
        "Ejemplo de respuesta: {\"tipo\": \"diario\", \"hora\": \"09:00\", \"fecha\": null, \"mensaje\": \"tomar la pastilla\"}.\n"
        f"Texto: {mensaje}"
    )

    try:
        respuesta = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=100
        )
        contenido = respuesta.choices[0].message.content.strip()
        print("🧠 GPT respondió:", contenido)

        # Limpiar si el modelo devuelve texto extra
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
        fechas = search_dates(mensaje, languages=["es"], settings={"PREFER_DATES_FROM": "future"})
        if fechas:
            _, fh = fechas[0]
            hora = fh.strftime("%H:%M")
            texto = mensaje.replace(fechas[0][0], "").strip()

            if re.search(r"\d{4}-\d{2}-\d{2}", fh.isoformat()):
                fecha = fh.strftime("%Y-%m-%d")
                data[numero]["puntuales"].append({
                    "fecha": fecha,
                    "hora": hora,
                    "mensaje": texto
                })
                respuesta = f"📅 Guardado puntual para el {fecha} a las {hora}: {texto}"
            else:
                data[numero]["diarios"].append({
                    "hora": hora,
                    "mensaje": texto
                })
                respuesta = f"💉 Guardado diario a las {hora}: {texto}"
            guardar_datos(data)
        else:
            print("⚠️ No se detectó hora. Usando GPT...")
            parsed = interpretar_con_gpt(mensaje)
            if parsed and "hora" in parsed and "mensaje" in parsed:
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
                    "❌ No pude entender el mensaje ni con ayuda. "
                    "Probá con frases como:\n"
                    "- Tomar la pastilla todos los días a las 9\n"
                    "- Médico el 18 de abril a las 10"
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
