import os
import io
import discord
from google import genai
from google.genai import types

# Configuración básica de intents para el bot de Discord
intents = discord.Intents.default()
intents.message_content = True

client_discord = discord.Client(intents=intents)

# Inicializa el cliente de la API de Gemini (toma automáticamente la GEMINI_API_KEY de las variables de entorno)
ai_client = genai.Client()

@client_discord.event
async def on_ready():
    print(f"horario-bot: Bot conectado como {client_discord.user}")

def extract_text_from_image(image_bytes: bytes, language: str = "es") -> str:
    """
    Extrae y analiza los horarios de la imagen utilizando la IA de Google Gemini.
    """
    try:
        response = ai_client.models.generate_content(
            model='gemini-3.6-flash',
            contents=[
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type='image/png',
                ),
                (
                    "Eres un asistente experto en lectura de datos y horarios de videojuegos. "
                    "Analiza esta imagen y extrae de forma limpia, estructurada y ordenada todos los "
                    "horarios, nombres de eventos, fechas o datos numéricos que aparezcan."
                )
            ]
        )
        if response and response.text:
            return response.text.strip()
        return ""
    except Exception as e:
        print(f"Error procesando la imagen con la IA: {e}")
        return ""

@client_discord.event
async def on_message(message):
    # Evitar que el bot se responda a sí mismo
    if message.author == client_discord.user:
        return

    # Verificar si el mensaje contiene imágenes adjuntas
    if message.attachments:
        for attachment in message.attachments:
            if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                print(f"Procesando imagen adjunta: {attachment.filename}")
                try:
                    # Descargar los bytes de la imagen directamente desde Discord
                    image_bytes = await attachment.read()
                    
                    # Llamar a la función de IA para extraer el texto/horarios
                    extracted_text = extract_text_from_image(image_bytes)
                    
                    if extracted_text:
                        print(f"Texto extraído con éxito:\n{extracted_text}")
                        # Aquí puedes continuar con tu lógica interna (ej. sincronizar a OneDrive/Excel)
                        # Nota: Se eliminaron los mensajes automáticos de respuesta al canal de Discord.
                    else:
                        print("⚠️ No se pudo extraer texto o datos claros de la imagen.")
                        
                except Exception as e:
                    print(f"Error inesperado procesando {attachment.filename}: {e}")

# Token del bot cargado desde las variables de entorno de Railway
TOKEN = os.getenv("DISCORD_TOKEN")

if __name__ == "__main__":
    if not TOKEN:
        print("ERROR: No se encontró la variable de entorno DISCORD_TOKEN.")
    else:
        client_discord.run(TOKEN)
