import os
import io
import discord
from google import genai
from google.genai import types

# Configuración básica de intents para el bot de Discord
intents = discord.Intents.default()
intents.message_content = True

client_discord = discord.Client(intents=intents)

# Inicializa el cliente de la API de Gemini (tomará automáticamente la GEMINI_API_KEY de las variables de entorno)
ai_client = genai.Client()

@client_discord.event
async def on_ready():
    print(f"horario-bot: Bot conectado como {client_discord.user}")

def extract_text_from_image(image_bytes: bytes, language: str = "es") -> str:
    """
    Extrae y analiza los horarios de la imagen utilizando la IA de Google Gemini,
    con un sistema de respaldo (fallback) ante futuros cambios de versión.
    """
    # Lista de modelos a probar en orden de prioridad
    modelos_a_probar = ['gemini-3.6-flash', 'gemini-flash', 'gemini-2.5-flash']
    
    for modelo in modelos_a_probar:
        try:
            response = ai_client.models.generate_content(
                model=modelo,
                contents=[
                    types.Part.from_bytes(
                        data=image_bytes,
                        mime_type='image/png', # O el formato correspondiente de la captura
                    ),
                    (
                        "Eres un asistente experto en lectura de datos y horarios de videojuegos. "
                        "Analiza esta imagen y extrae de forma limpia, estructurada y ordenada todos los "
                        "horarios, nombres de eventos, fechas o datos numéricos que aparezcan para que puedan "
                        "ser procesados y guardados en una hoja de cálculo."
                    )
                ]
            )
            if response and response.text:
                return response.text.strip()
        except Exception as e:
            print(f"Aviso: Falló con el modelo {modelo}: {e}. Intentando con el siguiente...")
            continue
            
    print("Error crítico: Todos los modelos de fallback fallaron al procesar la imagen.")
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
                    
                    # Llamar a la función de IA con respaldo para extraer el texto/horarios
                    extracted_text = extract_text_from_image(image_bytes)
                    
                    if extracted_text:
                        print(f"Texto extraído con éxito:\n{extracted_text}")
                        # Aquí puedes agregar tu lógica existente para sincronizar a OneDrive / Excel
                        await message.channel.send(f"✅ Horario procesado con IA correctamente:\n```{extracted_text[:1500]}```")
                    else:
                        await message.channel.send("⚠️ No se pudo extraer texto o datos claros de la imagen.")
                        
                except Exception as e:
                    print(f"Error inesperado procesando {attachment.filename}: {e}")
                    await message.channel.send("❌ Ocurrió un error al procesar la imagen.")

# Token del bot cargado desde las variables de entorno de Railway
TOKEN = os.getenv("DISCORD_TOKEN")

if __name__ == "__main__":
    if not TOKEN:
        print("ERROR: No se encontró la variable de entorno DISCORD_TOKEN.")
    else:
        client_discord.run(TOKEN)
