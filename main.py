import os
import io
import discord
import openpyxl
from discord.ext import tasks
from google import genai
from google.genai import types

# Configuración de clientes
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
EXCEL_FILE_PATH = "tu_archivo.xlsx"  # Cambia por el nombre real de tu Excel

intents = discord.Intents.default()
intents.message_content = True
client_discord = discord.Client(intents=intents)

ai_client = genai.Client(api_key=GEMINI_API_KEY)

# Variable global para guardar el último hash o texto de la web y detectar cambios
ultimo_contenido_web = None

@client_discord.event
async def on_ready():
    print(f"🤖 Bot conectado exitosamente como {client_discord.user}")
    # Arrancamos la tarea de monitoreo automático al encender
    monitorear_cambios_web.start()

# --- TAREA EN SEGUNDO PLANO: Monitorea y actualiza solo si hay cambios ---
@tasks.loop(minutes=15)  # Revisa cada 15 minutos (puedes ajustarlo)
async def monitorear_cambios_web():
    global ultimo_contenido_web
    print("🔍 [Monitoreo] Verificando la página web oficial del juego...")
    
    try:
        # 1. AQUÍ HACES EL SCRAPING DE LA PÁGINA WEB OFICIAL
        # Ejemplo: Usando requests o la herramienta que uses para traer el texto/datos de la web
        # texto_actual_web = obtener_datos_de_la_web()
        
        # Simulación de obtención de datos de la web para el ejemplo:
        texto_actual_web = "DATOS_DE_LOS_RAIDS_AQUÍ..." 

        # 2. COMPARAMOS SI HUBO CAMBIOS
        if ultimo_contenido_web is None:
            # Primera ejecución, guardamos el estado base
            ultimo_contenido_web = texto_actual_web
            print("📌 [Monitoreo] Estado inicial de la web guardado.")
            return

        if texto_actual_web != ultimo_contenido_web:
            print("🚨 ¡Cambio detectado en la página oficial! Actualizando Excel...")
            
            # Actualizamos el registro con el nuevo contenido
            ultimo_contenido_web = texto_actual_web

            # 3. ACTUALIZAMOS EL EXCEL AUTOMÁTICAMENTE
            if os.path.exists(EXCEL_FILE_PATH):
                wb = openpyxl.load_workbook(EXCEL_FILE_PATH)
                # Aquí aplicas los cambios en tus hojas (CALCULO o PLANTILLA)
                # wb.save(EXCEL_FILE_PATH)
                print("✅ Excel actualizado con los nuevos datos de los raids.")
                
                # Opcional: Si quieres que avise a un canal de Discord específico cuando haya cambios
                # canal = client_discord.get_channel(TU_ID_DE_CANAL)
                # await canal.send("🚨 ¡Los horarios de los raids cambiaron en la web y ya actualicé el Excel!")
        else:
            print("✨ [Monitoreo] Sin cambios en la web. Todo sigue igual.")

    except Exception as e:
        print(f"⚠️ Error durante el monitoreo web: {e}")

@monitorear_cambios_web.before_loop
async def before_monitoreo():
    await client_discord.wait_until_ready()


# --- COMANDO !HORARIO PARA DISCORD ---
@client_discord.event
async def on_message(message):
    if message.author == client_discord.user:
        return

    content = message.content.lower().strip()

    # Comando para extraer la imagen unificada de los horarios desde la hoja IMAGEN_HORARIO
    if content == "!horario":
        print("🖼️ Buscando la imagen unificada de horarios en el Excel...")
        if not os.path.exists(EXCEL_FILE_PATH):
            await message.channel.send("⚠️ No se encontró el archivo Excel en el servidor.")
            return

        try:
            wb = openpyxl.load_workbook(EXCEL_FILE_PATH, data_only=True)
            if "IMAGEN_HORARIO" in wb.sheetnames:
                sheet = wb["IMAGEN_HORARIO"]
                if hasattr(sheet, '_images') and sheet._images:
                    img = sheet._images[0]
                    img_data = img._data()
                    
                    if img_data:
                        file_to_send = discord.File(io.BytesIO(img_data), filename="Horario_OKT_HTF.png")
                        await message.channel.send(
                            "⚔️ **Horarios Oficiales - OKT & HTF Ally** ⚔️", 
                            file=file_to_send
                        )
                        return

            await message.channel.send("⚠️ No se encontró ninguna imagen incrustada en la hoja 'IMAGEN_HORARIO'.")

        except Exception as e:
            print(f"Error al enviar la imagen: {e}")
            await message.channel.send(f"❌ Ocurrió un error al procesar la imagen: {e}")

client_discord.run(DISCORD_TOKEN)
