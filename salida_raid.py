# ============================================================
# ACTIVAR / DESACTIVAR SERVIDORES
# Pon "si" para publicar en ese servidor o "no" para desactivarlo.
# ============================================================
PUBLICAR_SERVIDOR_1 = "si"
PUBLICAR_SERVIDOR_2 = "si"
PUBLICAR_SERVIDOR_3 = "si"

import os
import io
import json
import asyncio
import logging
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import discord
from PIL import Image
import config

logger = logging.getLogger("SalidaRaid")
ZONA_ARGENTINA = ZoneInfo(getattr(config, "TZ", "America/Argentina/Buenos_Aires"))
json_lock = asyncio.Lock()

# Bandera global para evitar que el monitoreo se duplique ante múltiples eventos on_ready
_MONITOREO_RAIDS_INICIADO = False

# Servidores secundarios: PUBLICAR_RAIDS normal NO se envia aqui.
# Estos canales reciben solamente PUBLICAR_RAIDS_ANTES.

# ===================== CONFIGURACION MANUAL =====================
TEMA_ACTIVO = "morado"  # "morado" o "rojo"
POS_X = 80
POS_Y = 590

FILTRO_PUBLICAR_RAIDS = {
    "valakas":"si","antharas":"si","fafureon":"si",
    "asediosabado":"si", "asediodomingo":"si",
    "balrog":"no","electrical":"no",
    "baium":"no","zaken":"no","core":"no","orfen":"no","queenant":"no","frintezza":"no",
    "freya":"no","zariche":"no","decarbia":"no","hekaton":"no","queenshyeed":"no",
    "golkonda":"no","galaxia":"no","barakiel":"no","otros_60_mas":"no","otros_60_menos":"no"
}
FILTRO_PUBLICAR_RAIDS_ANTES = {
    "valakas":"si","antharas":"si","fafureon":"si",
    "asediosabado":"si", "asediodomingo":"si",
    "balrog":"si","electrical":"si",
    "baium":"si","zaken":"si","core":"si","orfen":"si","queenant":"si","frintezza":"si",
    "freya":"si","zariche":"si","decarbia":"si","hekaton":"si","queenshyeed":"si",
    "golkonda":"si","galaxia":"si","barakiel":"si","otros_60_mas":"si","otros_60_menos":"no"
}

MEMORIA_PUBLICAR_RAIDS = set()
MEMORIA_PUBLICAR_RAIDS_ANTES = set()
ULTIMO_RESET_DIA = None

NUMEROS = {str(i): getattr(config, f"NUMERO_{i}", None) for i in range(10)}
NUMEROS[":"] = getattr(config, "NUMERO_DOS_PUNTOS", None)

def normalizar(nombre):
    return re.sub(r"\s+", "", str(nombre or "").strip().lower())

def filtro_ok(filtro, nombre, lista):
    nombre = normalizar(nombre)
    if nombre in filtro:
        return filtro[nombre] == "si"
    if lista == "raid_60_plus":
        return filtro.get("otros_60_mas", "no") == "si"
    if lista == "raid_60_menos":
        return filtro.get("otros_60_menos", "no") == "si"
    return False

def parsear_fecha(valor):
    m = re.fullmatch(r"(\d{2})-(\d{2})-(\d{4})\s+(\d{1,2}):(\d{2})", str(valor or "").strip())
    if not m:
        return None
    d, mo, y, h, mi = m.groups()
    try:
        return datetime(int(y), int(mo), int(d), int(h), int(mi), tzinfo=ZONA_ARGENTINA)
    except ValueError:
        return None

def obtener_datetime(item):
    """
    Unifica la fecha/hora del JSON con la hora de Argentina.
    Prioridad:
    1) datetime (si ya es datetime)
    2) datetime_iso (puede traer offset/zona)
    3) tiempo_str / tiempo / hora
    """
    dt = item.get("datetime")
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=ZONA_ARGENTINA)
        return dt.astimezone(ZONA_ARGENTINA)

    iso = str(item.get("datetime_iso", "")).strip()
    if iso:
        try:
            dt = datetime.fromisoformat(iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZONA_ARGENTINA)
            return dt.astimezone(ZONA_ARGENTINA)
        except Exception:
            pass

    tiempo = str(item.get("tiempo_str") or item.get("tiempo") or item.get("hora") or "").strip()
    if not tiempo or tiempo.upper() in {"VIVO", "ALIVE", "-", "NONE"}:
        return None

    for fmt in ("%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M"):
        try:
            return datetime.strptime(tiempo, fmt).replace(tzinfo=ZONA_ARGENTINA)
        except ValueError:
            pass

    if len(tiempo) == 5 and tiempo[2] == ":":
        try:
            h, m = map(int, tiempo.split(":"))
            ahora = datetime.now(ZONA_ARGENTINA)
            return ahora.replace(hour=h, minute=m, second=0, microsecond=0)
        except Exception:
            pass

    return None

