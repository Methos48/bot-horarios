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

# Webhooks proporcionados para Horario Rojo y Ronda Rojo
WEBHOOK_HORARIOS_URL = "https://discord.com/api/webhooks/1548528724268552263/8HTtDAEl9zMn2KimT8CzP9tBKeE60QjuyGhjedQkfraRLWOgr3SZj6XuOB8jzEJld0dD"
WEBHOOK_RONDA_URL = "https://discord.com/api/webhooks/1548528618949582929/WjfonjOAn-xX3TYbAWGCRQyg5Tz5J3-92m2o-YWoAtuwOTvxB_dobqAuANyJr4bI9Add"

DISCORD_CANAL_EXCEL_ID = 1549187543277379594

EXCEL_PATH = os.getenv("EXCEL_PATH", "Calculadora de RAID.xlsm")
EXCEL_URL = "https://1drv.ms/x/c/434ba5d6d0d889c3/IQAwNBrAH5eLQZWV-N3ufOfYAY8sBOApZdxzU8GuWMEBs0E?download=1"
SERVER_BOSS_URL = "https://www.l2sudamerica.com/?page=boss"

intents = discord.Intents.default()
intents.message_content = True
client_discord = discord.Client(intents=intents)

ultimo_mensaje_excel_id = None
hash_excel_anterior = None
hash_horarios_anterior = None
hash_ronda_anterior = None


@app.route("/")
def home():
    return "🤖 Bot autónomo de Lineage II activo 24/7!"


def run_web():
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


def descargar_excel_desde_onedrive():
    print("☁️ Descargando la última versión del Excel desde OneDrive...")
    try:
        response = requests.get(EXCEL_URL, timeout=60)
        if response.status_code == 200:
            with open(EXCEL_PATH, "wb") as f:
                f.write(response.content)
            print("✅ ¡Excel descargado y actualizado con éxito desde OneDrive!")
            return True
        else:
            print(f"❌ Error al descargar de OneDrive. Código HTTP: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error de red al intentar descargar el Excel: {e}")
        return False


def cargar_excel():
    try:
        if not os.path.exists(EXCEL_PATH):
            descargar_excel_desde_onedrive()
        if os.path.exists(EXCEL_PATH):
            return openpyxl.load_workbook(EXCEL_PATH, keep_vba=True)
        else:
            return None
    except Exception as e:
        print(f"❌ Error al abrir el Excel: {e}")
        return None


def guardar_excel(wb):
    try:
        wb.save(EXCEL_PATH)
        return True
    except Exception as e:
        print(f"❌ Error al guardar el Excel: {e}")
        return False


def calcular_hash_excel():
    try:
        if os.path.exists(EXCEL_PATH):
            with open(EXCEL_PATH, "rb") as f:
                import hashlib
                return hashlib.md5(f.read()).hexdigest()
    except:
        pass
    return None


def enviar_webhook_imagen(webhook_url, img_io, mensaje):
    try:
        img_io.seek(0)
        files = {"file": ("tabla.png", img_io, "image/png")}
        payload = {"content": mensaje}
        response = requests.post(webhook_url, data=payload, files=files, timeout=30)
        if response.status_code in [200, 201]:
            try:
                return response.json().get("id")
            except:
                return None
    except Exception as e:
        print(f"❌ Excepción enviando webhook: {e}")
    return None


