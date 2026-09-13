import os
import asyncio
import discord
from google import genai
from google.genai import types
import openpyxl
import requests
from bs4 import BeautifulSoup

# Configuración básica de intents para Discord
intents = discord.Intents.default()
intents.message_content = True

client_discord = discord.Client(intents=intents)
ai_client = genai.Client()

EXCEL_FILE_PATH = "tu_plantilla.xlsx"  # Cambia por el nombre exacto de tu archivo en Railway

def pegar_datos_en_calculo(lista_de_filas):
    """
    Toma los datos extraídos de la web y los pega en bloque 
    en la hoja CALCULO a partir de la celda A31, tal como lo haces a mano.
    """
    if not os.path.exists(EXCEL_FILE_PATH):
        print(f"⚠️ No se encontró el archivo Excel en {EXCEL_FILE_PATH}")
        return

    try:
        wb = openpyxl.load_workbook(EXCEL_FILE_PATH)
        
        # Selecciona específicamente la pestaña 'CALCULO'
        if "CALCULO" in wb.sheetnames:
            sheet = wb["CALCULO"]
        else:
            sheet = wb.active  # Respaldo por si usa la activa
            
        # Posición inicial: Fila 31, Columna A
        fila_inicio = 31
        
        for i, fila_datos in enumerate(lista_de_filas):
            fila_actual = fila_inicio + i
            
            # Pega en bloque las columnas A, B, C y D
            sheet.cell(row=fila_actual, column=1).value = fila_datos.get("nombre")   # Columna A: RAID
            sheet.cell(row=fila_actual, column=2).value = fila_datos.get("nivel")    # Columna B: LVL
            sheet.cell(row=fila_actual, column=3).value = fila_datos.get("estado")   # Columna C: Estado
            sheet.cell(row=fila_actual, column=4).value = fila_datos.get("respawn")  # Columna D: FECHA HORA ACTUAL

        wb.save(EXCEL_FILE_PATH)
        print("✅ Datos de la web pegados exitosamente en la hoja CALCULO desde A31.")
        
    except Exception as e:
        print(f"Error al manipular el Excel con openpyxl: {e}")

async def verificar_web_oficial():
    """
    Revisa la página web oficial del servidor cada 60 segundos de forma autónoma.
    """
    url = "https://www.l2sudamerica.com/?page=boss"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    while True:
        try:
            print("🔍 Verificando la página web oficial del servidor...")
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                filas_tabla = []
                
                # Rastreo de la tabla en la web
                filas = soup.find_all('tr')
                for fila in filas:
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
                    # Pega la data en bloque en el Excel
                    pegar_datos_en_calculo(filas_tabla)
            else:
                print(f"⚠️ Error al conectar con la web. Código HTTP: {response.status_code}")
        
        except Exception as e:
            print(f"Error en la tarea de rastreo web: {e}")

        # Esperar exactamente 60 segundos antes de la siguiente revisión
        await asyncio.sleep(60)

@client_discord.event
async def on_ready():
    print(f"horario-bot: Bot conectado como {client_discord.user}")
    # Arranca el bucle en segundo plano de la web cada 1 minuto
    client_discord.loop.create_task(verificar_web_oficial())

@client_discord.event
async def on_message(message):
    # Evitar bucles del propio bot
    if message.author == client_discord.user:
        return

    # Si envías una captura de pantalla al canal de Discord
    if message.attachments:
        for attachment in message.attachments:
            if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                print(f"📸 Captura recibida en Discord: {attachment.filename}")
                try:
                    image_bytes = await attachment.read()
                    
                    # Procesamiento con la IA Gemini
                    response = ai_client.models.generate_content(
                        model='gemini-3.6-flash',
                        contents=[
                            types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                            "Extrae de forma limpia los nombres de los jefes y sus horarios de esta imagen."
                        ]
                    )
                    
                    if response and response.text:
                        print(f"--- TEXTO EXTRAÍDO POR IA ---\n{response.text.strip()}")

                    # Borrar automáticamente la imagen para mantener el chat limpio
                    await message.delete()
                    
                except Exception as e:
                    print(f"Error procesando la imagen de Discord: {e}")

TOKEN = os.getenv("DISCORD_TOKEN")

if __name__ == "__main__":
    if not TOKEN:
        print("ERROR: Falta el token de Discord en las variables de entorno.")
    else:
        client_discord.run(TOKEN)
