from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
import os
import openai
import re
import json

app = Flask(__name__)
openai.api_key = os.environ.get("OPENAI_API_KEY")

@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    mensaje = request.form.get("Body", "").strip()
    numero = request.form.get("From", "").strip().lower()

    print(f"📥 Mensaje recibido: {mensaje} de {numero}")

    prompt = (
        "Sos un asistente para personas mayores que guarda recordatorios médicos. "
        "Extraé tipo ('diario' o 'puntual'), hora (HH:MM), fecha (YYYY-MM-DD o null), mensaje. "
        "Devolvé solo un JSON."
        f"Mensaje: {mensaje}\n"
    )

    try:
        print("📡 Enviando a GPT...")
        respuesta = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.2
        )
        contenido = respuesta.choices[0].message.content.strip()
        print("🧠 GPT respondió:", contenido)

        # Limpiar por si el JSON viene con texto extra
        contenido = re.sub(r"^[^{]*", "", contenido)
        contenido = re.sub(r"[^}]*$", "", contenido)
        parsed = json.loads(contenido)

        respuesta = f"📌 Tipo: {parsed['tipo']}\n🕒 Hora: {parsed['hora']}\n📅 Fecha: {parsed['fecha']}\n📝 Mensaje: {parsed['mensaje']}"

    except Exception as e:
        print("❌ Error al interpretar con GPT:", e)
        respuesta = "😕 No entendí el mensaje. Por favor, escribilo como: 'pastilla tensión a las 9' o 'médico 18 abril a las 10'."

    r = MessagingResponse()
    r.message(respuesta)
    return Response(str(r), mimetype="application/xml")

print("✅ Mini asistente de prueba activo")
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