def tiempo_item(item):
    return item.get("tiempo_str") or item.get("tiempo") or item.get("hora") or ""

def cargar_raids(data):
    for lista in ("raid_60_plus", "raid_60_menos", "vivo_o_muerto"):
        valores = data.get(lista, [])
        if isinstance(valores, list):
            for item in valores:
                if isinstance(item, dict):
                    yield item, lista

def reset_memorias(ahora):
    global ULTIMO_RESET_DIA
    dia = ahora.strftime("%Y-%m-%d")
    if ahora.hour >= 4 and ULTIMO_RESET_DIA != dia:
        MEMORIA_PUBLICAR_RAIDS.clear()
        MEMORIA_PUBLICAR_RAIDS_ANTES.clear()
        ULTIMO_RESET_DIA = dia
        logger.info("Memorias de salida_raid limpiadas a las 04:00 Argentina.")

def identificar_nombre_real(item):
    """Detecta el nombre base y si es asedio, determina si es sábado o domingo según su hora/fecha."""
    nombre_norm = normalizar(item.get("nombre"))
    dt = obtener_datetime(item)
    
    if nombre_norm == "asedio" and dt:
        # dt.weekday(): 5 es Sábado, 6 es Domingo
        if dt.weekday() == 5:
            return "asediosabado"
        elif dt.weekday() == 6:
            return "asediodomingo"
            
    return nombre_norm

def ruta_tema():
    if TEMA_ACTIVO.lower() == "rojo":
        return getattr(config, "DIR_ROJO_RAID", "imagen/raid/rojo/raid")
    return getattr(config, "DIR_MORADO_RAID", "imagen/raid/morado/raid")

def buscar_tema(nombre, sufijo):
    base = ruta_tema()

    # Si es asedio, busca directamente sabado1.png o domingo1.png en imagen/raid/castillo/
    if nombre in {"asediosabado", "asediodomingo"}:
        archivo = "sabado1" if nombre == "asediosabado" else "domingo1"
        base_castillo = os.path.join("imagen", "raid", "castillo")
        for ext in (".png", ".webp", ".jpg", ".jpeg"):
            p = os.path.join(base_castillo, f"{archivo}{ext}")
            if os.path.exists(p):
                return p
        return None

    if nombre in {"valakas", "antharas", "fafureon"}:
        archivo = f"{nombre}{sufijo}"
    else:
        archivo = nombre

    for ext in (".png", ".webp", ".jpg", ".jpeg"):
        p = os.path.join(base, f"{archivo}{ext}")
        if os.path.exists(p):
            return p

    return None

def buscar_antes(nombre, sufijo):
    if nombre in {"asediosabado", "asediodomingo"}:
        archivo = "sabado1" if nombre == "asediosabado" else "domingo1"
        base_castillo = os.path.join("imagen", "raid", "castillo")
        for ext in (".png", ".webp", ".jpg", ".jpeg"):
            p = os.path.join(base_castillo, f"{archivo}{ext}")
            if os.path.exists(p):
                return p

    base = os.path.join("imagen","raid","raid","antes")
    for ext in (".png",".webp",".jpg",".jpeg"):
        p = os.path.join(base, f"{nombre}{sufijo}{ext}")
        if os.path.exists(p):
            return p
    return None

def estampar_hora(img, texto):
    x = POS_X
    for c in texto:
        p = NUMEROS.get(c)
        if not p or not os.path.exists(p):
            continue
        try:
            d = Image.open(p).convert("RGBA")
            alto = 95 if c != ":" else int(95 * .75)
            ancho = int(d.width * alto / d.height)
            d = d.resize((ancho, alto), Image.Resampling.LANCZOS)
            y = POS_Y if c != ":" else POS_Y + int((95-alto)/2)
            img.paste(d, (x,y), d)
            x += ancho + 4
        except Exception as e:
            logger.error("Error al estampar %s: %s", c, e)

async def obtener_canal(bot, canal_id):
    if not canal_id:
        return None
    canal = bot.get_channel(int(canal_id))
    if canal is None:
        try:
            canal = await bot.fetch_channel(int(canal_id))
        except Exception as e:
            logger.error("No se pudo obtener canal %s: %s", canal_id, e)
    return canal

