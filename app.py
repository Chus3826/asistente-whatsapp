from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
import os
import openai
import re
import json

app = Flask(__name__)

# Verificación explícita de la API key al inicio
oai_key = os.environ.get("OPENAI_API_KEY")
print("🔑 OPENAI_API_KEY cargada:", "Sí" if oai_key else "No")
openai.api_key = oai_key

# Memoria temporal en RAM por usuario
memoria = {}

@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    print("📬 request.form completo:", dict(request.form))

    mensaje = request.form.get("Body")
    numero = request.form.get("From")

    if not mensaje:
        print("⚠️ Body no encontrado en request.form")
        mensaje = ""
    else:
        mensaje = mensaje.strip()

    if not numero:
        print("⚠️ From no encontrado en request.form")
        numero = ""
    else:
        numero = numero.strip().lower()

    print(f"📥 Mensaje recibido: '{mensaje}' de '{numero}'")

    if numero not in memoria:
        memoria[numero] = {"diarios": [], "puntuales": []}

    if mensaje.lower() == "ver":
        diarios = memoria[numero]["diarios"]
        puntuales = memoria[numero]["puntuales"]
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
        print("🧪 Lógica de GPT activada")
        prompt = (
            "Sos un asistente para personas mayores que guarda recordatorios médicos. "
            "Extraé tipo ('diario' o 'puntual'), hora (HH:MM), fecha (YYYY-MM-DD o null), mensaje. "
            "Devolvé solo un JSON.\n"
            f"Mensaje: {mensaje}\n"
        )

        print("📡 Enviando mensaje a GPT...")
        print("🧾 Prompt enviado a GPT:\n", prompt)

        try:
            respuesta_gpt = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0.2
            )
            contenido = respuesta_gpt.choices[0].message.content.strip()
            print("🧠 GPT respondió:", contenido)

            contenido = re.sub(r"^[^{]*", "", contenido)
            contenido = re.sub(r"[^}]*$", "", contenido)
            parsed = json.loads(contenido)

            if parsed["tipo"] == "diario":
                memoria[numero]["diarios"].append({"hora": parsed["hora"], "mensaje": parsed["mensaje"]})
                respuesta = f"💊 Guardado diario a las {parsed['hora']}: {parsed['mensaje']}"
            else:
                memoria[numero]["puntuales"].append({"fecha": parsed["fecha"], "hora": parsed["hora"], "mensaje": parsed["mensaje"]})
                respuesta = f"📅 Guardado puntual para el {parsed['fecha']} a las {parsed['hora']}: {parsed['mensaje']}"

        except Exception as e:
            print("❌ Error al interpretar con GPT:", e)
            respuesta = "😕 No entendí el mensaje. Probá escribir algo como 'tomar pastilla a las 9' o 'cita con el médico el 18 de abril a las 10'."

    r = MessagingResponse()
    r.message(respuesta)
    return Response(str(r), mimetype="application/xml")

print("✅ Mini asistente de prueba activo")
if __name__ == "__main__":
    print("🚀 Ejecutando archivo:", __name__)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
