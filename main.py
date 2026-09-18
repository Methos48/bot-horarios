import os
import logging
import asyncio
from flask import Flask
import discord
from discord.ext import commands, tasks

import config
# Importa tus módulos generadores/procesadores cuando los subas:
# import entrada_paguina
# import generador_ronda
# import generador_horario

# Configuración de logs limpia
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("BotMain")

# Inicializar Flask para mantener vivo el contenedor (Healthcheck / Uptime)
app = Flask('')

@app.route('/')
def home():
    return "¡El bot de horarios está activo y operando con éxito!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    import threading
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()
    logger.info("Servidor Flask web (keep_alive) iniciado en el puerto 8080.")

# Configurar intents de Discord
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    logger.info(f"¡Bot conectado exitosamente como {bot.user}!")
    logger.info(f"Usando el archivo Excel local: {config.EXCEL_LOCAL}")
    
    # Iniciar tareas automáticas si ya están creadas en tus módulos
    if not auto_monitor_web.is_running():
        auto_monitor_web.start()

# Tarea automática en segundo plano (ejemplo cada 60 segundos)
@tasks.loop(seconds=60)
async def auto_monitor_web():
    logger.info("🔍 [Automático] Revisando la página web de los jefes...")
    try:
        # Aquí llamarías a la función de rastreo web de entrada_paguina.py
        # cambios_detectados = entrada_paguina.verificar_cambios()
        pass
    except Exception as e:
        logger.error(f"Error en el monitoreo web automático: {e}")

@auto_monitor_web.before_loop
async def before_auto_monitor():
    await bot.wait_until_ready()
    logger.info("⏳ Esperando a que el sistema esté listo para arrancar la revisión de la web...")

# Escucha de mensajes en el canal de carga de horarios
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Validar si el mensaje proviene del canal de carga configurado
    if config.CARGAR_HORARIO_CHANNEL_ID and message.channel.id == config.CARGAR_HORARIO_CHANNEL_ID:
        logger.info(f"📥 Bloque de texto detectado en el canal de carga (ID: {message.channel.id})")
        
        try:
            # Procesar datos del mensaje, actualizar Excel y generar imagen
            # ... tu lógica de procesamiento aquí ...
            
            # Limpiar el mensaje original del usuario para mantener orden
            await message.delete()
            logger.info("🗑️ Texto original eliminado limpiamente del canal.")
        except Exception as e:
        #   logger.error(f"Error procesando la entrada manual: {e}")
            pass

    await bot.process_commands(message)

if __name__ == "__main__":
    # Arrancar el servidor web de respaldo
    keep_alive()
    
    # Arrancar el bot de Discord utilizando el token de configuración
    if config.DISCORD_TOKEN:
        bot.run(config.DISCORD_TOKEN)
    else:
        logger.critical("❌ No se encontró el DISCORD_TOKEN en las variables de entorno.")
