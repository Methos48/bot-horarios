import os
import io
import discord
from google import genai
from google.genai import types

# Configuración básica de intents para el bot de Discord
intents = discord.Intents.default()
intents.message_content = True

client_discord = discord.Client(intents=intents)

# Inicializa el cliente de la API de Gemini
ai_client = genai.Client()

@client_discord.event
async def on_ready():
    print(f"horario-bot: Bot conectado como {client_discord.user}")

def extract_text_from_image(image_bytes: bytes, mime_type: str = "image/png") -> str:
    """
    Extrae y analiza los horarios de la imagen utilizando la IA de Google Gemini.
    """
    try:
        response = ai_client.models.generate_content(
            model='gemini-3.6-flash',
            contents=[
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=mime_type,
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
            filename_lower = attachment.filename.lower()
            if filename_lower.endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif')):
                print(f"Procesando imagen adjunta: {attachment.filename}")
                try:
                    # Detectar el mime_type correcto según la extensión del archivo
                    mime_type = "image/png"
                    if filename_lower.endswith(('.jpg', '.jpeg')):
                        mime_type = "image/jpeg"
                    elif filename_lower.endswith('.webp'):
                        mime_type = "image/webp"
                    elif filename_lower.endswith('.gif'):
                        mime_type = "image/gif"

                    # Descargar los bytes de la imagen directamente desde Discord
                    image_bytes = await attachment.read()
                    
                    # Llamar a la función de IA
                    extracted_text = extract_text_from_image(image_bytes, mime_type)
                    
                    if extracted_text:
                        print(f"--- TEXTO EXTRAÍDO EXITOSAMENTE ---\n{extracted_text}\n-----------------------------------")
                    else:
                        print(f"⚠️ La IA no devolvió texto para la imagen: {attachment.filename}")
                        
                except Exception as e:
                    print(f"Error inesperado procesando {attachment.filename}: {e}")

# Token del bot cargado desde las variables de entorno de Railway
TOKEN = os.getenv("DISCORD_TOKEN")

if __name__ == "__main__":
    if not TOKEN:
        print("ERROR: No se encontró la variable de entorno DISCORD_TOKEN.")
    else:
        client_discord.run(TOKEN)
