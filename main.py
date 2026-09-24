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

# Definir la zona horaria estricta de Argentina
ZONA_ARGENTINA = ZoneInfo(getattr(config, "TZ", "America/Argentina/Buenos_Aires"))

# ==============================================================================
# ⚙️ CONFIGURACIÓN DE OFFSET WEB (Ajuste de hora para la página web)
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
        for clave, nivel in NIVELES_JEFE_MANUAL.items():
            if clave in nombre_limpio:
                item["nivel"] = nivel
                break
        else:
            if "nivel" not in item:
                item["nivel"] = 85
    return lista_jefes

def limpiar_duplicados_por_nombre(lista_jefes):
    """
    GARANTÍA ABSOLUTA: Agrupa por nombre en minúsculas y asegura que 
    exista estrictamente un (1) solo registro por cada jefe.
    Si hay duplicados, se queda con el más reciente o el último procesado.
    """
    if not lista_jefes:
        return []
     
    dict_unicos = {}
    for item in lista_jefes:
        nombre = str(item.get("nombre", "")).strip().lower()
        if not nombre:
            continue
         
        # Filtramos también por seguridad los que tengan tiempo inválido o "-" si ya tenemos uno válido
        tiempo = str(item.get("tiempo_str", "")).strip()
         
        if nombre not in dict_unicos:
            dict_unicos[nombre] = item
        else:
            # Si ya existía, priorizamos el que tenga un tiempo válido por encima de un "-"
            tiempo_existente = str(dict_unicos[nombre].get("tiempo_str", "")).strip()
            if tiempo_existente in ["-", "", "None"] and tiempo not in ["-", "", "None"]:
                dict_unicos[nombre] = item
            elif tiempo not in ["-", "", "None"]:
                # Si ambos son válidos, actualizamos con el nuevo
                dict_unicos[nombre] = item

    return list(dict_unicos.values())

def item_a_serializable(item):
    item_copia = item.copy()
    dt = item_copia.get("datetime")
    if isinstance(dt, datetime):
        item_copia["datetime_iso"] = dt.isoformat()
    if "datetime" in item_copia:
        del item_copia["datetime"]
    return item_copia

def item_desde_serializable(item):
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
    if os.path.exists(ARCHIVO_JSON):
        try:
            with open(ARCHIVO_JSON, 'r', encoding='utf-8') as f:
                data = json.load(f)
                t1 = limpiar_duplicados_por_nombre([item_desde_serializable(i) for i in data.get("tabla_60_plus", [])])
                t2 = limpiar_duplicados_por_nombre([item_desde_serializable(i) for i in data.get("tabla_raids", [])])
                t_epic = limpiar_duplicados_por_nombre([item_desde_serializable(i) for i in data.get("tabla_epic", [])])
                manuales = limpiar_duplicados_por_nombre([item_desde_serializable(i) for i in data.get("horarios_manuales", [])])
                logger.info("📂 Memoria cargada y depurada de duplicados desde el JSON.")
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
    try:
        data = {
            "tabla_60_plus": [item_a_serializable(i) for i in MEMORIA_JEFES.get("tabla_60_plus", [])],
            "tabla_raids": [item_a_serializable(i) for i in MEMORIA_JEFES.get("tabla_raids", [])],
            "tabla_epic": [item_a_serializable(i) for i in MEMORIA_JEFES.get("tabla_epic", [])],
            "horarios_manuales": [item_a_serializable(i) for i in MEMORIA_JEFES.get("horarios_manuales", [])]
        }
        with open(ARCHIVO_JSON, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        logger.info(f"💾 Archivo '{ARCHIVO_JSON}' guardado sin duplicados.")
    except Exception as e:
        logger.error(f"Error al guardar memoria en JSON: {e}")

def aplicar_offset_web(lista_jefes, offset_horas):
    if offset_horas == 0 or not lista_jefes:
        return lista_jefes
     
    lista_modificada = []
    for item in lista_jefes:
        item_copia = item.copy()
        dt = item_copia.get("datetime")
        tiempo_str = item_copia.get("tiempo_str", "").strip()
         
        if tiempo_str.upper() in ["VIVO", "ALIVE", "-"]:
            lista_modificada.append(item_copia)
            continue

        dt_ajustado = None
        if dt and isinstance(dt, datetime) and (1900 < dt.year < 9999):
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZONA_ARGENTINA)
            dt_ajustado = dt + timedelta(hours=offset_horas)
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
                logger.warning(f"No se pudo parsear el tiempo_str '{tiempo_str}': {e}")

        if dt_ajustado:
            item_copia["datetime"] = dt_ajustado
            if len(tiempo_str) <= 5 and ":" in tiempo_str:
                item_copia["tiempo_str"] = dt_ajustado.strftime("%H:%M")
            else:
                item_copia["tiempo_str"] = dt_ajustado.strftime("%d/%m/%Y %H:%M")

        lista_modificada.append(item_copia)
    return limpiar_duplicados_por_nombre(lista_modificada)

