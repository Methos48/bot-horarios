import os
import logging
import asyncio
from datetime import datetime
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
    "tabla_60_plus": [],  # Tabla 1 (60+) integrada con manuales
    "tabla_raids": [],    # Tabla 2 (la otra lista, independiente)
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

def ordenar_y_priorizar(lista_jefes):
    """
    Ordena una lista de diccionarios de jefes:
    1. Primero los que están 'Alive' o 'Vivo'.
    2. Luego cronológicamente por fecha/hora (lo más cercano arriba).
    """
    if not lista_jefes:
        return []

    def clave_orden(item):
        tiempo = str(item.get("tiempo_str", "")).lower()
        es_vivo = "alive" in tiempo or "vivo" in tiempo
        return (0 if es_vivo else 1, item.get("datetime", datetime.max))

    return sorted(lista_jefes, key=clave_orden)

def procesar_integracion_y_filtrado():
    """
    Integra la lista 60+ con los manuales, ordena ambas tablas,
    y aplica los filtros específicos para cada salida.
    """
    # 1. Integrar tabla 60+ con manuales (si los hay)
    tabla_60_base = MEMORIA_JEFES.get("tabla_60_plus", [])
    manuales = MEMORIA_JEFES.get("horarios_manuales", [])
    tabla_60_integrada = tabla_60_base + manuales
    
    # Ordenar ambas tablas principales (la otra tabla de raids NUNCA se integra con nada, solo se ordena)
    tabla_60_ordenada = ordenar_y_priorizar(tabla_60_integrada)
    tabla_raids_ordenada = ordenar_y_priorizar(MEMORIA_JEFES.get("tabla_raids", []))

    # Consolidado total para 'ronda' (integra todo)
    todos_los_datos = ordenar_y_priorizar(tabla_60_ordenada + tabla_raids_ordenada)

    # 2. Filtrados específicos
    wh_horario = {
        "valakas", "core", "orfen", "antharas", "baium", "zaken", 
        "frintezza", "fafurion", "fafureon", "queen ant", "freya", 
        "zariche", "asedio", "p v p", "x 9", "foto mes"
    }
    
    wh_ma = {"valakas", "antharas", "fafurion", "fafureon"}

    datos_horario = [j for j in todos_los_datos if j.get("nombre", "").strip().lower() in wh_horario]
    datos_ma = [j for j in todos_los_datos if j.get("nombre", "").strip().lower() in wh_ma]

    return {
        "tabla_60_plus": tabla_60_ordenada,
        "tabla_raids": tabla_raids_ordenada,
        "salida_horario_data": datos_horario,
        "salida_ma_data": datos_ma,
        "salida_ronda_data": todos_los_datos,
        "salida_raid_data": tabla_raids_ordenada  # Recibe exclusivamente la otra tabla ordenada
    }

async def disparar_salidas(bot_instance):
    """
    Envía los datos procesados y filtrados a los 4 servicios de salida.
    """
    logger.info("🚀 Procesando y enviando datos filtrados a los servicios de salida...")
    try:
        datos_procesados = procesar_integracion_y_filtrado()

        # 1. salida_horario
        await salida_horario.ejecutar(bot_instance, datos_procesados["salida_horario_data"])
        
        # 2. salida_ma
        await salida_ma.ejecutar(bot_instance, datos_procesados["salida_ma_data"])
        
        # 3. salida_ronda (Todos los jefes integrados y ordenados)
        await salida_ronda.ejecutar(bot_instance, datos_procesados["salida_ronda_data"])
        
        # 4. salida_raid (La otra tabla independiente ordenada)
        await salida_raid.ejecutar(bot_instance, datos_procesados["salida_raid_data"])
        
        logger.info("✅ Todos los servicios de salida ejecutados y despachados con éxito.")
    except Exception as e:
        logger.error(f"Error al despachar los servicios de salida: {e}")

@bot.event
async def on_ready():
    logger.info(f"¡Bot conectado exitosamente como {bot.user}!")
    logger.info("Sistema operando completamente en memoria (sin archivos Excel).")
    
    if not auto_monitor_web.is_running():
        auto_monitor_web.start()

# Tarea automática en segundo plano (cada 60 segundos)
@tasks.loop(seconds=60)
async def auto_monitor_web():
    logger.info("🔍 [Automático] Rastreando la página web de los jefes...")
    try:
        t1, t2 = entrada_paguina.obtener_datos_web()
        
        if t1 or t2:
            MEMORIA_JEFES["tabla_60_plus"] = t1
            MEMORIA_JEFES["tabla_raids"] = t2
            logger.info(f"💾 Memoria actualizada (Web): Tabla 60+ ({len(t1)} jefes) | Tabla Raids ({len(t2)} jefes)")
            
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

    if config.CARGAR_HORARIO_CHANNEL_ID and message.channel.id == config.CARGAR_HORARIO_CHANNEL_ID:
        try:
            horarios_procesados = []

            # 1. CASO IMAGEN
            if message.attachments:
                for attachment in message.attachments:
                    if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp']):
                        logger.info(f"🖼️ Imagen detectada en el canal de carga: {attachment.filename}")
                        imagen_bytes = await attachment.read()
                        horarios_procesados = entrada_imagen.procesar_imagen_jefes(imagen_bytes)
                        break

            # 2. CASO TEXTO
            elif message.content:
                logger.info("📥 Bloque de texto detectado en el canal de carga.")
                horarios_procesados = entrada_texto.procesar_y_ordenar_texto(message.content)

            if horarios_procesados:
                MEMORIA_JEFES["horarios_manuales"] = horarios_procesados
                logger.info(f"💾 Memoria actualizada (Entrada Manual): {len(horarios_procesados)} registros cargados.")
                
                await disparar_salidas(bot)

            await message.delete()
            logger.info("🗑️ Mensaje original eliminado limpiamente del canal.")

        except Exception as e:
            logger.error(f"Error procesando la entrada manual en el canal de carga: {e}")

    await bot.process_commands(message)

if __name__ == "__main__":
    keep_alive()
    
    if config.DISCORD_TOKEN:
        bot.run(config.DISCORD_TOKEN)
    else:
        logger.critical("❌ No se encontró el DISCORD_TOKEN en las variables de entorno.")
