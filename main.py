import os
import logging
import asyncio
from flask import Flask
import discord
from discord.ext import commands, tasks

import config
import entrada_paguina
import entrada_texto
import entrada_imagen

# --- MÓDULOS DE SALIDA ---
import salida_horario
import salida_ma
import salida_ronda
import salida_raid

# Configuración de logs limpia
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("BotMain")

# --- MEMORIA EN TIEMPO REAL ---
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

async def disparar_salidas(bot_instance):
    """
    Función centralizada para enviar la memoria actualizada a los 4 servicios de salida.
    """
    logger.info("🚀 Enviando datos actualizados a los servicios de salida...")
    try:
        # 1. salida_horario
        await salida_horario.ejecutar(bot_instance, MEMORIA_JEFES)
        
        # 2. salida_ma
        await salida_ma.ejecutar(bot_instance, MEMORIA_JEFES)
        
        # 3. salida_ronda
        await salida_ronda.ejecutar(bot_instance, MEMORIA_JEFES)
        
        # 4. salida_raid
        await salida_raid.ejecutar(bot_instance, MEMORIA_JEFES)
        
        logger.info("✅ Todos los servicios de salida ejecutados correctamente.")
    except Exception as e:
        logger.error(f"Error al enviar datos a los servicios de salida: {e}")

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
            
            # Enviar datos actualizados a los 4 servicios de salida
            await disparar_salidas(bot)
            
    except Exception as e:
        logger.error(f"Error en el monitoreo web automático: {e}")

@auto_monitor_web.before_loop
async def before_auto_monitor():
    await bot.wait_until_ready()
    logger.info("⏳ Esperando a que el sistema esté listo para arrancar el rastreo web...")

# Escucha de mensajes en el canal de carga de horarios (Texto o Imágenes)
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Validar si el mensaje proviene del canal de carga configurado en config.py
    if config.CARGAR_HORARIO_CHANNEL_ID and message.channel.id == config.CARGAR_HORARIO_CHANNEL_ID:
        try:
            horarios_procesados = []

            # 1. CASO IMAGEN: Si el usuario adjuntó una imagen
            if message.attachments:
                for attachment in message.attachments:
                    if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp']):
                        logger.info(f"🖼️ Imagen detectada en el canal de carga: {attachment.filename}")
                        imagen_bytes = await attachment.read()
                        # Procesamos con entrada_imagen (Gemini + filtros + orden de vivos)
                        horarios_procesados = entrada_imagen.procesar_imagen_jefes(imagen_bytes)
                        break

            # 2. CASO TEXTO: Si el usuario envió un bloque de texto plano
            elif message.content:
                logger.info("📥 Bloque de texto detectado en el canal de carga.")
                # Procesamos con entrada_texto (filtros + ordenamiento)
                horarios_procesados = entrada_texto.procesar_y_ordenar_texto(message.content)

            # Si obtuvimos resultados válidos, actualizamos la memoria
            if horarios_procesados:
                MEMORIA_JEFES["horarios_manuales"] = horarios_procesados
                logger.info(f"💾 Memoria actualizada (Entrada Manual): {len(horarios_procesados)} registros cargados.")
                
                # Enviar datos actualizados a los 4 servicios de salida
                await disparar_salidas(bot)

            # 3. Limpiar el mensaje original del usuario para mantener el canal impecable
            await message.delete()
            logger.info("🗑️ Mensaje original eliminado limpiamente del canal.")

        except Exception as e:
            logger.error(f"Error procesando la entrada manual en el canal de carga: {e}")

    await bot.process_commands(message)

if __name__ == "__main__":
    # Arrancar el servidor web de respaldo para Railway
    keep_alive()
    
    # Arrancar el bot de Discord utilizando el token de configuración
    if config.DISCORD_TOKEN:
        bot.run(config.DISCORD_TOKEN)
    else:
        logger.critical("❌ No se encontró el DISCORD_TOKEN en las variables de entorno.")
