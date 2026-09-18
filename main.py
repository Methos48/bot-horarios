import os
import logging
import asyncio
from flask import Flask
import discord
from discord.ext import commands, tasks

import config
import entrada_paguina
import entrada_texto
# Importa tus módulos generadores cuando los vayas subiendo:
# import generador_ronda
# import generador_horario

# Configuración de logs limpia
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("BotMain")

# --- MEMORIA EN TIEMPO REAL ---
# Almacenaremos aquí las tablas actualizadas por la web y por las entradas manuales de texto
MEMORIA_JEFES = {
    "tabla_1": [],
    "tabla_2": [],
    "horarios_manuales": []
}

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
    logger.info("Sistema operando completamente en memoria (sin archivos Excel).")
    
    # Iniciar la tarea automática de rastreo web
    if not auto_monitor_web.is_running():
        auto_monitor_web.start()

# Tarea automática en segundo plano (cada 60 segundos)
@tasks.loop(seconds=60)
async def auto_monitor_web():
    logger.info("🔍 [Automático] Rastreando la página web de los jefes...")
    try:
        # Llamamos a la entrada web para obtener las dos tablas ordenadas
        t1, t2 = entrada_paguina.obtener_datos_web()
        
        if t1 or t2:
            # Guardamos la información directamente en la memoria central del main
            MEMORIA_JEFES["tabla_1"] = t1
            MEMORIA_JEFES["tabla_2"] = t2
            logger.info(f"💾 Memoria actualizada (Web): Tabla 1 ({len(t1)} jefes) | Tabla 2 ({len(t2)} jefes)")
            
            # Aquí más adelante evaluaremos si hubo cambios para disparar las salidas (ej: generar imágenes)
            
    except Exception as e:
        logger.error(f"Error en el monitoreo web automático: {e}")

@auto_monitor_web.before_loop
async def before_auto_monitor():
    await bot.wait_until_ready()
    logger.info("⏳ Esperando a que el sistema esté listo para arrancar el rastreo web...")

# Escucha de mensajes en el canal de carga de horarios
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Validar si el mensaje proviene del canal de carga configurado en config.py
    if config.CARGAR_HORARIO_CHANNEL_ID and message.channel.id == config.CARGAR_HORARIO_CHANNEL_ID:
        logger.info(f"📥 Bloque de texto detectado en el canal de carga (ID: {message.channel.id})")
        
        try:
            # 1. Procesamos y filtramos el texto usando el módulo entrada_texto
            horarios_ordenados = entrada_texto.procesar_y_ordenar_texto(message.content)
            
            if horarios_ordenados:
                # 2. Guardamos la data limpia en la memoria central del main
                MEMORIA_JEFES["horarios_manuales"] = horarios_ordenados
                logger.info(f"💾 Memoria actualizada (Texto Manual): {len(horarios_ordenados)} registros cargados.")
                
                # Aquí más adelante llamaremos al generador de imágenes de horario correspondiente
            
            # 3. Limpiar el mensaje original del usuario para mantener el orden
            await message.delete()
            logger.info("🗑️ Texto original eliminado limpiamente del canal.")
        except Exception as e:
            logger.error(f"Error procesando la entrada de texto manual: {e}")

    await bot.process_commands(message)

if __name__ == "__main__":
    # Arrancar el servidor web de respaldo para Railway
    keep_alive()
    
    # Arrancar el bot de Discord utilizando el token de configuración
    if config.DISCORD_TOKEN:
        bot.run(config.DISCORD_TOKEN)
    else:
        logger.critical("❌ No se encontró el DISCORD_TOKEN en las variables de entorno.")
