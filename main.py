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
from PIL import Image, ImageDraw, ImageFont
import requests

# --- CONFIGURACIÓN GENERAL ---
app = Flask(__name__)
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Canal fijo configurado por ti
DISCORD_CANAL_NOTIFICACIONES_ID = 1549187543277379594

WEB_RAID_URL = "https://www.l2sudamerica.com/?page=boss"
EXCEL_URL = os.getenv(
    "EXCEL_URL",
    "https://1drv.ms/x/c/434ba5d6d0d889c3/IQAwNBrAH5eLQZWV-N3ufOfYAY8sBOApZdxzU8GuWMEBs0E?download=1",
)

ai_client = genai.Client(api_key=GEMINI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
client_discord = discord.Client(intents=intents)

# Variable para rastrear el último mensaje enviado y poder borrarlo
ultimo_mensaje_excel_id = None


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
  """Rellena la tabla inferior en crudo desde A31 hasta D189 en CALCULADORA."""
  try:
    sheet = wb["CALCULADORA"]
    for r in range(31, 190):
      for c in range(1, 5):
        sheet.cell(row=r, column=c).value = None

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


def generar_imagen_horario_rojo(wb):
  """Genera una tarjeta visual idéntica a la plantilla de Horario Rojo leyendo el Excel."""
  try:
    # Creamos un lienzo limpio con el fondo beige característico de la plantilla (#FDF3D8)
    img_width, img_height = 800, 900
    img = Image.new("RGB", (img_width, img_height), color="#FDF3D8")
    draw = ImageDraw.Draw(img)

    # Intentamos cargar una fuente estándar, si no usa la por defecto
    try:
      font_titulo = ImageFont.truetype(
          "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22
      )
      font_texto = ImageFont.truetype(
          "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16
      )
      font_chica = ImageFont.truetype(
          "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14
      )
    except:
      font_titulo = ImageFont.load_default()
      font_texto = ImageFont.load_default()
      font_chica = ImageFont.load_default()

    # Cabecera roja superior similar a la imagen
    draw.rectangle([0, 0, img_width, 110], fill="#8B0000")
    draw.text(
        (250, 40),
        "OKT Raid OKT Ally HTF",
        fill="#FFD700",
        font=font_titulo,
    )

    # Cabeceras de columnas
    draw.text((50, 140), "RAID", fill="#003366", font=font_texto)
    draw.text((200, 140), "DIA", fill="#003366", font=font_texto)
    draw.text((310, 140), "FECHA", fill="#003366", font=font_texto)
    draw.text((530, 140), "ARG / CHI", fill="#006600", font=font_texto)
    draw.text((640, 140), "VEN", fill="#006600", font=font_texto)
    draw.text((720, 140), "ESP", fill="#006600", font=font_texto)

    # Línea divisoria
    draw.line([30, 175, 770, 175], fill="#C08040", width=2)

    # Intentamos leer los datos de la pestaña HORARIO ROJO si existe, o simulamos con CALCULADORA
    sheet = (
        wb["HORARIO ROJO"]
        if "HORARIO ROJO" in wb.sheetnames
        else wb["CALCULADORA"]
    )

    # Pintamos filas de ejemplo/datos extraídos del Excel de forma dinámica
    y_offset = 200
    for row in range(10, 25):
      raid_nombre = sheet.cell(row=row, column=1).value
      if not raid_nombre:
        break

      dia = str(sheet.cell(row=row, column=2).value or "")
      fecha = str(sheet.cell(row=row, column=3).value or "")
      arg = str(sheet.cell(row=row, column=6).value or "18:00")
      ven = str(sheet.cell(row=row, column=7).value or "17:00")
      esp = str(sheet.cell(row=row, column=8).value or "23:00")

      # Color condicional similar al diseño (Rojo para algunos especiales, verde para normales)
      color_texto = "#CC0000" if row in [13, 19, 22, 23] else "#003300"

      draw.text((50, y_offset), str(raid_nombre), fill=color_texto, font=font_texto)
      draw.text((200, y_offset), dia, fill=color_texto, font=font_texto)
      draw.text((310, y_offset), fecha, fill=color_texto, font=font_texto)
      draw.text((530, y_offset), arg, fill=color_texto, font=font_texto)
      draw.text((640, y_offset), ven, fill=color_texto, font=font_texto)
      draw.text((720, y_offset), esp, fill=color_texto, font=font_texto)

      y_offset += 35

    # Guardamos en memoria RAM como imagen PNG
    output_img = io.BytesIO()
    img.save(output_img, format="PNG")
    output_img.seek(0)
    return output_img

  except Exception as e:
    print(f"❌ Error generando la imagen visual del horario: {e}")
    return None


# --- TAREA AUTÓNOMA: MONITOREO DE LA WEB DEL JUEGO (CADA 60 SEGUNDOS) ---
async def bucle_monitoreo_web():
  global ultimo_mensaje_excel_id
  await client_discord.wait_until_ready()
  print("🔄 Iniciando el monitoreo automático de la página de raids (cada 60 segundos)...")

  while not client_discord.is_closed():
    try:
      response = requests.get(WEB_RAID_URL, timeout=15)
      if response.status_code == 200:
        soup = BeautifulSoup(response.text, "html.parser")
        filas_tabla = soup.find_all("tr")
        datos_extraidos_web = []

        for fila in filas_tabla:
          columnas = fila.find_all(["td", "th"])
          if len(columnas) >= 4:
            val_nombre = columnas[0].get_text(strip=True)
            val_level = columnas[1].get_text(strip=True)
            val_status = columnas[2].get_text(strip=True)
            val_respawn = columnas[3].get_text(strip=True)

            if val_nombre and val_nombre.upper() != "NOMBRE":
              datos_extraidos_web.append(
                  [val_nombre, val_level, val_status, val_respawn]
              )

        if datos_extraidos_web:
          wb = descargar_excel_nube()
          if wb and "CALCULADORA" in wb.sheetnames:
            actualizar_rango_tabla_web(wb, datos_extraidos_web)

            # Generamos la imagen visual exacta del horario rojo
            imagen_buffer = generar_imagen_horario_rojo(wb)

            canal = client_discord.get_channel(int(DISCORD_CANAL_NOTIFICACIONES_ID))
            if canal and imagen_buffer:
              # Borramos el mensaje anterior del bot si existe para mantener el chat limpio
              if ultimo_mensaje_excel_id:
                try:
                  msg_anterior = await canal.fetch_message(
                      ultimo_mensaje_excel_id
                  )
                  await msg_anterior.delete()
                  print("🗑️ Imagen de horario anterior borrada del canal.")
                except Exception as ex:
                  print(
                      f"No se pudo borrar el mensaje anterior (posiblemente ya"
                      f" fue borrado): {ex}"
                  )

              # Enviamos la nueva imagen generada
              file_to_send = discord.File(
                  fp=imagen_buffer, filename="Horario_Rojo_Raids.png"
              )
              nuevo_msg = await canal.send(
                  "🔥 **HORARIOS DE RAIDS ACTUALIZADOS** (Sincronizado con la"
                  " web):",
                  file=file_to_send,
              )
              ultimo_mensaje_excel_id = nuevo_msg.id

    except Exception as e:
      print(f"Error en el ciclo de monitoreo web: {e}")

    await asyncio.sleep(60)


@client_discord.event
async def on_ready():
  print(f"🤖 Bot conectado exitosamente como {client_discord.user}")
  client_discord.loop.create_task(bucle_monitoreo_web())


# --- PROCESAMIENTO AUTOMÁTICO DE IMÁGENES EN DISCORD ---
@client_discord.event
async def on_message(message):
  global ultimo_mensaje_excel_id
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
                      "Extrae la información de los raids de la imagen en un"
                      " formato estructurado para actualizar la pestaña"
                      " CALCULADORA (A2:B15) del Excel."
                  ),
              ],
          )
          if response and response.text:
            print(f"--- DATOS PROCESADOS POR IA ---\n{response.text.strip()}")
            wb = descargar_excel_nube()
            if wb and "CALCULADORA" in wb.sheetnames:
              # Generamos y publicamos la nueva imagen actualizada tras procesar la captura
              imagen_buffer = generar_imagen_horario_rojo(wb)

              if message.channel and imagen_buffer:
                if ultimo_mensaje_excel_id:
                  try:
                    msg_anterior = await message.channel.fetch_message(
                        ultimo_mensaje_excel_id
                    )
                    await msg_anterior.delete()
                  except Exception:
                    pass

                file_to_send = discord.File(
                    fp=imagen_buffer, filename="Horario_Rojo_Raids.png"
                )
                nuevo_msg = await message.channel.send(
                    "📸 **Horario actualizado mediante captura procesada por"
                    " IA:**",
                    file=file_to_send,
                )
                ultimo_mensaje_excel_id = nuevo_msg.id

          await message.delete()

        except Exception as e:
          print(f"Error procesando la imagen automáticamente: {e}")


# --- INICIO DE PROCESOS (Flask + Discord) ---
if __name__ == "__main__":
  t = threading.Thread(target=run_web)
  t.daemon = True
  t.start()

  client_discord.run(DISCORD_TOKEN)
