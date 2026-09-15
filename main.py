import asyncio
import base64
import io
import os
import threading
import time
from bs4 import BeautifulSoup
import discord
from flask import Flask
import openpyxl
from PIL import Image, ImageDraw, ImageFont
import requests

# --- CONFIGURACIÓN GENERAL ---
app = Flask(__name__)
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# IDs de tus dos canales de prueba configurados
DISCORD_CANAL_HORARIOS_ID = 1548528724268552263
DISCORD_CANAL_RONDA_ID = 1548528618949582929

WEB_RAID_URL = "https://www.l2sudamerica.com/?page=boss"
EXCEL_URL = os.getenv(
    "EXCEL_URL",
    "https://1drv.ms/x/c/434ba5d6d0d889c3/IQAwNBrAH5eLQZWV-N3ufOfYAY8sBOApZdxzU8GuWMEBs0E?download=1",
)

intents = discord.Intents.default()
intents.message_content = True
client_discord = discord.Client(intents=intents)

# Variables para rastrear los mensajes anteriores en cada canal
ultimo_mensaje_horarios_id = None
ultimo_mensaje_ronda_id = None


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


def generar_imagen_horario_rojo(wb):
  """Genera la tarjeta visual de Horario Rojo."""
  try:
    img_width, img_height = 800, 900
    img = Image.new("RGB", (img_width, img_height), color="#FDF3D8")
    draw = ImageDraw.Draw(img)

    try:
      font_titulo = ImageFont.truetype(
          "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22
      )
      font_texto = ImageFont.truetype(
          "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16
      )
    except:
      font_titulo = ImageFont.load_default()
      font_texto = ImageFont.load_default()

    draw.rectangle([0, 0, img_width, 110], fill="#8B0000")
    draw.text(
        (250, 40),
        "OKT Raid OKT Ally HTF",
        fill="#FFD700",
        font=font_titulo,
    )

    draw.text((50, 140), "RAID", fill="#003366", font=font_texto)
    draw.text((200, 140), "DIA", fill="#003366", font=font_texto)
    draw.text((310, 140), "FECHA", fill="#003366", font=font_texto)
    draw.text((530, 140), "ARG / CHI", fill="#006600", font=font_texto)
    draw.text((640, 140), "VEN", fill="#006600", font=font_texto)
    draw.text((720, 140), "ESP", fill="#006600", font=font_texto)

    draw.line([30, 175, 770, 175], fill="#C08040", width=2)

    sheet = (
        wb["HORARIO ROJO"]
        if "HORARIO ROJO" in wb.sheetnames
        else wb["CALCULADORA"]
    )
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

      color_texto = "#CC0000" if row in [13, 19, 22, 23] else "#003300"

      draw.text(
          (50, y_offset), str(raid_nombre), fill=color_texto, font=font_texto
      )
      draw.text((200, y_offset), dia, fill=color_texto, font=font_texto)
      draw.text((310, y_offset), fecha, fill=color_texto, font=font_texto)
      draw.text((530, y_offset), arg, fill=color_texto, font=font_texto)
      draw.text((640, y_offset), ven, fill=color_texto, font=font_texto)
      draw.text((720, y_offset), esp, fill=color_texto, font=font_texto)

      y_offset += 35

    output_img = io.BytesIO()
    img.save(output_img, format="PNG")
    output_img.seek(0)
    return output_img
  except Exception as e:
    print(f"❌ Error generando Horario Rojo: {e}")
    return None


def generar_imagen_ronda_rojo(wb):
  """Genera la tarjeta visual de Ronda Rojo (doble columna de nivel 60+)."""
  try:
    img_width, img_height = 850, 950
    img = Image.new("RGB", (img_width, img_height), color="#FDF3D8")
    draw = ImageDraw.Draw(img)

    try:
      font_titulo = ImageFont.truetype(
          "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22
      )
      font_texto = ImageFont.truetype(
          "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 13
      )
    except:
      font_titulo = ImageFont.load_default()
      font_texto = ImageFont.load_default()

    draw.rectangle([0, 0, img_width, 110], fill="#8B0000")
    draw.text(
        (250, 40),
        "OKT Ronda Raid HTF",
        fill="#FFD700",
        font=font_titulo,
    )

    draw.text((40, 135), "Raid", fill="#003366", font=font_texto)
    draw.text((260, 135), "LVL", fill="#003366", font=font_texto)
    draw.text((310, 135), "Hora", fill="#003366", font=font_texto)

    draw.text((450, 135), "Raid", fill="#003366", font=font_texto)
    draw.text((670, 135), "LVL", fill="#003366", font=font_texto)
    draw.text((720, 135), "Hora", fill="#003366", font=font_texto)

    draw.line([30, 160, 820, 160], fill="#C08040", width=2)

    sheet = (
        wb["RONDA ROJO"] if "RONDA ROJO" in wb.sheetnames else wb["CALCULADORA"]
    )

    y_left = 180
    for row in range(9, 30):
      raid = sheet.cell(row=row, column=2).value
      if not raid:
        break
      lvl = str(sheet.cell(row=row, column=4).value or "")
      hora = str(sheet.cell(row=row, column=5).value or "")

      draw.text((40, y_left), str(raid), fill="#003300", font=font_texto)
      draw.text((260, y_left), lvl, fill="#003300", font=font_texto)
      draw.text((310, y_left), hora, fill="#006600", font=font_texto)
      y_left += 28

    y_right = 180
    for row in range(9, 35):
      raid = sheet.cell(row=row, column=7).value
      if not raid:
        break
      lvl = str(sheet.cell(row=row, column=9).value or "")
      hora = str(sheet.cell(row=row, column=10).value or "")

      draw.text((450, y_right), str(raid), fill="#003300", font=font_texto)
      draw.text((670, y_right), lvl, fill="#003300", font=font_texto)
      draw.text((720, y_right), hora, fill="#006600", font=font_texto)
      y_right += 28

    output_img = io.BytesIO()
    img.save(output_img, format="PNG")
    output_img.seek(0)
    return output_img
  except Exception as e:
    print(f"❌ Error generando Ronda Rojo: {e}")
    return None


