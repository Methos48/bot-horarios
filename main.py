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
import COMANDOS_BOT

# --- MÓDULOS DE SALIDA ---
import salida_horario
import salida_ma
import salida_ronda
import salida_raid
import salida_low
import salida_raid_salio  # <-- 1. Importado el servicio de Raids Salió

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

# --- BLOQUEO ASÍNCRONO PARA EL JSON ---
json_lock = asyncio.Lock()  # <-- 2. Bloqueo para lectura/escritura segura de archivos JSON

# --- CONTROL DE SALIDA MA ---
# Se reinicia junto con main.py. La primera entrada manual que contenga
# Valakas, Antharas o Fafureon publica MA. Después, MA solo se publica
# cuando cambia la FECHA de alguno de esos tres raids.
MA_RAIDS = {"valakas", "antharas", "fafureon"}
MA_INICIALIZADA = False
MA_FECHAS_CONOCIDAS = {}

# --- CONTROL DE PRIMERA PUBLICACIÓN DE LAS TABLAS DESDE LA WEB ---
# Al arrancar el bot, la primera data válida de entrada_pagina.py publica
# una vez salida_low y salida_ronda. Después, cada servicio solo se dispara
# cuando cambia la(s) lista(s) que realmente administra.
SALIDAS_WEB_INICIALES_ENVIADAS = False

# --- MEMORIA EXCLUSIVA PARA salida_horario ---
# Se mantiene solamente la información vigente de los 11 raids fijos y de
# los eventos opcionales recibidos por texto/imagen. Esta memoria vive en
# main.py y se reconstruye al recibir cada nueva entrada manual.
RAIDS_HORARIO_FIJOS = {
    "orfen", "queen ant", "core", "zaken", "baium", "frintezza",
    "freya", "zariche", "valakas", "antharas", "fafureon"
}
EVENTOS_HORARIO_OPCIONALES = {"asedio", "p v p", "x 9", "x9", "foto mes"}
MEMORIA_HORARIO = []

# --- LISTA OFICIAL DE JEFES ÉPICOS (Los de la imagen) ---
JEFES_EPICOS_IMAGEN = {
    "antharas", "fafureon", "freya", "frintezza", 
    "valakas", "baium", "zaken", "core", "orfen", "queen ant"
}

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
        
        if nombre_limpio in NIVELES_VACIOS_EXTRA:
            item["nivel"] = ""
            continue

        encontrado = False
        for clave, nivel in NIVELES_JEFE_MANUAL.items():
            if clave in nombre_limpio:
                item["nivel"] = nivel
                encontrado = True
                break
        
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

