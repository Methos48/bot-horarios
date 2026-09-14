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
      return openpyxl.load_workbook(io.BytesIO(response.content))
    else:
      print(f"❌ Error al descargar Excel de OneDrive: {response.status_code}")
      return None
  except Exception as e:
    print(f"❌ Excepción al conectar con OneDrive: {e}")
    return None


def actualizar_rango_tabla_web(wb, datos_web):
  """Rellena la tabla inferior en crudo desde A31 hasta D189 en CALCULADORA

  con los datos obtenidos de la página web del juego.
  """
  try:
    sheet = wb["CALCULADORA"]

    # Limpiamos primero el rango A31:D189 por si hay datos viejos
    for r in range(31, 190):
      for c in range(1, 5):
        sheet.cell(row=r, column=c).value = None

    # Insertamos los nuevos datos de la web
    for i, fila_datos in enumerate(datos_web):
      fila_idx = 31 + i
      if fila_idx > 189:
        break
      for col_offset, valor in enumerate(fila_datos):
        sheet.cell(row=fila_idx, column=1 + col_offset).value = valor

    print("✅ Rango inferior (A31:D189) actualizado con los datos de la web.")
    return True
  except Exception as e:
    print(f"❌ Error al actualizar el rango web A31:D189: {e}")
    return False


def actualizar_rango_superior_discord(wb, datos_procesados_ia):
  """Rellena la tabla superior en el rango A2:B15 en CALCULADORA

  con los datos extraídos de las imágenes que llegan al canal de Discord.
  """
  try:
    sheet = wb["CALCULADORA"]

    for i, item in enumerate(datos_procesados_ia):
      fila_idx = 2 + i
      if fila_idx > 15:
        break  # Límite superior B15

      boss_nombre = item.get("boss") or item.get("nombre")
      fecha_hora = item.get("fecha_hora") or item.get("hora")

      if boss_nombre:
        sheet.cell(row=fila_idx, column=1).value = boss_nombre
      if fecha_hora:
        sheet.cell(row=fila_idx, column=2).value = fecha_hora

    print("✅ Rango superior (A2:B15) actualizado con la información de Discord.")
    return True
  except Exception as e:
    print(f"❌ Error al actualizar el rango superior A2:B15: {e}")
    return False


# --- TAREA AUTÓNOMA: MONITOREO DE LA WEB DEL JUEGO (CADA 60 SEGUNDOS) ---
async def bucle_monitoreo_web():
  await client_discord.wait_until_ready()
  print(
      "🔄 Iniciando el monitoreo automático de la página de raids (cada 60"
      " segundos)..."
  )

  while not client_discord.is_closed():
    try:
      response = requests.get(WEB_RAID_URL, timeout=15)
      if response.status_code == 200:
        soup = BeautifulSoup(response.text, "html.parser")
        print("🌐 Página del juego consultada. Verificando cambios...")

        # Aquí procesarías el HTML de la sopa para extraer los datos en bruto
        # Ejemplo simulado de datos estructurados para la tabla A31:D189:
        # datos_extraidos_web = [ [colA, colB, colC, colD], ... ]

        wb = descargar_excel_nube()
        if wb and "CALCULADORA" in wb.sheetnames:
          # Si deseas aplicar la actualización automática en el Excel:
          # actualizar_rango_tabla_web(wb, datos_extraidos_web)
          pass

    except Exception as e:
      print(f"Error en el ciclo de monitoreo web: {e}")

    # Espera exactamente 60 segundos antes de volver a revisar la página
    await asyncio.sleep(60)


@client_discord.event
async def on_ready():
  print(f"🤖 Bot conectado exitosamente como {client_discord.user}")
  client_discord.loop.create_task(bucle_monitoreo_web())


# --- PROCESAMIENTO AUTOMÁTICO DE IMÁGENES EN DISCORD ---
@client_discord.event
async def on_message(message):
  if message.author == client_discord.user:
    return

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
                      " pestaña CALCULADORA (A2:B15) del Excel."
                  ),
              ],
          )
          if response and response.text:
            print(f"--- DATOS PROCESADOS POR IA ---\n{response.text.strip()}")
            wb = descargar_excel_nube()
            if wb and "CALCULADORA" in wb.sheetnames:
              # Aquí puedes parsear la respuesta de la IA en formato de lista de diccionarios
              # y llamar a: actualizar_rango_superior_discord(wb, datos_ia)
              pass

          await message.delete()

        except Exception as e:
          print(f"Error procesando la imagen automáticamente: {e}")


# --- INICIO DE PROCESOS (Flask + Discord) ---
if __name__ == "__main__":
  t = threading.Thread(target=run_web)
  t.daemon = True
  t.start()

  client_discord.run(DISCORD_TOKEN)