RAIDS_DOBLE_CANAL_ANTES = {
    "baium", "zaken", "core", "orfen", "queenant", "frintezza",
    "freya", "zariche", "valakas", "antharas", "fafureon",
    "asediosabado", "asediodomingo",
}

async def enviar_archivo_canales(canales, ruta, nombre_archivo):
    for canal in canales:
        with open(ruta, "rb") as f:
            await canal.send(file=discord.File(f, filename=nombre_archivo))

async def enviar_imagen_canales(canales, img, nombre_archivo):
    for canal in canales:
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "PNG")
        buf.seek(0)
        try:
            await canal.send(file=discord.File(buf, filename=nombre_archivo))
        finally:
            buf.close()

async def procesar_un_raid_publicar(canales, item, lista, ahora):
    nombre = identificar_nombre_real(item)
    if not nombre or not filtro_ok(FILTRO_PUBLICAR_RAIDS, nombre, lista):
        return

    dt = obtener_datetime(item)
    if not dt:
        return

    if nombre in {"valakas", "antharas", "fafureon", "asediosabado"}:
        impresa = dt - timedelta(minutes=30)
        ventanas = [
            (dt.replace(hour=10, minute=0, second=0, microsecond=0) - timedelta(days=1), "m", "dia_anterior_10"),
            (dt.replace(hour=10, minute=0, second=0, microsecond=0), "h", "mismo_dia_10"),
            (dt.replace(hour=18, minute=0, second=0, microsecond=0), "h", "mismo_dia_18"),
        ]
    elif nombre == "asediodomingo":
        impresa = dt - timedelta(minutes=30)
        ventanas = [
            (dt.replace(hour=10, minute=0, second=0, microsecond=0) - timedelta(days=1), "m", "dia_anterior_10"),
            (dt.replace(hour=10, minute=0, second=0, microsecond=0), "h", "mismo_dia_10"),
        ]
    else:
        if dt.date() != ahora.date() or not (16 <= dt.hour <= 23):
            return
        impresa = dt
        ventanas = [
            (dt.replace(hour=14, minute=0, second=0, microsecond=0), "normal", "normal_1400")
        ]

    for inicio, sufijo, ventana in ventanas:
        if not (inicio <= ahora < inicio + timedelta(minutes=5)):
            continue

        clave = f"{nombre}|{dt.strftime('%Y-%m-%d')}|{ventana}"
        if clave in MEMORIA_PUBLICAR_RAIDS:
            continue

        ruta = buscar_tema(nombre, sufijo)
        if not ruta:
            logger.warning("No existe plantilla para %s en ventana %s", nombre, ventana)
            continue

        img = Image.open(ruta).convert("RGBA")
        try:
            estampar_hora(img, impresa.strftime("%H:%M"))
            await enviar_imagen_canales(canales, img, f"{nombre}.png")
        finally:
            img.close()

        MEMORIA_PUBLICAR_RAIDS.add(clave)
        logger.info("[PUBLICAR_RAIDS] %s publicado en %d canales (%s)", nombre, len(canales), ventana)
        break

async def servicio_publicar_raids(bot_instance, ruta_json):
    await bot_instance.wait_until_ready()
    logger.info("PUBLICAR_RAIDS iniciado. Tema: %s", TEMA_ACTIVO)
    while not bot_instance.is_closed():
        try:
            ahora = datetime.now(ZONA_ARGENTINA)
            reset_memorias(ahora)
            if os.path.exists(ruta_json):
                async with json_lock:
                    with open(ruta_json, encoding="utf-8") as f:
                        data = json.load(f)

                canal_clan = await obtener_canal(bot_instance, 1569251132893823048)
                canal_enviar = await obtener_canal(bot_instance, getattr(config, "ENVIAR_MENSAJE_CHANNEL_ID", None))
                canales = []
                for c in (canal_clan, canal_enviar):
                    if c and c not in canales:
                        canales.append(c)

                if canales:
                    for item, lista in cargar_raids(data):
                        try:
                            await procesar_un_raid_publicar(canales, item, lista, ahora)
                        except Exception as e:
                            nombre = normalizar(item.get("nombre")) if isinstance(item, dict) else "<sin nombre>"
                            logger.exception("Error procesando PUBLICAR_RAIDS para %s: %s", nombre, e)
        except Exception as e:
            logger.exception("Error en PUBLICAR_RAIDS: %s", e)
        await asyncio.sleep(30)

