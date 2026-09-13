mport os
import asyncio
import discord
from google import genai
from google.genai import types
import openpyxl
import requests
from bs4 import BeautifulSoup

# Configuración de intents para Discord
intents = discord.Intents.default()
intents.message_content = True

client_discord = discord.Client(intents=intents)
ai_client = genai.Client()

# Nombre exacto de tu archivo con macros en Railway
EXCEL_FILE_PATH = "Calculadora de RAID.xlsm"

def pegar_datos_en_calculo(lista_de_filas):
    """
    Pega en bloque los datos de la web oficial en la hoja 'CALCULO' a partir de la celda A31.
    """
    if not os.path.exists(EXCEL_FILE_PATH):
        print(f"⚠️ No se encontró el archivo Excel: {EXCEL_FILE_PATH}")
        return

    try:
        wb = openpyxl.load_workbook(EXCEL_FILE_PATH)
        sheet = wb["CALCULO"] if "CALCULO" in wb.sheetnames else wb.active
            
        # Pega la tabla de la web desde la fila 31 hacia abajo
        fila_inicio = 31
        for i, fila_datos in enumerate(lista_de_filas):
            fila_actual = fila_inicio + i
            sheet.cell(row=fila_actual, column=1).value = fila_datos.get("nombre")   # Columna A: RAID
            sheet.cell(row=fila_actual, column=2).value = fila_datos.get("nivel")    # Columna B: LVL
            sheet.cell(row=fila_actual, column=3).value = fila_datos.get("estado")   # Columna C: Estado
            sheet.cell(row=fila_actual, column=4).value = fila_datos.get("respawn")  # Columna D: Fecha/Hora

        wb.save(EXCEL_FILE_PATH)
        print("✅ Datos de la web actualizados en la hoja CALCULO (desde A31).")
        
    except Exception as e:
        print(f"Error al manipular el Excel con openpyxl (CALCULO): {e}")

def actualizar_plantilla_desde_discord(datos_bosses):
    """
    Actualiza la hoja 'PLANTILLA' (filas 8 a 20):
    - Columna C (VIVO): True si está tildado, False si no.
    - Columna E (RAID), F (LVL), G (HORA), H (FECHA).
    """
    if not os.path.exists(EXCEL_FILE_PATH):
        return

    try:
        wb = openpyxl.load_workbook(EXCEL_FILE_PATH)
        
        if "PLANTILLA" in wb.sheetnames:
            sheet = wb["PLANTILLA"]
            
            # Recorremos el rango exacto de la plantilla (filas 8 a 20)
            for row in range(8, 21):
                nombre_raid = sheet.cell(row=row, column=5).value  # Columna E: RAID
                if nombre_raid and nombre_raid in datos_bosses:
                    info = datos_bosses[nombre_raid]
                    
                    # Columna C: VIVO (Checkbox True/False)
                    if info.get("vivo", False):
                        sheet.cell(row=row, column=3).value = True   # Tildado
                    else:
                        sheet.cell(row=row, column=3).value = False  # Destildado
                        
                    # Actualizar Hora y Fecha si vienen en los datos
                    if info.get("hora"):
                        sheet.cell(row=row, column=7).value = info.get("hora")   # Columna G: HORA
                    if info.get("fecha"):
                        sheet.cell(row=row, column=8).value = info.get("fecha")  # Columna H: FECHA
                        
            wb.save(EXCEL_FILE_PATH)
            print("✅ Hoja PLANTILLA actualizada con éxito desde Discord.")
    except Exception as e:
        print(f"Error al actualizar PLANTILLA desde Discord: {e}")

async def verificar_web_oficial():
    """
    Revisa la página web oficial del servidor cada 60 segundos de forma autónoma.
    """
    url = "https://www.l2sudamerica.com/?page=boss"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    while True:
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                filas_tabla = []
                
                for fila in soup.find_all('tr'):
                    columnas = fila.find_all('td')
                    if len(columnas) >= 4:
                        nombre = columnas[0].get_text(strip=True)
                        nivel = columnas[1].get_text(strip=True)
                        status = columnas[2].get_text(strip=True)
                        respawn = columnas[3].get_text(strip=True)
                        
                        if nombre and respawn and respawn != "-":
                            filas_tabla.append({
                                "nombre": nombre,
                                "nivel": nivel,
                                "estado": status,
                                "respawn": respawn
                            })

                if filas_tabla:
                    pegar_datos_en_calculo(filas_tabla)
        except Exception as e:
            print(f"Error en rastreo web: {e}")

        await asyncio.sleep(60)

@client_discord.event
async def on_ready():
    print(f"bot-horarios: Conectado como {client_discord.user}")
    client_discord.loop.create_task(verificar_web_oficial())

@client_discord.event
async def on_message(message):
    if message.author == client_discord.user:
        return

    if message.attachments:
        for attachment in message.attachments:
            if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                print(f"📸 Procesando captura de Discord: {attachment.filename}")
                try:
                    image_bytes = await attachment.read()
                    
                    # Análisis con Gemini
                    response = ai_client.models.generate_content(
                        model='gemini-3.6-flash',
                        contents=[
                            types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                            "Extrae el nombre de cada raid, si está vivo (true/false), su hora y fecha para actualizar la plantilla."
                        ]
                    )
                    
                    if response and response.text:
                        print(f"--- DATOS EXTRAÍDOS --- \n{response.text.strip()}")
                        # Aquí puedes estructurar la respuesta de la IA en un diccionario y llamar a:
                        # actualizar_plantilla_desde_discord(datos_procesados)

                    # Borrar imagen automáticamente para mantener el chat limpio
                    await message.delete()
                    
                except Exception as e:
                    print(f"Error procesando imagen de Discord: {e}")

TOKEN = os.getenv("DISCORD_TOKEN")

if __name__ == "__main__":
    if not TOKEN:
        print("ERROR: Falta el token de Discord.")
    else:
        client_discord.run(TOKEN)