def generar_imagen_horario_rojo(wb):
    """
    Generador gráfico adaptado exactamente a la estética de la plantilla OKT / HTF.
    """
    try:
        img_width, img_height = 800, 680
        img = Image.new("RGB", (img_width, img_height), color="#FDF3D8")
        draw = ImageDraw.Draw(img)

        try:
            font_titulo = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
            font_sub = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
            font_texto = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 15)
        except:
            font_titulo = ImageFont.load_default()
            font_sub = ImageFont.load_default()
            font_texto = ImageFont.load_default()

        # 1. Cabecera roja con bordes negros y escudo dorado central
        draw.rectangle([0, 0, img_width, 105], fill="#7A0A0A")
        draw.rectangle([0, 0, 90, 105], fill="#1C1C1C")
        draw.rectangle([710, 0, img_width, 105], fill="#1C1C1C")

        draw.text((28, 38), "OKT", fill="#FFFFFF", font=font_titulo)
        draw.text((735, 38), "HTF", fill="#FFFFFF", font=font_titulo)

        draw.rectangle([210, 20, 590, 85], outline="#DAA520", width=2)
        draw.text((250, 38), "Raid", fill="#DAA520", font=font_titulo)
        draw.text((320, 42), "OKT HTF", fill="#FFFFFF", font=font_sub)
        draw.text((450, 38), "Ally", fill="#DAA520", font=font_titulo)

        # 2. Encabezados de columnas y banderas
        draw.text((45, 130), "RAID", fill="#003366", font=font_sub)
        draw.text((180, 130), "DIA", fill="#003366", font=font_sub)
        draw.text((285, 130), "FECHA", fill="#003366", font=font_sub)

        draw.text((515, 125), "🇦🇷 🇨🇱", font=font_texto)
        draw.text((615, 125), "🇻🇪", font=font_texto)
        draw.text((700, 125), "🇪🇸", font=font_texto)

        draw.line([30, 160, 770, 160], fill="#C08040", width=2)

        # 3. Llenado dinámico de filas desde el Excel
        sheet = wb["HORARIO ROJO"] if "HORARIO ROJO" in wb.sheetnames else wb["CALCULADORA"]
        y_offset = 185
        
        for row in range(10, 22):
            raid_nombre = sheet.cell(row=row, column=1).value
            if not raid_nombre:
                break

            dia = str(sheet.cell(row=row, column=2).value or "")
            fecha = str(sheet.cell(row=row, column=3).value or "")
            arg = str(sheet.cell(row=row, column=6).value or "")
            ven = str(sheet.cell(row=row, column=7).value or "")
            esp = str(sheet.cell(row=row, column=8).value or "")

            color_texto = "#CC0000" if str(raid_nombre).lower() in ["antharas", "valakas", "zaken"] else "#003300"

            draw.text((45, y_offset), str(raid_nombre), fill=color_texto, font=font_texto)
            draw.text((180, y_offset), dia, fill=color_texto, font=font_texto)
            draw.text((285, y_offset), fecha, fill=color_texto, font=font_texto)
            
            draw.text((515, y_offset), arg, fill="#006600", font=font_texto)
            draw.text((615, y_offset), ven, fill="#006600", font=font_texto)
            draw.text((700, y_offset), esp, fill="#006600", font=font_texto)

            y_offset += 36

        output_img = io.BytesIO()
        img.save(output_img, format="PNG")
        output_img.seek(0)
        return output_img
    except Exception as e:
        print(f"❌ Error generando Horario Rojo: {e}")
        return None


def generar_imagen_ronda_rojo(wb):
    try:
        img_width, img_height = 850, 950
        img = Image.new("RGB", (img_width, img_height), color="#FDF3D8")
        draw = ImageDraw.Draw(img)

        try:
            font_titulo = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
            font_texto = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 13)
        except:
            font_titulo = ImageFont.load_default()
            font_texto = ImageFont.load_default()

        draw.rectangle([0, 0, img_width, 110], fill="#8B0000")
        draw.text((250, 40), "OKT Ronda Raid HTF", fill="#FFD700", font=font_titulo)

        draw.text((40, 135), "Raid", fill="#003366", font=font_texto)
        draw.text((260, 135), "LVL", fill="#003366", font=font_texto)
        draw.text((310, 135), "Hora", fill="#003366", font=font_texto)

        draw.text((450, 135), "Raid", fill="#003366", font=font_texto)
        draw.text((670, 135), "LVL", fill="#003366", font=font_texto)
        draw.text((720, 135), "Hora", fill="#003366", font=font_texto)

        draw.line([30, 160, 820, 160], fill="#C08040", width=2)

        sheet = wb["RONDA ROJO"] if "RONDA ROJO" in wb.sheetnames else wb["CALCULADORA"]

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