def listas_han_cambiado(lista_vieja, lista_nueva):
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

# --- MEMORIA EN TIEMPO REAL ---
MEMORIA_JEFES = cargar_memoria_desde_json()

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
    logger.info("Servidor Flask web iniciado en el puerto 8080.")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

def ordenar_y_priorizar(lista_jefes):
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

    # Aseguramos que antes de ordenar, no pasen duplicados
    lista_limpia = limpiar_duplicados_por_nombre(lista_jefes)
    return sorted(lista_limpia, key=clave_orden)

def procesar_integracion_y_filtrado():
    tabla_60_base = MEMORIA_JEFES.get("tabla_60_plus", [])
    manuales = MEMORIA_JEFES.get("horarios_manuales", [])
     
    # Fusión limpia previniendo duplicados
    tabla_60_integrada = limpiar_duplicados_por_nombre(tabla_60_base + manuales)
     
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
        "salida_horario_data": limpiar_duplicados_por_nombre(datos_horario),
        "salida_ma_data": limpiar_duplicados_por_nombre(datos_ma),
        "salida_ronda_data": limpiar_duplicados_por_nombre(todos_los_datos),
        "salida_low_data": limpiar_duplicados_por_nombre(tabla_raids_ordenada)
    }

async def disparar_salidas_web(bot_instance):
    logger.info("🚀 [Web] Procesando salidas web...")
    try:
        datos_procesados = procesar_integracion_y_filtrado()
        await salida_ronda.ejecutar(bot_instance, datos_procesados["salida_ronda_data"])
        await salida_low.ejecutar(bot_instance, datos_procesados["salida_low_data"])
         
        todos_los_jefes_unificados = limpiar_duplicados_por_nombre(
            MEMORIA_JEFES.get("tabla_60_plus", []) + 
            MEMORIA_JEFES.get("tabla_raids", []) + 
            MEMORIA_JEFES.get("tabla_epic", []) +
            MEMORIA_JEFES.get("horarios_manuales", [])
        )
        await salida_raid.ejecutar(bot_instance, todos_los_jefes_unificados)
        logger.info("✅ Salidas web ejecutadas.")
    except Exception as e:
        logger.error(f"Error en salidas web: {e}")

async def disparar_salidas_manuales(bot_instance):
    logger.info("🚀 [Manual] Procesando salidas manuales...")
    try:
        datos_procesados = procesar_integracion_y_filtrado()
        await salida_horario.ejecutar(bot_instance, datos_procesados["salida_horario_data"])
        await salida_ma.ejecutar(bot_instance, datos_procesados["salida_ma_data"])
        await salida_ronda.ejecutar(bot_instance, datos_procesados["salida_ronda_data"])
         
        todos_los_jefes_unificados = limpiar_duplicados_por_nombre(
            MEMORIA_JEFES.get("tabla_60_plus", []) + 
            MEMORIA_JEFES.get("tabla_raids", []) + 
            MEMORIA_JEFES.get("tabla_epic", []) +
            MEMORIA_JEFES.get("horarios_manuales", [])
        )
        await salida_raid.ejecutar(bot_instance, todos_los_jefes_unificados)
        logger.info("✅ Salidas manuales ejecutadas.")
    except Exception as e:
        logger.error(f"Error en salidas manuales: {e}")

@bot.event
async def on_ready():
    logger.info(f"¡Bot conectado como {bot.user}!")
    if not auto_monitor_web.is_running():
        auto_monitor_web.start()

