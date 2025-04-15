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
    prompt = f"Extraé la hora, el mensaje y la fecha (si hay) de este texto para un recordatorio. Respondé en JSON: 'hora', 'mensaje', y opcionalmente 'fecha'. Texto: {mensaje}"
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
    except:
        return None

def detectar_hora(texto):
    reemplazos = {
        "y media": ":30",
        "y cuarto": ":15",
        "menos cuarto": ":45"
    }
    for k, v in reemplazos.items():
        if k in texto:
            texto = texto.replace(k, v)
    coincidencias = search_dates(texto, languages=["es"], settings={"PREFER_DATES_FROM": "future"})
    if coincidencias:
        _, dt = coincidencias[0]
        return dt.strftime("%H:%M")
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

    comandos_ver = ["ver", "ver recordatorios", "qué tengo", "que tengo", "mostrar", "recordatorios"]
    comandos_cancelar = ["cancelar", "salir", "borrar", "olvidalo"]

    # Si usuario quiere salir
    if mensaje.lower() in comandos_cancelar:
        if numero in temp:
            temp.pop(numero)
            guardar_temporal(temp)
        return responder("🧼 He cancelado la operación anterior. ¿En qué te puedo ayudar ahora?")

    # Mostrar recordatorios
    if mensaje.lower() in comandos_ver:
        diarios = data[numero]["diarios"]
        puntuales = data[numero]["puntuales"]
        respuesta = "🧠 Tus recordatorios:💊 Diarios:"
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

    if numero in temp:
        contexto = temp[numero]
        intentos = contexto.get("intentos", 0)

        if contexto["fase"] == "hora":
            hora = detectar_hora(mensaje)
            if hora:
                contexto["hora"] = hora
                contexto["fase"] = "frecuencia"
                contexto["intentos"] = 0
                guardar_temporal(temp)
                return responder("🔁 ¿Querés que te lo recuerde todos los días o solo una vez?")
            else:
                contexto["intentos"] = intentos + 1
                guardar_temporal(temp)
                if contexto["intentos"] >= 2:
                    temp.pop(numero)
                    guardar_temporal(temp)
                    return responder("❌ No entendí la hora. Cancelé la operación. Podés decirme 'ver' o empezar de nuevo.")
                return responder("❌ No entendí la hora. Probá algo como 'a las 9'.")
        
        elif contexto["fase"] == "frecuencia":
            msg = contexto["mensaje"]
            hora = contexto["hora"]
            fecha = contexto.get("fecha")
            if "una vez" in mensaje.lower() or "puntual" in mensaje.lower():
                if not fecha:
                    fecha = datetime.now(timezone("Europe/Madrid")).strftime("%Y-%m-%d")
                data[numero]["puntuales"].append({"hora": hora, "fecha": fecha, "mensaje": msg})
                respuesta = f"📅 Guardado puntual para el {fecha} a las {hora}: {msg}"
            else:
                data[numero]["diarios"].append({"hora": hora, "mensaje": msg})
                respuesta = f"💊 Guardado diario a las {hora}: {msg}"
            guardar_datos(data)
            temp.pop(numero)
            guardar_temporal(temp)
            return responder(respuesta)

    parsed = interpretar_con_gpt(mensaje)
    if parsed and "mensaje" in parsed:
        if any(p in mensaje.lower() for p in ["recordar", "recordame", "apuntame", "tomar", "pastilla", "medico", "medicación", "medicina", "tengo que"]):
            temp[numero] = {
                "fase": "hora",
                "mensaje": parsed["mensaje"],
                "fecha": parsed.get("fecha"),
                "intentos": 0
            }
            guardar_temporal(temp)
            return responder("⏰ ¿A qué hora querés que te lo recuerde?")
    
    return responder("🤖 No entendí el mensaje. Probá con algo como:- 'tomar pastilla a las 9'- 'recordame la cita el 20 de abril'- o decime 'ver' para mostrar tus recordatorios.")

def responder(texto):
    r = MessagingResponse()
    r.message(texto)
    return Response(str(r), mimetype="application/xml")

print("✅ Asistente v4 iniciado con tolerancia a errores.")
scheduler = BackgroundScheduler()
scheduler.add_job(revisar_recordatorios, "interval", minutes=1)
scheduler.start()

port = int(os.environ.get("PORT", 5000))
app.run(host="0.0.0.0", port=port)
