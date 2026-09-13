import os
import io
import threading
from flask import Flask
import discord
import openpyxl
from google import genai
from google.genai import types

# --- SERVIDOR WEB PARA UPTIMEROBOT ---
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Bot de Lineage II activo y despierto 24/7!"

def run_web():
    # Railway asigna automáticamente el puerto en la variable PORT (por defecto 8080)
    port = int(os.getenv("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- CONFIGURACIÓN DEL BOT DE DISCORD ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
EXCEL_FILE_PATH = "tu_archivo.xlsx"  # Cambia esto por el nombre real de tu archivo Excel en GitHub

intents = discord.Intents.default()
intents.message_content = True
client_discord = discord.Client(intents=intents)

ai_client = genai.Client(api_key=GEMINI_API_KEY)

@client_discord.event
async def on_ready():
    print(f"🤖 Bot conectado exitosamente como {client_discord.user}")

@client_discord.event
async def on_message(message):
    if message.author == client_discord.user:
        return

    content = message.content.lower().strip()

    # Comando para enviar la imagen vinculada del Excel a Discord
    if content == "!horario":
        print("🖼️ Buscando la imagen unificada de horarios en el Excel...")
        if not os.path.exists(EXCEL_FILE_PATH):
            await message.channel.send("⚠️ No se encontró el archivo Excel en el servidor.")
            return

        try:
            # Abrimos el Excel en modo lectura (data_only para leer valores de fórmulas)
            wb = openpyxl.load_workbook(EXCEL_FILE_PATH, data_only=True)
            
            if "IMAGEN_HORARIO" in wb.sheetnames:
                sheet = wb["IMAGEN_HORARIO"]
                if hasattr(sheet, '_images') and sheet._images:
                    # Extraemos la imagen vinculada del contenedor
                    img = sheet._images[0]
                    img_data = img._data()
                    
                    if img_data:
                        file_to_send = discord.File(io.BytesIO(img_data), filename="Horario_OKT_HTF.png")
                        await message.channel.send(
                            "⚔️ **Horarios Oficiales - OKT & HTF Ally** ⚔️", 
                            file=file_to_send
                        )
                        print("✅ Imagen de horarios enviada con éxito a Discord.")
                        return

            await message.channel.send("⚠️ No se encontró ninguna imagen incrustada en la hoja 'IMAGEN_HORARIO'. Asegúrate de haber pegado la imagen vinculada allí.")

        except Exception as e:
            print(f"Error al enviar la imagen de horarios: {e}")
            await message.channel.send(f"❌ Ocurrió un error al procesar la imagen: {e}")

    # Lógica para procesar capturas subidas al chat con IA
    if message.attachments:
        for attachment in message.attachments:
            if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                print(f"📸 Procesando captura de Discord: {attachment.filename}")
                try:
                    image_bytes = await attachment.read()
                    response = ai_client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=[
                            types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                            "Extrae el nombre de cada raid, si está vivo (true/false), su hora y fecha para actualizar la plantilla."
                        ]
                    )
                    if response and response.text:
                        print(f"--- DATOS EXTRAÍDOS --- \n{response.text.strip()}")
                    await message.delete()
                except Exception as e:
                    print(f"Error procesando imagen de Discord con IA: {e}")

# --- INICIO DE AMBOS PROCESOS (Web + Discord) ---
if __name__ == "__main__":
    # 1. Arrancamos el servidor web en un hilo aparte para que UptimeRobot lo vigile
    t = threading.Thread(target=run_web)
    t.daemon = True
    t.start()
    
    # 2. Arrancamos el bot de Discord
    client_discord.run(DISCORD_TOKEN)