@client_discord.event
async def on_ready():
  print(f"🤖 Bot conectado exitosamente como {client_discord.user}")


# --- FUNCIÓN DE LLAMADA DIRECTA POR API REST (VERSIÓN v1 + GEMINI 2.0 FLASH) ---
def llamar_ia_con_reintentos(img_pil):
  # Convertir la imagen PIL a formato base64 JPEG
  buffered = io.BytesIO()
  img_pil.save(buffered, format="JPEG")
  img_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

  # Endpoint actualizado con gemini-2.0-flash y API v1 estable
  url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

  headers = {"Content-Type": "application/json"}

  payload = {
      "contents": [{
          "parts": [
              {
                  "inline_data": {
                      "mime_type": "image/jpeg",
                      "data": img_base64,
                  }
              },
              {
                  "text": (
                      "Extrae la información de los raids de la imagen en un"
                      " formato estructurado para actualizar la pestaña"
                      " CALCULADORA (A2:B15) del Excel."
                  )
              },
          ]
      }]
  }

  intentos = 3
  for i in range(intentos):
    try:
      response = requests.post(url, headers=headers, json=payload, timeout=30)
      if response.status_code == 200:
        data = response.json()
        texto_resultado = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        return texto_resultado
      else:
        raise Exception(f"HTTP {response.status_code}: {response.text}")
    except Exception as ex:
      print(f"⚠️ Intento {i+1} fallido por API REST: {ex}")
      if i < intentos - 1:
        time.sleep(4)
      else:
        raise ex


# --- PROCESAMIENTO AUTOMÁTICO SEGURO ---
@client_discord.event
async def on_message(message):
  global ultimo_mensaje_horarios_id, ultimo_mensaje_ronda_id
  if message.author == client_discord.user:
    return

  if message.attachments:
    for attachment in message.attachments:
      if attachment.filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        print(f"📸 Nueva imagen de raids detectada: {attachment.filename}")
        try:
          image_bytes = await attachment.read()
          img_pil = Image.open(io.BytesIO(image_bytes))

          texto_respuesta = await asyncio.to_thread(
              llamar_ia_con_reintentos, img_pil
          )

          if texto_respuesta:
            print(f"--- DATOS PROCESADOS POR IA ---\n{texto_respuesta.strip()}")
            wb = descargar_excel_nube()
            if wb and "CALCULADORA" in wb.sheetnames:
              # 1. Publicar en Canal Horarios
              img_horarios = generar_imagen_horario_rojo(wb)
              canal_horarios = client_discord.get_channel(
                  int(DISCORD_CANAL_HORARIOS_ID)
              )
              if canal_horarios and img_horarios:
                if ultimo_mensaje_horarios_id:
                  try:
                    msg_ant = await canal_horarios.fetch_message(
                        ultimo_mensaje_horarios_id
                    )
                    await msg_ant.delete()
                  except:
                    pass

                f_horarios = discord.File(
                    fp=img_horarios, filename="Horario_Rojo.png"
                )
                msg_h = await canal_horarios.send(
                    "🔥 **HORARIOS DE RAIDS ACTUALIZADOS (vía imagen):**",
                    file=f_horarios,
                )
                ultimo_mensaje_horarios_id = msg_h.id

              # 2. Publicar en Canal Ronda Rojo
              img_ronda = generar_imagen_ronda_rojo(wb)
              canal_ronda = client_discord.get_channel(
                  int(DISCORD_CANAL_RONDA_ID)
              )
              if canal_ronda and img_ronda:
                if ultimo_mensaje_ronda_id:
                  try:
                    msg_ant_r = await canal_ronda.fetch_message(
                        ultimo_mensaje_ronda_id
                    )
                    await msg_ant_r.delete()
                  except:
                    pass

                f_ronda = discord.File(
                    fp=img_ronda, filename="Ronda_Rojo.png"
                )
                msg_r = await canal_ronda.send(
                    "⚔️ **RONDA ROJO (Nivel 60+) ACTUALIZADA (vía"
                    " imagen):**",
                    file=f_ronda,
                )
                ultimo_mensaje_ronda_id = msg_r.id

          await message.delete()

        except Exception as e:
          print(f"❌ Error definitivo procesando la imagen tras reintentos: {e}")


# --- INICIO DE PROCESOS (Flask + Discord) ---
if __name__ == "__main__":
  t = threading.Thread(target=run_web)
  t.daemon = True
  t.start()

  client_discord.run(DISCORD_TOKEN)