# ==============================================================================
# 🎮 ACTIVACIÓN DEL MÓDULO DE COMANDOS (COMANDOS_BOT)
# ==============================================================================
COMANDOS_BOT.registrar_comandos_bot(bot)

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
# 🚀 DISPARADORES INDEPENDIENTES: SALIDA RONDA Y SALIDA LOW
# ==============================================================================
async def disparar_salida_ronda_si_cambio(bot_instance):
    logger.info("🚀 [Web/Manual] Actualizando salida_ronda...")
    try:
        mapa_vivos_web = {}
        for item_epic in MEMORIA_JEFES.get("vivo_o_muerto", []):
            nombre_epic = str(item_epic.get("nombre", "")).strip().lower()
            tiempo_epic = str(item_epic.get("tiempo_str", "")).lower()
            estado_epic = str(item_epic.get("estado", "")).lower()
            
            es_vivo = "alive" in tiempo_epic or "vivo" in tiempo_epic or estado_epic in ["vivo", "alive"] or item_epic.get("es_vivo", False)
            if es_vivo:
                mapa_vivos_web[nombre_epic] = True

        r60_plus_original = MEMORIA_JEFES.get("raid_60_plus", [])
        r60_plus_actualizada = []

        for item_raid in r60_plus_original:
            item_copia = item_raid.copy()
            nombre_raid = str(item_copia.get("nombre", "")).strip().lower()
            
            es_epico_imagen = nombre_raid in JEFES_EPICOS_IMAGEN

            if es_epico_imagen:
                if nombre_raid in mapa_vivos_web:
                    item_copia["tiempo_str"] = "VIVO"
                    item_copia["estado"] = "VIVO"
                    item_copia["es_vivo"] = True
                    item_copia["fue_vivo"] = True  
                    item_copia["datetime"] = datetime.min.replace(tzinfo=ZONA_ARGENTINA)
                    r60_plus_actualizada.append(item_copia)
                else:
                    fue_vivo_antes = item_copia.get("fue_vivo", False)
                    if fue_vivo_antes:
                        logger.info(f"💀 El jefe épico '{nombre_raid}' fue abatido y la web lo retiró. Eliminando de la ronda.")
                        continue
                    else:
                        r60_plus_actualizada.append(item_copia)
            else:
                r60_plus_actualizada.append(item_copia)

        MEMORIA_JEFES["raid_60_plus"] = limpiar_duplicados_por_nombre(r60_plus_actualizada)
        guardar_memoria_a_json_completa()

        datos_ronda = ordenar_y_priorizar(MEMORIA_JEFES["raid_60_plus"])

        await salida_ronda.ejecutar(bot_instance, datos_ronda)
        logger.info("✅ salida_ronda ejecutada con éxito.")
    except Exception as e:
        logger.error(f"Error al disparar salida_ronda: {e}")

async def disparar_salida_low_si_cambio(bot_instance):
    logger.info("🚀 [Web] Actualizando salida_low...")
    try:
        datos_low = ordenar_y_priorizar(MEMORIA_JEFES.get("raid_60_menos", []))
        await salida_low.ejecutar(bot_instance, datos_low)
        logger.info("✅ salida_low ejecutada con éxito.")
    except Exception as e:
        logger.error(f"Error al disparar salida_low: {e}")

# ==============================================================================
# 🚀 DISPARADOR 2: ENTRADAS MANUALES (TEXTO / IMAGEN)
# ==============================================================================
def obtener_fecha_ma(item):
    """Obtiene únicamente la fecha del registro de MA para poder detectar cambios."""
    dt = item.get("datetime")
    if isinstance(dt, datetime):
        return dt.date()

    dt_iso = item.get("datetime_iso")
    if dt_iso:
        try:
            return datetime.fromisoformat(str(dt_iso)).date()
        except Exception:
            pass

    tiempo_str = str(item.get("tiempo_str", "")).strip()
    for formato in ("%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M"):
        try:
            return datetime.strptime(tiempo_str, formato).date()
        except Exception:
            pass

    return None

def _normalizar_nombre_horario(nombre):
    return " ".join(str(nombre or "").strip().lower().split())


def _fecha_hora_horario(item):
    """Obtiene la fecha/hora utilizable para ordenar y saber si ya pasó."""
    dt = item.get("datetime")
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZONA_ARGENTINA)
        return dt.astimezone(ZONA_ARGENTINA)

    dt_iso = item.get("datetime_iso")
    if dt_iso:
        try:
            dt = datetime.fromisoformat(str(dt_iso))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZONA_ARGENTINA)
            return dt.astimezone(ZONA_ARGENTINA)
        except Exception:
            pass

    for campo in ("tiempo_str", "tiempo", "hora"):
        valor = str(item.get(campo, "")).strip()
        if not valor or valor.upper() in {"VIVO", "ALIVE"}:
            continue
        for formato in (
            "%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M",
            "%d/%m/%y %H:%M", "%d-%m-%y %H:%M",
            "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y",
        ):
            try:
                dt = datetime.strptime(valor, formato).replace(tzinfo=ZONA_ARGENTINA)
                return dt
            except Exception:
                pass

    return None


