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

# --- DICCIONARIO DE NIVELES EXACTOS PARA ENTRADAS MANUALES ---
NIVELES_JEFE_MANUAL = {
    "valakas": 85,
    "balrog": 85,
    "core": 50,
    "orfen": 50,
    "antharas": 85,
    "electrical": 85,
    "electrica": 85,
    "baium": 75,
    "zaken": 60,
    "frintezza": 85,
    "fafureon": 85,
    "queen ant": 40,
    "freya": 85,
    "zariche": 85
}

# Elementos que deben quedar sin nivel (en blanco)
NIVELES_VACIOS_EXTRA = {
    "asedio", "p v p", "x9", "x 9", "foto mes"
}

def asignar_nivel_manual(lista_jefes):
    """Asigna el nivel correspondiente o lo deja en blanco según las reglas establecidas."""
    for item in lista_jefes:
        nombre_limpio = item.get("nombre", "").strip().lower()
        
        # Si es un evento especial, limpiar el nivel para que salga en blanco
        if nombre_limpio in NIVELES_VACIOS_EXTRA:
            item["nivel"] = ""
            continue

        # Buscar en el diccionario de niveles definidos
        encontrado = False
        for clave, nivel in NIVELES_JEFE_MANUAL.items():
            if clave in nombre_limpio:
                item["nivel"] = nivel
                encontrado = True
                break
        
        # Si no está en ninguna lista, por defecto asignar 85
        if not encontrado:
            if "nivel" not in item or item["nivel"] is None:
                item["nivel"] = 85
    return lista_jefes

def limpiar_duplicados_por_nombre(lista_jefes):
    """
    GARANTÍA ABSOLUTA: Agrupa por nombre en minúsculas y asegura que 
    exista estrictamente un (1) solo registro por cada jefe.
    """
    if not lista_jefes:
        return []
     
    dict_unicos = {}
    for item in lista_jefes:
        nombre = str(item.get("nombre", "")).strip().lower()
        if not nombre:
            continue
         
        tiempo = str(item.get("tiempo_str", "")).strip()
         
        if nombre not in dict_unicos:
            dict_unicos[nombre] = item
        else:
            tiempo_existente = str(dict_unicos[nombre].get("tiempo_str", "")).strip()
            if tiempo_existente in ["-", "", "None"] and tiempo not in ["-", "", "None"]:
                dict_unicos[nombre] = item
            elif tiempo not in ["-", "", "None"]:
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
                vivo_muerto = limpiar_duplicados_por_nombre([item_desde_serializable(i) for i in data.get("vivo_o_muerto", [])])
                r60_plus = limpiar_duplicados_por_nombre([item_desde_serializable(i) for i in data.get("raid_60_plus", [])])
                r60_menos = limpiar_duplicados_por_nombre([item_desde_serializable(i) for i in data.get("raid_60_menos", [])])
                
                if not vivo_muerto and not r60_plus and not r60_menos:
                    t1 = [item_desde_serializable(i) for i in data.get("tabla_60_plus", [])]
                    t2 = [item_desde_serializable(i) for i in data.get("tabla_raids", [])]
                    t_epic = [item_desde_serializable(i) for i in data.get("tabla_epic", [])]
                    manuales = [item_desde_serializable(i) for i in data.get("horarios_manuales", [])]
                    
                    r60_plus = limpiar_duplicados_por_nombre(t1 + manuales)
                    r60_menos = limpiar_duplicados_por_nombre(t2)
                    vivo_muerto = limpiar_duplicados_por_nombre(t_epic)

                logger.info("📂 Memoria cargada en las 3 tablas principales desde el JSON.")
                return {
                    "vivo_o_muerto": vivo_muerto,
                    "raid_60_plus": r60_plus,
                    "raid_60_menos": r60_menos
                }
        except Exception as e:
            logger.error(f"Error al cargar JSON en memoria: {e}")
            
    return {
        "vivo_o_muerto": [],
        "raid_60_plus": [],
        "raid_60_menos": []
    }

