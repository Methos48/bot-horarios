import os
import json
import logging
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from flask import Flask
import discord
from discord.ext import commands, tasks

import config
import entrada_pagina
import entrada_texto
import entrada_imagen

# --- MÓDULOS DE SALIDA ---
import salida_horario
import salida_ma
import salida_ronda
import salida_raid
import salida_low

# Configuración de logs limpia
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("BotMain")

# Definir la zona horaria estricta de Argentina (tomando config.TZ o por defecto)
ZONA_ARGENTINA = ZoneInfo(getattr(config, "TZ", "America/Argentina/Buenos_Aires"))

# ==============================================================================
# ⚙️ CONFIGURACIÓN DE OFFSET WEB (Ajuste de hora para la página web)
# Modifica este número a voluntad:
#   - 0 (cero): Deja la hora de la página tal cual está.
#   - Positivo (ej. 1, 2): Suma horas para adelantar el reloj.
#   - Negativo (ej. -1, -2): Resta horas para atrasar el reloj.
# ==============================================================================
HORA_OFFSET_WEB = 1

# --- ARCHIVO DE PERSISTENCIA JSON ---
ARCHIVO_JSON = "jefes_activos.json"

# --- DICCIONARIO DE NIVELES PARA ENTRADAS MANUALES ---
NIVELES_JEFE_MANUAL = {
    "queen ant": 40,
    "core": 50,
    "orfen": 50,
    "zaken": 60,
    "baium": 75,
    "frintezza": 85,
    "freya": 85,
    "zariche": 85,
    "balrog": 85,
    "electrica": 85,
    "electrical": 85
}

def asignar_nivel_manual(lista_jefes):
    """Asigna el nivel correspondiente a cada jefe manual basándose en su nombre."""
    for item in lista_jefes:
        nombre_limpio = item.get("nombre", "").strip().lower()
        # Buscar coincidencia exacta o parcial en el diccionario
        for clave, nivel in NIVELES_JEFE_MANUAL.items():
            if clave in nombre_limpio:
                item["nivel"] = nivel
                break
        else:
            # Valor por defecto si no está en la lista
            if "nivel" not in item:
                item["nivel"] = 85
    return lista_jefes

def item_a_serializable(item):
    """Convierte objetos datetime a formato ISO para poder guardarlos en JSON."""
    item_copia = item.copy()
    dt = item_copia.get("datetime")
    if isinstance(dt, datetime):
        item_copia["datetime_iso"] = dt.isoformat()
    if "datetime" in item_copia:
        del item_copia["datetime"]
    return item_copia

def item_desde_serializable(item):
    """Restaura los objetos datetime y la zona horaria al leer el JSON."""
    item_copia = item.copy()
    dt_iso = item_copia.pop("datetime_iso", None)
    if dt_iso:
        try:
            item_copia["datetime"] = datetime.fromisoformat(dt_iso)
        except Exception:
            item_copia["datetime"] = None
    else:
        tiempo_str = item_copia.get("tiempo_str", "")
        if tiempo_str and tiempo_str not in ["VIVO", "ALIVE"]:
            try:
                item_copia["datetime"] = datetime.strptime(tiempo_str, "%d/%m/%Y %H:%M").replace(tzinfo=ZONA_ARGENTINA)
            except Exception:
                item_copia["datetime"] = None
        else:
            es_v = item_copia.get("estado") in ["VIVO", "ALIVE"] or item_copia.get("es_vivo", False)
            item_copia["datetime"] = datetime.min.replace(tzinfo=ZONA_ARGENTINA) if es_v else datetime.max.replace(tzinfo=ZONA_ARGENTINA)
    return item_copia

def cargar_memoria_desde_json():
    """Carga y deserializa el estado de los jefes desde el archivo JSON."""
    if os.path.exists(ARCHIVO_JSON):
        try:
            with open(ARCHIVO_JSON, 'r', encoding='utf-8') as f:
                data = json.load(f)
                t1 = [item_desde_serializable(i) for i in data.get("tabla_60_plus", [])]
                t2 = [item_desde_serializable(i) for i in data.get("tabla_raids", [])]
                t_epic = [item_desde_serializable(i) for i in data.get("tabla_epic", [])]
                manuales = [item_desde_serializable(i) for i in data.get("horarios_manuales", [])]
                logger.info("📂 Memoria cargada exitosamente desde el archivo JSON.")
                return {
                    "tabla_60_plus": t1,
                    "tabla_raids": t2,
                    "tabla_epic": t_epic,
                    "horarios_manuales": manuales
                }
        except Exception as e:
            logger.error(f"Error al cargar JSON en memoria: {e}")
    return {
        "tabla_60_plus": [],
        "tabla_raids": [],
        "tabla_epic": [],
        "horarios_manuales": []
    }