def _es_vivo_horario(item):
    valores = [
        str(item.get("estado", "")).strip().upper(),
        str(item.get("tiempo_str", "")).strip().upper(),
        str(item.get("tiempo", "")).strip().upper(),
    ]
    return bool(item.get("es_vivo")) or any(v in {"VIVO", "ALIVE"} for v in valores)


def _preparar_registro_horario(item):
    """Normaliza lo necesario para que salida_horario reciba una data consistente."""
    copia = dict(item)
    nombre = str(copia.get("nombre", "")).strip()
    copia["nombre"] = nombre

    if _es_vivo_horario(copia):
        ahora = datetime.now(ZONA_ARGENTINA)
        dt = _fecha_hora_horario(copia)

        # Si viene una fecha sin hora, se usa esa fecha. Si no viene fecha,
        # VIVO corresponde al día actual.
        fecha_vivo = dt.date() if dt else ahora.date()
        dt_vivo = datetime.combine(fecha_vivo, datetime.min.time(), tzinfo=ZONA_ARGENTINA)
        copia["datetime"] = dt_vivo
        copia["datetime_iso"] = dt_vivo.isoformat()
        copia["estado"] = "VIVO"
        copia["es_vivo"] = True
        copia["tiempo_str"] = f"{fecha_vivo.strftime('%d/%m/%y')} VIVO"

        # Conserva cualquier campo de hora que ya entregue entrada_texto /
        # entrada_imagen y lo convierte a VIVO. No inventa nombres de campos.
        for clave in list(copia.keys()):
            if "hora" in str(clave).lower():
                copia[clave] = "VIVO"

    return copia


def _clave_evento_horario(item):
    """Los eventos se distinguen por nombre + fecha; permite dos Asedios futuros."""
    nombre = _normalizar_nombre_horario(item.get("nombre", ""))
    dt = _fecha_hora_horario(item)
    fecha = dt.strftime("%Y-%m-%d") if dt else "sin-fecha"
    return nombre, fecha


def _es_opcional_horario(nombre):
    return _normalizar_nombre_horario(nombre) in EVENTOS_HORARIO_OPCIONALES


def _es_futuro_horario(item, ahora=None):
    ahora = ahora or datetime.now(ZONA_ARGENTINA)
    dt = _fecha_hora_horario(item)
    if dt is None:
        return False
    # Un evento que ya pasó deja de formar parte de la memoria.
    return dt >= ahora


def _limpiar_memoria_horario():
    """Elimina de la memoria todo evento/raid con fecha y hora ya vencidas."""
    global MEMORIA_HORARIO
    ahora = datetime.now(ZONA_ARGENTINA)
    memoria_limpia = []

    for item in MEMORIA_HORARIO:
        nombre = _normalizar_nombre_horario(item.get("nombre", ""))
        dt = _fecha_hora_horario(item)

        if _es_opcional_horario(nombre):
            if dt is not None and dt >= ahora:
                memoria_limpia.append(item)
            continue

        # Los 11 raids fijos permanecen una sola vez mientras sean vigentes.
        # Si tienen una fecha/hora vencida, se eliminan y la próxima entrada
        # manual podrá colocar el nuevo respawn.
        if nombre in RAIDS_HORARIO_FIJOS:
            if _es_vivo_horario(item) and dt is not None and dt.date() == ahora.date():
                memoria_limpia.append(item)
            elif dt is not None and dt >= ahora:
                memoria_limpia.append(item)

    MEMORIA_HORARIO = memoria_limpia


