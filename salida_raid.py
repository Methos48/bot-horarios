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

# ===================== CONFIGURACION MANUAL =====================
TEMA_ACTIVO = "morado"  # "morado" o "rojo"
CANAL_PUBLICAR_RAIDS_PRUEBA = 1549577944999927999
POS_X = 80
POS_Y = 590

FILTRO_PUBLICAR_RAIDS = {
    "valakas":"si","antharas":"si","fafureon":"si","balrog":"no","electrical":"no",
    "baium":"si","zaken":"si","core":"si","orfen":"si","queenant":"si","frintezza":"si",
    "freya":"si","zariche":"si","decarbia":"si","hekaton":"si","queenshyeed":"si",
    "golkonda":"si","galaxia":"si","barakiel":"si","otros_60_mas":"si","otros_60_menos":"no"
}
FILTRO_PUBLICAR_RAIDS_ANTES = {
    "valakas":"si","antharas":"si","fafureon":"si","balrog":"si","electrical":"si",
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
    # IMPORTANTE: se monitorean TODAS las listas.
    # El filtro se aplica solamente al momento de publicar.
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

def ruta_tema():
    if TEMA_ACTIVO.lower() == "rojo":
        return getattr(config, "DIR_ROJO_RAID", "imagen/raid/rojo/raid")
    return getattr(config, "DIR_MORADO_RAID", "imagen/raid/morado/raid")

def buscar_tema(nombre, sufijo):
    base = ruta_tema()
    for ext in (".png",".webp",".jpg",".jpeg"):
        p = os.path.join(base, f"{nombre}{sufijo}{ext}")
        if os.path.exists(p):
            return p
    return None

def buscar_antes(nombre, sufijo):
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
                canal = await obtener_canal(bot_instance, CANAL_PUBLICAR_RAIDS_PRUEBA)
                if canal:
                    for item, lista in cargar_raids(data):
                        nombre = normalizar(item.get("nombre"))
                        if not nombre or not filtro_ok(FILTRO_PUBLICAR_RAIDS,nombre,lista):
                            continue

                        dt = obtener_datetime(item)
                        if not dt:
                            continue

                        if nombre in {"valakas","antharas","fafureon"}:
                            impresa = dt - timedelta(minutes=30)
                            ventanas = [
                                (dt.replace(hour=10,minute=0,second=0,microsecond=0)-timedelta(days=1),"m","dia_anterior_10"),
                                (dt.replace(hour=10,minute=0,second=0,microsecond=0),"h","mismo_dia_10"),
                                (dt.replace(hour=18,minute=0,second=0,microsecond=0),"h","mismo_dia_18"),
                            ]
                        else:
                            if dt.date() != ahora.date() or not (16 <= dt.hour <= 23):
                                continue
                            ventanas = [(dt.replace(hour=14,minute=0,second=0,microsecond=0),dt.strftime("%H%M"),"normal_1400")]
                            impresa = dt

                        for inicio,sufijo,ventana in ventanas:
                            if not (inicio <= ahora < inicio + timedelta(minutes=5)):
                                continue
                            clave = f"{nombre}|{dt.strftime('%Y-%m-%d')}|{ventana}"
                            if clave in MEMORIA_PUBLICAR_RAIDS:
                                break
                            ruta = buscar_tema(nombre,sufijo)
                            if not ruta:
                                logger.warning("No existe plantilla: %s%s en tema %s",nombre,sufijo,TEMA_ACTIVO)
                                break
                            img = Image.open(ruta).convert("RGBA")
                            estampar_hora(img, impresa.strftime("%H:%M"))
                            buf = io.BytesIO()
                            img.convert("RGB").save(buf,"PNG")
                            buf.seek(0)
                            await canal.send(file=discord.File(buf,filename=f"{nombre}{sufijo}.png"))
                            MEMORIA_PUBLICAR_RAIDS.add(clave)
                            logger.info("[PUBLICAR_RAIDS] %s%s publicado (%s)",nombre,sufijo,ventana)
                            break
        except Exception as e:
            logger.exception("Error en PUBLICAR_RAIDS: %s",e)
        await asyncio.sleep(30)

async def servicio_publicar_raids_antes(bot_instance, ruta_json):
    await bot_instance.wait_until_ready()
    logger.info("PUBLICAR_RAIDS_ANTES iniciado.")
    while not bot_instance.is_closed():
        try:
            ahora = datetime.now(ZONA_ARGENTINA)
            reset_memorias(ahora)
            canal_id = getattr(config,"ENVIAR_MENSAJE_CHANNEL_ID",None)
            if canal_id and os.path.exists(ruta_json):
                canal = await obtener_canal(bot_instance,canal_id)
                if canal:
                    async with json_lock:
                        with open(ruta_json,encoding="utf-8") as f:
                            data = json.load(f)
                    for item,lista in cargar_raids(data):
                        nombre = normalizar(item.get("nombre"))
                        if not nombre or not filtro_ok(FILTRO_PUBLICAR_RAIDS_ANTES,nombre,lista):
                            continue

                        dt = obtener_datetime(item)
                        if not dt or dt.date() != ahora.date():
                            continue

                        if nombre in {"valakas","antharas","fafureon"}:
                            objetivos=[(dt-timedelta(minutes=60),"1"),(dt-timedelta(minutes=30),"2"),(dt,"3")]
                        elif nombre in {"baium","zaken","core","orfen","queenant","frintezza","freya","zariche"}:
                            objetivos=[(dt,"1")]
                        else:
                            objetivos=[(dt-timedelta(minutes=10),"1")]

                        for objetivo,sufijo in objetivos:
                            if objetivo <= ahora < objetivo+timedelta(minutes=5):
                                clave=f"{nombre}|{dt.strftime('%Y-%m-%d')}|{sufijo}"
                                if clave in MEMORIA_PUBLICAR_RAIDS_ANTES:
                                    break
                                ruta=buscar_antes(nombre,sufijo)
                                if not ruta:
                                    logger.warning("No existe plantilla ANTES: %s%s",nombre,sufijo)
                                    break
                                with open(ruta,"rb") as f:
                                    await canal.send(file=discord.File(f,filename=f"{nombre}{sufijo}.png"))
                                MEMORIA_PUBLICAR_RAIDS_ANTES.add(clave)
                                logger.info("[PUBLICAR_RAIDS_ANTES] %s%s publicado",nombre,sufijo)
                                break
        except Exception as e:
            logger.exception("Error en PUBLICAR_RAIDS_ANTES: %s",e)
        await asyncio.sleep(30)

async def iniciar_monitoreo_permanente_raids(bot_instance,ruta_json="jefes_activos.json",intervalo_segundos=30):
    await bot_instance.wait_until_ready()
    logger.info("Iniciando PUBLICAR_RAIDS y PUBLICAR_RAIDS_ANTES.")
    asyncio.create_task(servicio_publicar_raids(bot_instance,ruta_json))
    asyncio.create_task(servicio_publicar_raids_antes(bot_instance,ruta_json))