def guardar_memoria_a_json_completa():
    """Guarda toda la memoria actual de jefes en el archivo JSON de manera segura."""
    try:
        data = {
            "tabla_60_plus": [item_a_serializable(i) for i in MEMORIA_JEFES.get("tabla_60_plus", [])],
            "tabla_raids": [item_a_serializable(i) for i in MEMORIA_JEFES.get("tabla_raids", [])],
            "tabla_epic": [item_a_serializable(i) for i in MEMORIA_JEFES.get("tabla_epic", [])],
            "horarios_manuales": [item_a_serializable(i) for i in MEMORIA_JEFES.get("horarios_manuales", [])]
        }
        with open(ARCHIVO_JSON, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        logger.info(f"💾 Archivo '{ARCHIVO_JSON}' actualizado correctamente.")
    except Exception as e:
        logger.error(f"Error al guardar memoria completa en JSON: {e}")

def aplicar_offset_web(lista_jefes, offset_horas):
    """Aplica el desplazamiento de horas (positivo, negativo o cero) configurado en HORA_OFFSET_WEB."""
    if offset_horas == 0 or not lista_jefes:
        return lista_jefes
     
    lista_modificada = []
    for item in lista_jefes:
        item_copia = item.copy()
        dt = item_copia.get("datetime")
        tiempo_str = item_copia.get("tiempo_str", "").strip()
        
        # Si el jefe está vivo o sin hora, se respeta tal cual
        if tiempo_str.upper() in ["VIVO", "ALIVE", "-"]:
            lista_modificada.append(item_copia)
            continue

        dt_ajustado = None

        # 1. Ajustar el datetime existente si es válido
        if dt and isinstance(dt, datetime) and (1900 < dt.year < 9999):
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZONA_ARGENTINA)
            dt_ajustado = dt + timedelta(hours=offset_horas)
        
        # 2. Si no hay datetime pero hay texto de hora/fecha, parsearlo y ajustarlo
        elif tiempo_str:
            try:
                if ":" in tiempo_str and len(tiempo_str) <= 5:
                    partes = tiempo_str.split(":")
                    dt_base = datetime.now(ZONA_ARGENTINA).replace(hour=int(partes[0]), minute=int(partes[1]), second=0, microsecond=0)
                    dt_ajustado = dt_base + timedelta(hours=offset_horas)
                else:
                    dt_parsed = datetime.strptime(tiempo_str, "%d/%m/%Y %H:%M")
                    dt_ajustado = dt_parsed.replace(tzinfo=ZONA_ARGENTINA) + timedelta(hours=offset_horas)
            except Exception as e:
                logger.warning(f"No se pudo parsear el tiempo_str '{tiempo_str}' para aplicar offset: {e}")

        # 3. Consolidar los cambios en el item copiado
        if dt_ajustado:
            item_copia["datetime"] = dt_ajustado
            if len(tiempo_str) <= 5 and ":" in tiempo_str:
                item_copia["tiempo_str"] = dt_ajustado.strftime("%H:%M")
            else:
                item_copia["tiempo_str"] = dt_ajustado.strftime("%d/%m/%Y %H:%M")

        lista_modificada.append(item_copia)
    return lista_modificada

def listas_han_cambiado(lista_vieja, lista_nueva):
    """Compara dos listas de jefes para detectar si hubo cambios en estado, nivel o tiempo."""
    if len(lista_vieja) != len(lista_nueva):
        return True
    dict_viejo = {j.get("nombre", "").lower(): j for j in lista_vieja}
    dict_nuevo = {j.get("nombre", "").lower(): j for j in lista_nueva}
     
    if set(dict_viejo.keys()) != set(dict_nuevo.keys()):
        return True
         
    for nombre, nuevo_item in dict_nuevo.items():
        viejo_item = dict_viejo[nombre]
        if (viejo_item.get("estado") != nuevo_item.get("estado") or
            viejo_item.get("tiempo_str") != nuevo_item.get("tiempo_str") or
            viejo_item.get("nivel") != nuevo_item.get("nivel")):
            return True
             
    return False

# --- MEMORIA EN TIEMPO REAL INICIALIZADA DESDE JSON ---
MEMORIA_JEFES = cargar_memoria_desde_json()

# Inicializar Flask para mantener vivo el contenedor (Healthcheck / Uptime)
app = Flask('')