def _actualizar_memoria_horario(registros_ingresados):
    """Mezcla la nueva entrada con la memoria vigente de salida_horario."""
    global MEMORIA_HORARIO

    _limpiar_memoria_horario()
    actuales = [_preparar_registro_horario(i) for i in MEMORIA_HORARIO]

    # Solo interesan los 11 raids fijos y los eventos opcionales definidos.
    nuevos = []
    for registro in registros_ingresados or []:
        item = _preparar_registro_horario(registro)
        nombre = _normalizar_nombre_horario(item.get("nombre", ""))
        if nombre in RAIDS_HORARIO_FIJOS or _es_opcional_horario(nombre):
            nuevos.append(item)

    # Los 11 raids fijos: uno solo por nombre; la nueva entrada reemplaza la anterior.
    por_raid = {
        _normalizar_nombre_horario(i.get("nombre", "")): i
        for i in actuales
        if _normalizar_nombre_horario(i.get("nombre", "")) in RAIDS_HORARIO_FIJOS
    }
    for item in nuevos:
        nombre = _normalizar_nombre_horario(item.get("nombre", ""))
        if nombre in RAIDS_HORARIO_FIJOS:
            por_raid[nombre] = item

    # Eventos: se distinguen por nombre + fecha. Así Asedio puede aparecer
    # dos veces si son dos fechas distintas (sábado/domingo, por ejemplo).
    eventos = {
        _clave_evento_horario(i): i
        for i in actuales
        if _es_opcional_horario(i.get("nombre", ""))
    }
    for item in nuevos:
        nombre = _normalizar_nombre_horario(item.get("nombre", ""))
        if _es_opcional_horario(nombre):
            if _es_futuro_horario(item):
                eventos[_clave_evento_horario(item)] = item

    MEMORIA_HORARIO = list(por_raid.values()) + list(eventos.values())
    _limpiar_memoria_horario()

    # Primero fecha y después hora. VIVO queda al inicio de su fecha.
    MEMORIA_HORARIO.sort(key=lambda i: (
        _fecha_hora_horario(i) or datetime.max.replace(tzinfo=ZONA_ARGENTINA),
        _normalizar_nombre_horario(i.get("nombre", ""))
    ))
    return list(MEMORIA_HORARIO)


async def disparar_salidas_manuales(bot_instance, registros_ingresados):
    global MA_INICIALIZADA, MA_FECHAS_CONOCIDAS

    logger.info("🚀 [Manual] Procesando salidas exclusivas para entradas manuales...")
    try:
        datos_ma = [
            j for j in registros_ingresados
            if str(j.get("nombre", "")).strip().lower() in MA_RAIDS
        ]

        if datos_ma:
            datos_ma = limpiar_duplicados_por_nombre(datos_ma)

            # Primera entrada después de cada reinicio: publica MA una vez.
            publicar_ma = not MA_INICIALIZADA

            # A partir de ahí, solo publica si cambió la FECHA de Valakas,
            # Antharas o Fafureon. Cambios de hora/estado no disparan MA.
            for item in datos_ma:
                nombre = str(item.get("nombre", "")).strip().lower()
                fecha_nueva = obtener_fecha_ma(item)
                fecha_anterior = MA_FECHAS_CONOCIDAS.get(nombre)

                if MA_INICIALIZADA and fecha_nueva != fecha_anterior:
                    publicar_ma = True

            if publicar_ma:
                await salida_ma.ejecutar(bot_instance, datos_ma)
                logger.info("✅ salida_ma ejecutada con éxito (primera entrada o cambio de fecha).")

            for item in datos_ma:
                nombre = str(item.get("nombre", "")).strip().lower()
                MA_FECHAS_CONOCIDAS[nombre] = obtener_fecha_ma(item)

            MA_INICIALIZADA = True

        # salida_horario recibe siempre la memoria completa y vigente, no solo
        # los registros de la entrada actual.
        datos_horario = _actualizar_memoria_horario(registros_ingresados)
        if datos_horario:
            await salida_horario.ejecutar(bot_instance, datos_horario)
            logger.info("✅ salida_horario ejecutada con memoria completa, vigente y ordenada.")

    except Exception as e:
        logger.error(f"Error al disparar salidas manuales: {e}")

