import asyncio
import io
import os
import threading
from bs4 import BeautifulSoup
import discord
from flask import Flask
from google import genai
from google.genai import types
import openpyxl
import requests

# --- CONFIGURACIÓN GENERAL ---
app = Flask(__name__)
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WEB_RAID_URL = "https://www.l2sudamerica.com/?page=boss"
EXCEL_URL = os.getenv(
    "EXCEL_URL",
    "https://1drv.ms/x/c/434ba5d6d0d889c3/IQAwNBrAH5eLQZWV-N3ufOfYAY8sBOApZdxzU8GuWMEBs0E?download=1",
)

ai_client = genai.Client(api_key=GEMINI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
client_discord = discord.Client(intents=intents)


@app.route("/")
def home():
  return "🤖 Bot autónomo de Lineage II activo 24/7!"


def run_web():
  port = int(os.getenv("PORT", 8080))
  app.run(host="0.0.0.0", port=port)


def descargar_excel_nube():
  """Descarga el archivo Excel desde OneDrive directamente a la memoria RAM."""
  try:
    response = requests.get(EXCEL_URL, timeout=20)
    if response.status_code == 200:
      return openpyxl.load_workbook(io.BytesIO(response.content), data_only=True)
    else:
      print(f"❌ Error al descargar Excel de OneDrive: {response.status_code}")
      return None
  except Exception as e:
    print(f"❌ Excepción al conectar con OneDrive: {e}")
    return None


# --- TAREA AUTÓNOMA: MONITOREO DE LA WEB DEL JUEGO ---
async def bucle_monitoreo_web():
  await client_discord.wait_until_ready()
  print("🔄 Iniciando el monitoreo automático de la página de raids...")

  while not client_discord.is_closed():
    try:
      # 1. Hacemos scraping a la página de L2Sudamérica
      response = requests.get(WEB_RAID_URL, timeout=15)
      if response.status_code == 200:
        soup = BeautifulSoup(response.text, "html.parser")
        print(
            "🌐 Página del juego consultada con éxito. Verificando datos para"
            " la pestaña CALCULADORA..."
        )

        # 2. Descargamos el Excel para interactuar con él
        wb = descargar_excel_nube()
        if wb and "CALCULADORA" in wb.sheetnames:
          sheet = wb["CALCULADORA"]
          # Aquí puedes implementar la lógica de volcado en el rango A31:D189
          # Ejemplo: sheet['A31'] = "Dato extraído"
          print("📊 Excel de OneDrive cargado correctamente en memoria.")

    except Exception as e:
      print(f"Error en el ciclo de monitoreo web: {e}")

    # Revisa la web cada 10 minutos de forma continua
    await asyncio.sleep(600)


@client_discord.event
async def on_ready():
  print(f"🤖 Bot conectado exitosamente como {client_discord.user}")
  # Arrancamos la tarea en segundo plano al encender el bot
  client_discord.loop.create_task(bucle_monitoreo_web())


# --- PROCESAMIENTO AUTOMÁTICO DE IMÁGENES EN DISCORD ---
@client_discord.event
async def on_message(message):
  if message.author == client_discord.user:
    return

  # Si alguien sube una captura al chat, actúa de forma totalmente autónoma
  if message.attachments:
    for attachment in message.attachments:
      if attachment.filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        print(f"📸 Captura detectada en Discord: {attachment.filename}")
        try:
          image_bytes = await attachment.read()
          response = ai_client.models.generate_content(
              model="gemini-2.5-flash",
              contents=[
                  types.Part.from_bytes(
                      data=image_bytes, mime_type="image/png"
                  ),
                  (
                      "Extrae la información de los raids para actualizar la"
                      " pestaña CALCULADORA del Excel."
                  ),
              ],
          )
          if response and response.text:
            print(f"--- DATOS PROCESADOS POR IA ---\n{response.text.strip()}")
            # Aquí conectamos la actualización del Excel y el envío de la imagen resultante a Discord

          await message.delete()

        except Exception as e:
          print(f"Error procesando la imagen automáticamente: {e}")


# --- INICIO DE PROCESOS (Flask + Discord) ---
if __name__ == "__main__":
  # 1. Arrancamos el servidor Flask en un hilo independiente para UptimeRobot
  t = threading.Thread(target=run_web)
  t.daemon = True
  t.start()

  # 2. Arrancamos el cliente de Discord
  client_discord.run(DISCORD_TOKEN)