@tasks.loop(seconds=60)
async def auto_monitor_web():
    try:
        t1_crudo, t2_crudo = entrada_pagina.obtener_datos_web()
        t_epic_crudo = entrada_pagina.obtener_datos_epic_web()
          
        t1 = aplicar_offset_web(t1_crudo, HORA_OFFSET_WEB)
        t2 = aplicar_offset_web(t2_crudo, HORA_OFFSET_WEB)
        t_epic = aplicar_offset_web(t_epic_crudo, HORA_OFFSET_WEB)
          
        if t1 or t2 or t_epic:
            vieja_t1 = MEMORIA_JEFES.get("tabla_60_plus", [])
            vieja_t2 = MEMORIA_JEFES.get("tabla_raids", [])
            vieja_t_epic = MEMORIA_JEFES.get("tabla_epic", [])
              
            if listas_han_cambiado(vieja_t1, t1) or listas_han_cambiado(vieja_t2, t2) or listas_han_cambiado(vieja_t_epic, t_epic):
                MEMORIA_JEFES["tabla_60_plus"] = limpiar_duplicados_por_nombre(t1)
                MEMORIA_JEFES["tabla_raids"] = limpiar_duplicados_por_nombre(t2)
                MEMORIA_JEFES["tabla_epic"] = limpiar_duplicados_por_nombre(t_epic)
                guardar_memoria_a_json_completa()
                await disparar_salidas_web(bot)
    except Exception as e:
        logger.error(f"Error en monitoreo web: {e}")

@auto_monitor_web.before_loop
async def before_auto_monitor():
    await bot.wait_until_ready()

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if config.CARGAR_HORARIO_CHANNEL_ID and message.channel.id == config.CARGAR_HORARIO_CHANNEL_ID:
        try:
            nuevos_registros = []

            if message.attachments:
                logger.info("🖼️ Procesando imagen con entrada_imagen...")
                nuevos_registros = await entrada_imagen.procesar_mensaje_imagenes(message)
            elif message.content:
                logger.info("📥 Procesando texto con entrada_texto...")
                nuevos_registros = entrada_texto.procesar_y_ordenar_texto(message.content)
                try:
                    await message.delete()
                except Exception:
                    pass

            if nuevos_registros:
                # 1. Asignar niveles
                nuevos_registros = asignar_nivel_manual(nuevos_registros)

                # 2. Obtener manuales actuales
                manuales_actuales = MEMORIA_JEFES.get("horarios_manuales", [])
                
                # Creamos un diccionario de respaldo de los actuales para proteger datos buenos
                dict_actuales = {str(item.get("nombre", "")).strip().lower(): item for item in manuales_actuales}

                # 3. Validar y fusionar protegiendo contra tiempos vacíos o "-"
                registros_depurados = []
                for nuevo in nuevos_registros:
                    nombre_nuevo = str(nuevo.get("nombre", "")).strip().lower()
                    tiempo_nuevo = str(nuevo.get("tiempo_str", "")).strip()

                    # Si el nuevo viene con "-", vacío o "None", revisamos si ya teníamos un horario válido
                    if tiempo_nuevo in ["-", "", "None"]:
                        if nombre_nuevo in dict_actuales:
                            tiempo_viejo = str(dict_actuales[nombre_nuevo].get("tiempo_str", "")).strip()
                            # Si el que ya teníamos era bueno, conservamos el viejo
                            if tiempo_viejo not in ["-", "", "None"]:
                                logger.info(f"🛡️ Protección activada: Se ignoró el valor inválido para '{nombre_nuevo}' y se mantiene el horario existente.")
                                continue
                    
                    registros_depurados.append(nuevo)

                # Combinamos manteniendo los actualizados o nuevos válidos
                dict_combinado = dict_actuales.copy()
                for reg in registros_depurados:
                    nombre = str(reg.get("nombre", "")).strip().lower()
                    if nombre:
                        dict_combinado[nombre] = reg

                # 4. APLICAR LIMPIEZA GLOBAL DE DUPLICADOS POR NOMBRE
                MEMORIA_JEFES["horarios_manuales"] = limpiar_duplicados_por_nombre(list(dict_combinado.values()))

                guardar_memoria_a_json_completa()
                logger.info(f"💾 Memoria actualizada de forma segura. Total manuales únicos: {len(MEMORIA_JEFES['horarios_manuales'])}")
                 
                await disparar_salidas_manuales(bot)

        except Exception as e:
            logger.error(f"Error procesando entrada manual: {e}")

    await bot.process_commands(message)

if __name__ == "__main__":
    keep_alive()
    if config.DISCORD_TOKEN:
        bot.run(config.DISCORD_TOKEN)
    else:
        logger.critical("❌ No se encontró el DISCORD_TOKEN.")