@bot.event
async def on_ready():
    logger.info(f"¡Bot conectado como {bot.user}!")

    # Sincronización global automática de los comandos de barra
    try:
        synced = await bot.tree.sync()
        logger.info(f"✨ ¡Se sincronizaron {len(synced)} comandos de barra globales con éxito!")
    except Exception as e:
        logger.error(f"❌ Error al sincronizar los comandos de barra: {e}")

    # Monitoreo de la página: normales cada 30 s y especiales cada 5 s.
    if not auto_monitor_web.is_running():
        auto_monitor_web.start()
    if not auto_monitor_epic.is_running():
        auto_monitor_epic.start()

    bot.loop.create_task(
        salida_raid.iniciar_monitoreo_permanente_raids(
            bot,
            ruta_json=ARCHIVO_JSON,
            intervalo_segundos=30,
        )
    )
    logger.info("🚀 PUBLICAR_RAIDS/PUBLICAR_RAIDS_ANTES configurados a 30 segundos.")

    bot.loop.create_task(
        salida_raid_salio.servicio_publicar_raids_salio(
            bot,
            ruta_json=ARCHIVO_JSON,
            json_lock=json_lock,
        )
    )
    logger.info("🟢 PUBLICAR_RAIDS_SALIO configurado a 5 segundos.")


@tasks.loop(seconds=30)
async def auto_monitor_web():
    """Monitorea exclusivamente los raids normales 60+ y 60-."""
    global SALIDAS_WEB_INICIALES_ENVIADAS
    try:
        t1_crudo, t2_crudo = entrada_pagina.obtener_datos_web()
        t1 = aplicar_offset_web(t1_crudo, HORA_OFFSET_WEB)
        t2 = aplicar_offset_web(t2_crudo, HORA_OFFSET_WEB)

        if not (t1 or t2):
            return

        def clasificar_local(lista_items):
            r_plus, r_minus = [], []
            wh_plus = {
                "asedio", "p v p", "x9", "x 9", "foto mes",
                "core", "orfen", "queen ant", "zaken", "balrog",
                "electrical", "electrica", "valakas", "baium",
                "frintezza", "fafureon", "antharas", "freya", "zariche",
            }
            for item in lista_items:
                nombre = str(item.get("nombre", "")).strip().lower()
                try:
                    niv = int(str(item.get("nivel", 85)).strip() or 85)
                except Exception:
                    niv = 85
                if nombre in wh_plus or niv >= 60:
                    r_plus.append(item)
                else:
                    r_minus.append(item)
            return limpiar_duplicados_por_nombre(r_plus), limpiar_duplicados_por_nombre(r_minus)

        nuevos_r60_plus_web, nuevos_r60_menos = clasificar_local(t1 + t2)
        vieja_r60_plus = MEMORIA_JEFES.get("raid_60_plus", [])
        vieja_r60_menos = MEMORIA_JEFES.get("raid_60_menos", [])

        # 60+: la web actualiza los raids normales, pero conservamos los
        # registros manuales/anteriores que no hayan sido reemplazados por la web.
        dict_r60_plus_actual = {
            str(i.get("nombre", "")).strip().lower(): i
            for i in vieja_r60_plus
        }
        for item in nuevos_r60_plus_web:
            dict_r60_plus_actual[str(item.get("nombre", "")).strip().lower()] = item
        fusion_r60_plus = list(dict_r60_plus_actual.values())

        cambio_r60_plus = listas_han_cambiado(vieja_r60_plus, fusion_r60_plus)
        cambio_r60_menos = listas_han_cambiado(vieja_r60_menos, nuevos_r60_menos)

        async with json_lock:
            MEMORIA_JEFES["raid_60_plus"] = fusion_r60_plus
            MEMORIA_JEFES["raid_60_menos"] = nuevos_r60_menos
            guardar_memoria_a_json_completa()

        # Primera data válida de entrada_pagina.py después del arranque:
        # se imprimen las dos tablas una vez, aunque el JSON ya tuviera los mismos datos.
        if not SALIDAS_WEB_INICIALES_ENVIADAS:
            logger.info("🟢 Primera data web recibida: enviando salida_ronda y salida_low.")
            await disparar_salida_ronda_si_cambio(bot)
            await disparar_salida_low_si_cambio(bot)
            SALIDAS_WEB_INICIALES_ENVIADAS = True
            return

        # Después de la primera publicación, cada salida responde únicamente
        # a la lista que administra.
        if cambio_r60_plus:
            await disparar_salida_ronda_si_cambio(bot)

        if cambio_r60_menos:
            await disparar_salida_low_si_cambio(bot)

    except Exception as e:
        logger.error(f"Error en monitoreo web de raids normales: {e}")