async def procesar_un_raid_publicar_antes(canales_enviar, canal_clan, item, lista, ahora, canales_secundarios=None):
    nombre = identificar_nombre_real(item)
    if not nombre or not filtro_ok(FILTRO_PUBLICAR_RAIDS_ANTES, nombre, lista):
        return

    dt = obtener_datetime(item)
    if not dt or dt.date() != ahora.date():
        return

    if nombre in {"valakas", "antharas", "fafureon", "asediosabado", "asediodomingo"}:
        objetivos = [(dt - timedelta(minutes=60), "1"), (dt - timedelta(minutes=30), "2"), (dt, "3")]
    elif nombre in {"baium", "zaken", "core", "orfen", "queenant", "frintezza", "freya", "zariche"}:
        objetivos = [(dt, "1")]
    elif nombre in {"electrical", "balrog"}:
        # Publican exactamente a su hora exacta (sin restar los 10 minutos previos)
        objetivos = [(dt, "1")]
    else:
        objetivos = [(dt - timedelta(minutes=10), "1")]

    for objetivo, sufijo in objetivos:
        if not (objetivo <= ahora < objetivo + timedelta(minutes=5)):
            continue

        clave = f"{nombre}|{dt.strftime('%Y-%m-%d')}|{sufijo}"
        if clave in MEMORIA_PUBLICAR_RAIDS_ANTES:
            continue

        ruta = buscar_antes(nombre, sufijo)
        if not ruta:
            logger.warning("No existe plantilla ANTES para %s con sufijo %s", nombre, sufijo)
            continue

        canales = [canales_enviar] if canales_enviar else []
        if nombre in RAIDS_DOBLE_CANAL_ANTES and canal_clan and canal_clan not in canales:
            canales.append(canal_clan)

        for canal_secundario in (canales_secundarios or []):
            if canal_secundario and canal_secundario not in canales:
                canales.append(canal_secundario)

        if not canales:
            return

        await enviar_archivo_canales(canales, ruta, f"{nombre}{sufijo}.png")
        MEMORIA_PUBLICAR_RAIDS_ANTES.add(clave)
        logger.info("[PUBLICAR_RAIDS_ANTES] %s publicado en %d canal(es)", nombre, len(canales))
        break

async def servicio_publicar_raids_antes(bot_instance, ruta_json):
    await bot_instance.wait_until_ready()
    logger.info("PUBLICAR_RAIDS_ANTES iniciado.")
    while not bot_instance.is_closed():
        try:
            ahora = datetime.now(ZONA_ARGENTINA)
            reset_memorias(ahora)
            if os.path.exists(ruta_json):
                canal_enviar = await obtener_canal(bot_instance, getattr(config, "ENVIAR_MENSAJE_CHANNEL_ID", None)) if PUBLICAR_SERVIDOR_1 == "si" else None
                canal_clan = await obtener_canal(bot_instance, 1569251132893823048) if PUBLICAR_SERVIDOR_1 == "si" else None
                canales_secundarios = []
                if PUBLICAR_SERVIDOR_2 == "si":
                    canal_secundario = await obtener_canal(bot_instance, 1556550803928653844)
                    if canal_secundario:
                        canales_secundarios.append(canal_secundario)
                if PUBLICAR_SERVIDOR_3 == "si":
                    canal_secundario = await obtener_canal(bot_instance, 1556552846168821832)
                    if canal_secundario:
                        canales_secundarios.append(canal_secundario)
                if canal_enviar or canal_clan or canales_secundarios:
                    async with json_lock:
                        with open(ruta_json, encoding="utf-8") as f:
                            data = json.load(f)
                    for item, lista in cargar_raids(data):
                        try:
                            await procesar_un_raid_publicar_antes(canal_enviar, canal_clan, item, lista, ahora, canales_secundarios)
                        except Exception as e:
                            nombre = normalizar(item.get("nombre")) if isinstance(item, dict) else "<sin nombre>"
                            logger.exception("Error procesando PUBLICAR_RAIDS_ANTES para %s: %s", nombre, e)
        except Exception as e:
            logger.exception("Error en PUBLICAR_RAIDS_ANTES: %s", e)
        await asyncio.sleep(30)

async def iniciar_monitoreo_permanente_raids(bot_instance, ruta_json="jefes_activos.json", intervalo_segundos=30):
    global _MONITOREO_RAIDS_INICIADO
    await bot_instance.wait_until_ready()
    
    if _MONITOREO_RAIDS_INICIADO:
        logger.warning("El monitoreo de raids ya estaba activo. Ignorando llamada duplicada.")
        return
        
    _MONITOREO_RAIDS_INICIADO = True
    logger.info("Iniciando PUBLICAR_RAIDS y PUBLICAR_RAIDS_ANTES por única vez.")
    asyncio.create_task(servicio_publicar_raids(bot_instance, ruta_json))
    asyncio.create_task(servicio_publicar_raids_antes(bot_instance, ruta_json))