# --- TAREA EN SEGUNDO PLANO: MONITOREO WEB ---
async def tarea_monitoreo_web():
    global hash_excel_anterior, hash_horarios_anterior, hash_ronda_anterior
    await client_discord.wait_until_ready()
    print("🌐 Tarea de monitoreo web de raids iniciada...")

    while not client_discord.is_closed():
        try:
            print("🔍 Escaneando la página web del servidor...")
            response = requests.get(SERVER_BOSS_URL, timeout=30)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                capturando = False
                datos_extraidos = []

                for tr in soup.find_all(['tr', 'div']):
                    texto_fila = tr.get_text(separator="|", strip=True)
                    if "Ember" in texto_fila:
                        capturando = True
                    
                    if capturando:
                        partes = [p.strip() for p in texto_fila.split('|') if p.strip()]
                        if len(partes) >= 3:
                            nombre_boss = partes[0]
                            lvl_boss = partes[1] if len(partes) > 1 else ""
                            estado_boss = partes[2] if len(partes) > 2 else ""
                            tiempo_boss = partes[3] if len(partes) > 3 else "-"
                            datos_extraidos.append([nombre_boss, lvl_boss, estado_boss, tiempo_boss])

                        if "Zombie Lord Farakelsus" in texto_fila:
                            break

                if len(datos_extraidos) > 0:
                    wb = cargar_excel()
                    if wb and "CALCULADORA" in wb.sheetnames:
                        sheet_calc = wb["CALCULADORA"]
                        row_idx = 31
                        for item in datos_extraidos:
                            if row_idx > 189:
                                break
                            sheet_calc.cell(row=row_idx, column=1, value=item[0])
                            sheet_calc.cell(row=row_idx, column=2, value=item[1])
                            sheet_calc.cell(row=row_idx, column=3, value=item[2])
                            sheet_calc.cell(row=row_idx, column=4, value=item[3])
                            row_idx += 1

                        guardar_excel(wb)

            hash_actual = calcular_hash_excel()
            if hash_excel_anterior and hash_actual != hash_excel_anterior:
                wb_actualizado = cargar_excel()
                
                if DISCORD_CANAL_EXCEL_ID != 0 and wb_actualizado:
                    canal_excel = client_discord.get_channel(DISCORD_CANAL_EXCEL_ID)
                    if canal_excel:
                        global ultimo_mensaje_excel_id
                        if ultimo_mensaje_excel_id:
                            try:
                                msg_ant_ex = await canal_excel.fetch_message(ultimo_mensaje_excel_id)
                                await msg_ant_ex.delete()
                            except:
                                pass
                        
                        with open(EXCEL_PATH, "rb") as f_ex:
                            archivo_discord = discord.File(f_ex, filename="Calculadora_de_RAID_Actualizado.xlsm")
                            msg_ex = await canal_excel.send("📊 **NUEVA VERSIÓN DEL EXCEL ACTUALIZADA:**", file=archivo_discord)
                            ultimo_mensaje_excel_id = msg_ex.id

                if wb_actualizado:
                    img_horarios = generar_imagen_horario_rojo(wb_actualizado)
                    if img_horarios:
                        h_h = hash(img_horarios.getvalue())
                        if h_h != hash_horarios_anterior:
                            enviar_webhook_imagen(WEBHOOK_HORARIOS_URL, img_horarios, "🔥 **HORARIOS DE RAIDS ACTUALIZADOS:**")
                            hash_horarios_anterior = h_h

                    img_ronda = generar_imagen_ronda_rojo(wb_actualizado)
                    if img_ronda:
                        h_r = hash(img_ronda.getvalue())
                        if h_r != hash_ronda_anterior:
                            enviar_webhook_imagen(WEBHOOK_RONDA_URL, img_ronda, "⚔️ **RONDA ROJO (Nivel 60+) ACTUALIZADA:**")
                            hash_ronda_anterior = h_r

            hash_excel_anterior = hash_actual

        except Exception as e:
            print(f"❌ Error en la tarea de monitoreo web: {e}")

        await asyncio.sleep(300)


@client_discord.event
async def on_ready():
    print(f"🤖 Bot conectado exitosamente como {client_discord.user}")
    global hash_excel_anterior
    hash_excel_anterior = calcular_hash_excel()
    client_discord.loop.create_task(tarea_monitoreo_web())


@client_discord.event
async def on_message(message):
    global hash_excel_anterior, hash_horarios_anterior, hash_ronda_anterior

    if message.author == client_discord.user:
        return

    if message.attachments:
        imagenes_validas = [
            att for att in message.attachments
            if att.filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
        ]

        if imagenes_validas:
            print(f"📸 Se detectaron {len(imagenes_validas)} imágenes adjuntas.")
            
            # =========================================================================
            # CÓDIGO DE LA API DE GEMINI (MANTENIDO ESCRITO PERO DESACTIVADO/COMENTADO)
            # =========================================================================
            """
            import google.generativeai as genai
            genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
            model = genai.GenerativeModel("gemini-2.5-flash") # o la versión de tu preferencia
            
            for attachment in imagenes_validas:
                try:
                    img_bytes = await attachment.read()
                    # Código original de llamada a la API comentado para evitar el error 429
                    # response = model.generate_content([
                    #     {'mime_type': 'image/png', 'data': img_bytes},
                    #     "Extrae los nombres de los raids y sus horarios."
                    # ])
                except Exception as e:
                    print(f"Error con la IA: {e}")
            """
            # =========================================================================


if __name__ == "__main__":
    descargar_excel_desde_onedrive()
    t = threading.Thread(target=run_web)
    t.daemon = True
    t.start()
    client_discord.run(DISCORD_TOKEN)