@auto_monitor_web.before_loop
async def before_auto_monitor():
    await bot.wait_until_ready()


@tasks.loop(seconds=5)
async def auto_monitor_epic():
    """Monitorea exclusivamente los estados de los Epic Bosses cada 5 segundos."""
    try:
        t_epic_crudo = entrada_pagina.obtener_datos_especiales_web()
        t_epic = limpiar_duplicados_por_nombre(t_epic_crudo)

        if not t_epic:
            return

        vieja_vivo_muerto = MEMORIA_JEFES.get("vivo_o_muerto", [])
        if not listas_han_cambiado(vieja_vivo_muerto, t_epic):
            return

        async with json_lock:
            MEMORIA_JEFES["vivo_o_muerto"] = t_epic
            guardar_memoria_a_json_completa()

        await disparar_salida_ronda_si_cambio(bot)

    except Exception as e:
        logger.error(f"Error en monitoreo web de Epic Bosses: {e}")


@auto_monitor_epic.before_loop
async def before_auto_monitor_epic():
    await bot.wait_until_ready()

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if config.CARGAR_HORARIO_CHANNEL_ID and message.channel.id == config.CARGAR_HORARIO_CHANNEL_ID:
        try:
            nuevos_registros = []

            if message.attachments:
                logger.info("🖼 Procesando imagen con entrada_imagen...")
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
                        if nombre in JEFES_EPICOS_IMAGEN:
                            reg["fue_vivo"] = False
                        dict_combinado[nombre] = reg

                nueva_r60_plus = limpiar_duplicados_por_nombre(list(dict_combinado.values()))
                cambio_r60_plus = listas_han_cambiado(actuales_r60_plus, nueva_r60_plus)

                async with json_lock:
                    MEMORIA_JEFES["raid_60_plus"] = nueva_r60_plus
                    guardar_memoria_a_json_completa()
                
                logger.info(f"💾 Memoria actualizada por entrada manual. Total en raid_60_plus: {len(MEMORIA_JEFES['raid_60_plus'])}")
                
                await disparar_salidas_manuales(bot, nuevos_registros)

                # La entrada de texto/imagen alimenta 60+. Solo se vuelve a
                # imprimir salida_ronda si realmente cambió esa lista.
                if cambio_r60_plus:
                    await disparar_salida_ronda_si_cambio(bot)
                else:
                    logger.info("ℹ️ Entrada manual sin cambios en raid_60_plus: no se imprime salida_ronda.")

        except Exception as e:
            logger.error(f"Error procesando entrada manual: {e}")

    await bot.process_commands(message)

# ==============================================================================
# 🚀 INICIO DE LA APLICACIÓN
# ==============================================================================
if __name__ == "__main__":
    # 1. Iniciamos Flask para mantener el servicio activo en servicios cloud (Render, etc.)
    keep_alive()

    # 2. Obtenemos el token y arrancamos el bot de Discord de manera bloqueante
    TOKEN = getattr(config, "DISCORD_TOKEN", None)
    if not TOKEN:
        logger.error("❌ No se encontró el DISCORD_TOKEN en el archivo config.py")
    else:
        try:
            logger.info("🤖 Iniciando conexión con Discord...")
            bot.run(TOKEN)
        except Exception as e:
            logger.error(f"❌ Error crítico al ejecutar el bot: {e}")