def guardar_memoria_a_json_completa():
    try:
        data = {
            "vivo_o_muerto": [item_a_serializable(i) for i in MEMORIA_JEFES.get("vivo_o_muerto", [])],
            "raid_60_plus": [item_a_serializable(i) for i in MEMORIA_JEFES.get("raid_60_plus", [])],
            "raid_60_menos": [item_a_serializable(i) for i in MEMORIA_JEFES.get("raid_60_menos", [])]
        }
        with open(ARCHIVO_JSON, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        logger.info(f"💾 Archivo '{ARCHIVO_JSON}' guardado con las 3 tablas limpias.")
    except Exception as e:
        logger.error(f"Error al guardar memoria en JSON: {e}")

def clasificar_y_distribuir_items_web(lista_items):
    """Clasifica los ítems provenientes de la página web en raid_60_plus y raid_60_menos."""
    r60_plus = []
    r60_menos = []

    wh_r60_plus_extra = {
        "asedio", "p v p", "x9", "x 9", "foto mes", 
        "core", "orfen", "queen ant", "zaken", "balrog", "electrical", "electrica",
        "valakas", "baium", "frintezza", "fafureon", "antharas", "freya", "zariche"
    }

    for item in lista_items:
        nombre = str(item.get("nombre", "")).strip().lower()
        try:
            nivel_str = str(item.get("nivel", 85)).strip()
            nivel = int(nivel_str) if nivel_str else 85
        except Exception:
            nivel = 85

        if nombre in wh_r60_plus_extra or nivel >= 60:
            r60_plus.append(item)
        else:
            r60_menos.append(item)

    return limpiar_duplicados_por_nombre(r60_plus), limpiar_duplicados_por_nombre(r60_menos)

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

    lista_limpia = limpiar_duplicados_por_nombre(lista_jefes)
    return sorted(lista_limpia, key=clave_orden)

# ==============================================================================
# 🚀 DISPARADOR 1: CAMBIOS WEB AUTOMÁTICOS (Corregido y separado)
# ==============================================================================
async def disparar_salidas_por_cambios(bot_instance):
    """
    Controlado por el ciclo web. Envía de forma independiente:
    - salida_ronda: exclusivamente la combinación de epics y la tabla 60+
    - salida_low: exclusivamente la tabla de raids menores a 60
    """
    logger.info("🚀 [Web] Detectados cambios automáticos. Actualizando salidas web...")
    try:
        vivo_muerto_ord = ordenar_y_priorizar(MEMORIA_JEFES.get("vivo_o_muerto", []))
        r60_plus_ord = ordenar_y_priorizar(MEMORIA_JEFES.get("raid_60_plus", []))
        r60_menos_ord = ordenar_y_priorizar(MEMORIA_JEFES.get("raid_60_menos", []))

        # 1. Lista exclusiva para ronda (Epics + Raids de nivel 60+)
        datos_ronda = vivo_muerto_ord + r60_plus_ord

        # 2. Lista exclusiva para low (Raids menores a 60)
        datos_low = r60_menos_ord

        # Ejecutar las salidas de forma completamente independiente sin cruzar listas
        await salida_ronda.ejecutar(bot_instance, ordenar_y_priorizar(datos_ronda))
        await salida_low.ejecutar(bot_instance, ordenar_y_priorizar(datos_low))
        
        logger.info("✅ Salidas automáticas web ejecutadas con éxito (listas separadas correctamente).")
    except Exception as e:
        logger.error(f"Error al disparar salidas web: {e}")

# ==============================================================================
# 🚀 DISPARADOR 2: ENTRADAS MANUALES (TEXTO / IMAGEN)
# ==============================================================================
async def disparar_salidas_manuales(bot_instance, registros_ingresados):
    """
    Controlado exclusivamente por entrada_texto y entrada_imagen. Envía:
    - salida_ma: solo VALAKAS, ANTHARAS y FAFUREON de los registros ingresados.
    - salida_horario: toda la información recibida EXCEPTO balrog y electrical.
    """
    logger.info("🚀 [Manual] Procesando salidas exclusivas para entradas manuales...")
    try:
        wh_ma = {"valakas", "antharas", "fafureon"}
        datos_ma = [
            j for j in registros_ingresados 
            if str(j.get("nombre", "")).strip().lower() in wh_ma
        ]

        if datos_ma:
            await salida_ma.ejecutar(bot_instance, limpiar_duplicados_por_nombre(datos_ma))
            logger.info("✅ salida_ma ejecutada con éxito.")

        if registros_ingresados:
            exclusiones = {"balrog", "electrical", "electrica"}
            registros_horario = [
                j for j in registros_ingresados
                if str(j.get("nombre", "")).strip().lower() not in exclusiones
            ]

            if registros_horario:
                await salida_horario.ejecutar(bot_instance, limpiar_duplicados_por_nombre(registros_horario))
                logger.info("✅ salida_horario ejecutada con éxito.")

    except Exception as e:
        logger.error(f"Error al disparar salidas manuales: {e}")

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
            nuevos_r60_plus_web, nuevos_r60_menos = clasificar_y_distribuir_items_web(t1 + t2)
            nuevos_vivo_muerto = limpiar_duplicados_por_nombre(t_epic)

            vieja_r60_plus = MEMORIA_JEFES.get("raid_60_plus", [])
            vieja_r60_menos = MEMORIA_JEFES.get("raid_60_menos", [])
            vieja_vivo_muerto = MEMORIA_JEFES.get("vivo_o_muerto", [])
              
            dict_r60_plus_actual = {str(i.get("nombre","")).lower(): i for i in vieja_r60_plus}
            for item in nuevos_r60_plus_web:
                dict_r60_plus_actual[str(item.get("nombre","")).lower()] = item
            fusion_r60_plus = list(dict_r60_plus_actual.values())

            if (listas_han_cambiado(vieja_r60_plus, fusion_r60_plus) or 
                listas_han_cambiado(vieja_r60_menos, nuevos_r60_menos) or 
                listas_han_cambiado(vieja_vivo_muerto, nuevos_vivo_muerto)):
                
                MEMORIA_JEFES["raid_60_plus"] = fusion_r60_plus
                MEMORIA_JEFES["raid_60_menos"] = nuevos_r60_menos
                MEMORIA_JEFES["vivo_o_muerto"] = nuevos_vivo_muerto
                
                guardar_memoria_a_json_completa()
                await disparar_salidas_por_cambios(bot)
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
                nuevos_registros = asignar_nivel_manual(nuevos_registros)

                actuales_r60_plus = MEMORIA_JEFES.get("raid_60_plus", [])
                dict_actuales_r60 = {str(item.get("nombre", "")).strip().lower(): item for item in actuales_r60_plus}

                registros_depurados = []
                for nuevo in nuevos_registros:
                    nombre_nuevo = str(nuevo.get("nombre", "")).strip().lower()
                    tiempo_nuevo = str(nuevo.get("tiempo_str", "")).strip()

                    if tiempo_nuevo in ["-", "", "None"]:
                        if nombre_nuevo in dict_actuales_r60:
                            tiempo_viejo = str(dict_actuales_r60[nombre_nuevo].get("tiempo_str", "")).strip()
                            if tiempo_viejo not in ["-", "", "None"]:
                                logger.info(f"🛡️ Protección activada: Se ignoró el valor inválido para '{nombre_nuevo}' y se mantiene el horario existente.")
                                continue
                    
                    registros_depurados.append(nuevo)

                dict_combinado = dict_actuales_r60.copy()
                for reg in registros_depurados:
                    nombre = str(reg.get("nombre", "")).strip().lower()
                    if nombre:
                        dict_combinado[nombre] = reg

                MEMORIA_JEFES["raid_60_plus"] = limpiar_duplicados_por_nombre(list(dict_combinado.values()))

                guardar_memoria_a_json_completa()
                logger.info(f"💾 Memoria actualizada por entrada manual. Total en raid_60_plus: {len(MEMORIA_JEFES['raid_60_plus'])}")
               
                await disparar_salidas_manuales(bot, nuevos_registros)
                await disparar_salidas_por_cambios(bot)

        except Exception as e:
            logger.error(f"Error procesando entrada manual: {e}")

    await bot.process_commands(message)

if __name__ == "__main__":
    keep_alive()
    if config.DISCORD_TOKEN:
        bot.run(config.DISCORD_TOKEN)
    else:
        logger.critical("❌ No se encontró el DISCORD_TOKEN.")
