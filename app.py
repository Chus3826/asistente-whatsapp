from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
import json
import os

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

@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    mensaje = request.form.get("Body").strip().lower()
    numero = request.form.get("From").strip().lower()
    data = cargar_datos()

    if numero not in data:
        data[numero] = {"diarios": [], "puntuales": []}

    respuesta = ""

    if mensaje.startswith("medicacion"):
        try:
            _, hora, texto = mensaje.split(" ", 2)
            data[numero]["diarios"].append({"hora": hora, "mensaje": texto})
            guardar_datos(data)
            respuesta = f"💊 Recordatorio diario guardado para las {hora}: {texto}"
        except:
            respuesta = "❌ Usa: medicacion HH:MM tu mensaje"

    elif mensaje.startswith("cita"):
        try:
            _, fecha, hora, texto = mensaje.split(" ", 3)
            data[numero]["puntuales"].append({"fecha": fecha, "hora": hora, "mensaje": texto})
            guardar_datos(data)
            respuesta = f"📅 Cita guardada para el {fecha} a las {hora}: {texto}"
        except:
            respuesta = "❌ Usa: cita YYYY-MM-DD HH:MM tu mensaje"

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


    elif mensaje.startswith("eliminar "):
        hora_borrar = mensaje.split(" ", 1)[1]
        originales = len(data[numero]["diarios"])
        data[numero]["diarios"] = [r for r in data[numero]["diarios"] if r["hora"] != hora_borrar]
        if len(data[numero]["diarios"]) < originales:
            guardar_datos(data)
            respuesta = f"🗑️ Eliminado recordatorio diario a las {hora_borrar}."
        else:
            respuesta = "❌ No se encontró ese recordatorio diario."

    elif mensaje.startswith("eliminar_cita "):
        try:
            _, fecha, hora = mensaje.split(" ")
            originales = len(data[numero]["puntuales"])
            data[numero]["puntuales"] = [
                r for r in data[numero]["puntuales"] if not (r["fecha"] == fecha and r["hora"] == hora)
            ]
            if len(data[numero]["puntuales"]) < originales:
                guardar_datos(data)
                respuesta = f"🗑️ Cita eliminada para {fecha} a las {hora}."
            else:
                respuesta = "❌ No se encontró esa cita."
        except:
            respuesta = "❌ Usa: eliminar_cita YYYY-MM-DD HH:MM"

    else:
        respuesta = (
            "🤖 Comandos disponibles:
"
            "- medicacion HH:MM mensaje
"
            "- cita YYYY-MM-DD HH:MM mensaje
"
            "- ver
"
            "- eliminar HH:MM
"
            "- eliminar_cita YYYY-MM-DD HH:MM"
        )

    r = MessagingResponse()
    r.message(respuesta)
    return Response(str(r), mimetype="application/xml")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