@app.route('/')
def home():
    return "¡El bot de horarios está activo y operando con éxito (Hora Argentina)!"

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
    Ordena una lista de diccionarios de jefes considerando hora de Argentina:
    1. Primero los que están 'Alive' o 'Vivo'.
    2. Luego cronológicamente por fecha/hora (lo más cercano arriba).
    """
    if not lista_jefes:
        return []

    def clave_orden(item):
        tiempo = str(item.get("tiempo_str", "")).lower()
        es_vivo = "alive" in tiempo or "vivo" in tiempo or item.get("es_vivo", False)
         
        dt = item.get("datetime")
        if dt is None:
            dt = datetime.max.replace(tzinfo=ZONA_ARGENTINA)
        elif dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZONA_ARGENTINA)
        else:
            dt = dt.astimezone(ZONA_ARGENTINA)

        return (0 if es_vivo else 1, dt)

    return sorted(lista_jefes, key=clave_orden)

def procesar_integracion_y_filtrado():
    """
    Integrar lista 60+, tabla de raids, epic bosses y manuales,
    ordenando las tablas con criterio argentino y aplicando filtros.
    """
    tabla_60_base = MEMORIA_JEFES.get("tabla_60_plus", [])
    manuales = MEMORIA_JEFES.get("horarios_manuales", [])
    tabla_60_integrada = tabla_60_base + manuales
     
    tabla_60_ordenada = ordenar_y_priorizar(tabla_60_integrada)
    tabla_raids_ordenada = ordenar_y_priorizar(MEMORIA_JEFES.get("tabla_raids", []))
    tabla_epic_ordenada = ordenar_y_priorizar(MEMORIA_JEFES.get("tabla_epic", []))

    todos_los_datos = ordenar_y_priorizar(tabla_60_ordenada + tabla_raids_ordenada + tabla_epic_ordenada)

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
        "tabla_epic": tabla_epic_ordenada,
        "salida_horario_data": datos_horario,
        "salida_ma_data": datos_ma,
        "salida_ronda_data": todos_los_datos,
        "salida_low_data": tabla_raids_ordenada
    }

async def disparar_salidas_web(bot_instance):
    """Despacha las salidas web y entrega toda la información unificada a salida_raid para su evaluación interna."""
    logger.info("🚀 [Web] Procesando y enviando datos a salida_low, salida_ronda y salida_raid...")
    try:
        datos_procesados = procesar_integracion_y_filtrado()
        await salida_ronda.ejecutar(bot_instance, datos_procesados["salida_ronda_data"])
        await salida_low.ejecutar(bot_instance, datos_procesados["salida_low_data"])
         
        # Unificamos todas las listas de la memoria para dárselas por completo a salida_raid
        todos_los_jefes_unificados = (
            MEMORIA_JEFES.get("tabla_60_plus", []) + 
            MEMORIA_JEFES.get("tabla_raids", []) + 
            MEMORIA_JEFES.get("tabla_epic", []) +
            MEMORIA_JEFES.get("horarios_manuales", [])
        )
        await salida_raid.ejecutar(bot_instance, todos_los_jefes_unificados)
         
        logger.info("✅ Servicios de salida web ejecutados con éxito.")
    except Exception as e:
        logger.error(f"Error al despachar los servicios de salida web: {e}")

async def disparar_salidas_manuales(bot_instance):
    """Despacha únicamente las salidas asignadas a entrada_imagen.py o entrada_texto.py."""
    logger.info("🚀 [Manual] Procesando y enviando datos filtrados a horario, ma, ronda y raid...")
    try:
        datos_procesados = procesar_integracion_y_filtrado()
        await salida_horario.ejecutar(bot_instance, datos_procesados["salida_horario_data"])
        await salida_ma.ejecutar(bot_instance, datos_procesados["salida_ma_data"])
        await salida_ronda.ejecutar(bot_instance, datos_procesados["salida_ronda_data"])
         
        # Unificamos todas las listas también para las salidas manuales
        todos_los_jefes_unificados = (
            MEMORIA_JEFES.get("tabla_60_plus", []) + 
            MEMORIA_JEFES.get("tabla_raids", []) + 
            MEMORIA_JEFES.get("tabla_epic", []) +
            MEMORIA_JEFES.get("horarios_manuales", [])
        )
        await salida_raid.ejecutar(bot_instance, todos_los_jefes_unificados)
         
        logger.info("✅ Servicios de salida manual ejecutados con éxito.")
    except Exception as e:
        logger.error(f"Error al despachar los servicios de salida manuales: {e}")

@bot.event
async def on_ready():
    hora_actual_arg = datetime.now(ZONA_ARGENTINA).strftime('%Y-%m-%d %H:%M:%S')
    logger.info(f"¡Bot conectado exitosamente como {bot.user}!")
    logger.info(f"⏰ Hora actual del sistema (Argentina): {hora_actual_arg}")
    logger.info(f"⚙️ Offset aplicado a listas web (entrada_pagina): {HORA_OFFSET_WEB} hora(s)")
    logger.info("Sistema operando completamente en memoria y JSON bajo zona horaria de Argentina.")
     
    if not auto_monitor_web.is_running():
        auto_monitor_web.start()

# Tarea automática en segundo plano (cada 60 segundos) - Viene de entrada_pagina.py
@tasks.loop(seconds=60)
async def auto_monitor_web():
    logger.info("🔍 [Automático] Rastreando la página web de los jefes...")
    try:
        t1_crudo, t2_crudo = entrada_pagina.obtener_datos_web()
        t_epic_crudo = entrada_pagina.obtener_datos_epic_web()
          
        # Aplicamos el offset de inmediato a la data cruda de entrada_pagina
        t1 = aplicar_offset_web(t1_crudo, HORA_OFFSET_WEB)
        t2 = aplicar_offset_web(t2_crudo, HORA_OFFSET_WEB)
        t_epic = aplicar_offset_web(t_epic_crudo, HORA_OFFSET_WEB)
          
        if t1 or t2 or t_epic:
            vieja_t1 = MEMORIA_JEFES.get("tabla_60_plus", [])
            vieja_t2 = MEMORIA_JEFES.get("tabla_raids", [])
            vieja_t_epic = MEMORIA_JEFES.get("tabla_epic", [])
              
            cambio_t1 = listas_han_cambiado(vieja_t1, t1)
            cambio_t2 = listas_han_cambiado(vieja_t2, t2)
            cambio_t_epic = listas_han_cambiado(vieja_t_epic, t_epic)
              
            if cambio_t1 or cambio_t2 or cambio_t_epic:
                MEMORIA_JEFES["tabla_60_plus"] = t1
                MEMORIA_JEFES["tabla_raids"] = t2
                MEMORIA_JEFES["tabla_epic"] = t_epic
                guardar_memoria_a_json_completa()
                logger.info(f"💾 Memoria y JSON actualizados por cambios (Web con offset {HORA_OFFSET_WEB}h): Tabla 60+ ({len(t1)}) | Raids ({len(t2)}) | Epic Bosses ({len(t_epic)})")
                  
                await disparar_salidas_web(bot)
            else:
                logger.info("🔍 [Automático] No se detectaron cambios en los jefes de la web.")
          
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

            # 1. CASO IMAGEN: Delega a entrada_imagen.py (procesamiento asíncrono y borrado interno)
            if message.attachments:
                logger.info("🖼️ Adjunto(s) detectado(s) en el canal de carga. Procesando con entrada_imagen...")
                horarios_procesados = await entrada_imagen.procesar_mensaje_imagenes(message)

            # 2. CASO TEXTO: Delega a entrada_texto.py
            elif message.content:
                logger.info("📥 Bloque de texto detectado en el canal de carga. Procesando con entrada_texto...")
                horarios_procesados = entrada_texto.procesar_y_ordenar_texto(message.content)
                # Borrado del mensaje de texto original tras procesarlo
                try:
                    await message.delete()
                    logger.info("🗑️ Mensaje de texto original eliminado limpiamente del canal.")
                except Exception as e:
                    logger.error(f"No se pudo eliminar el mensaje de texto original: {e}")

            if horarios_procesados:
                # Asignar los niveles correspondientes antes de guardar en memoria
                horarios_procesados = asignar_nivel_manual(horarios_procesados)

                MEMORIA_JEFES["horarios_manuales"] = horarios_procesados
                guardar_memoria_a_json_completa()
                logger.info(f"💾 Memoria y JSON actualizados (Entrada Manual): {len(horarios_procesados)} registros cargados con sus niveles.")
                 
                await disparar_salidas_manuales(bot)

        except Exception as e:
            logger.error(f"Error procesando la entrada manual en el canal de carga: {e}")

    await bot.process_commands(message)

if __name__ == "__main__":
    keep_alive()
     
    if config.DISCORD_TOKEN:
        bot.run(config.DISCORD_TOKEN)
    else:
        logger.critical("❌ No se encontró el DISCORD_TOKEN en las variables de entorno.")
