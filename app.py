from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
import os
import openai

app = Flask(__name__)
openai.api_key = os.environ.get("OPENAI_API_KEY")

@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    mensaje = request.form.get("Body", "").strip()
    numero = request.form.get("From", "").strip().lower()
    print(f"📥 Mensaje recibido de {numero}: {mensaje}")

    prompt = f"Respondé con un mensaje amistoso que diga que recibiste: '{mensaje}'"

    try:
        print("📡 Enviando a GPT...")
        respuesta = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=50,
            temperature=0.5
        )
        contenido = respuesta.choices[0].message.content.strip()
        print("🧠 GPT respondió:", contenido)
        respuesta_final = contenido
    except Exception as e:
        print("❌ Error al contactar con GPT:", e)
        respuesta_final = "❌ No pude contactar con el asistente en este momento."

    r = MessagingResponse()
    r.message(respuesta_final)
    return Response(str(r), mimetype="application/xml")

print("✅ Asistente mínimo con GPT activo")
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))



