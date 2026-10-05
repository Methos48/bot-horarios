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
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import discord
from PIL import Image
import config

logger = logging.getLogger("SalidaRaid")
ZONA_ARGENTINA = ZoneInfo(getattr(config, "TZ", "America/Argentina/Buenos_Aires"))

# Servidores secundarios: reciben los avisos SALIO en estos canales.

CONFIG_FILTRO_PUBLICAR_RAIDS_SALIO = {
    "valakas": "si", "antharas": "si", "fafureon": "si",
    "baium": "si", "zaken": "si", "core": "si", "orfen": "si",
    "queenant": "si", "frintezza": "si", "freya": "si", "zariche": "si",
    "decarbia": "si", "hekaton": "si", "queenshyeed": "si",
    "golkonda": "si", "galaxia": "si", "barakiel": "si",
    "balrog": "no", "electrical": "no",
    "otros_60_mas": "si", "otros_60_menos": "no",
}


# Estos 11 solamente pueden confirmarse como "salieron"
# mediante el estado VIVO/MUERTO de la página.
RAIDS_VIVO_O_MUERTO = {
    "orfen", "queenant", "core", "zaken", "baium",
    "frintezza", "freya", "zariche", "valakas",
    "antharas", "fafureon",
}

RAIDS_DOBLE_CANAL = set(RAIDS_VIVO_O_MUERTO)

NUMEROS = {str(i): getattr(config, f"NUMERO_{i}", None) for i in range(10)}
NUMEROS[":"] = getattr(config, "NUMERO_DOS_PUNTOS", None)

MEMORIA_DUPLICADOS = set()
ESTADO_ANTERIOR_VIVO_MUERTO = {}
MEMORIA_SALIDA_ESPECIALES = {}
ULTIMO_RESET_DIA = None


def normalizar(nombre):
    return str(nombre or "").strip().lower().replace(" ", "")


def filtro_ok(nombre, lista):
    if nombre in CONFIG_FILTRO_PUBLICAR_RAIDS_SALIO:
        return CONFIG_FILTRO_PUBLICAR_RAIDS_SALIO[nombre] == "si"

    if lista == "raid_60_plus":
        return CONFIG_FILTRO_PUBLICAR_RAIDS_SALIO.get("otros_60_mas", "no") == "si"

    if lista == "raid_60_menos":
        return CONFIG_FILTRO_PUBLICAR_RAIDS_SALIO.get("otros_60_menos", "no") == "si"

    return False


def cargar_raids(data):
    # Se revisan TODAS las listas.
    for lista in ("raid_60_plus", "raid_60_menos", "vivo_o_muerto"):
        valores = data.get(lista, [])
        if isinstance(valores, list):
            for item in valores:
                if isinstance(item, dict):
                    yield item, lista


def catalogo():
    base = os.path.join("imagen", "raid", "raid", "antes")
    salida = {}

    if not os.path.exists(base):
        return salida

    for root, _, files in os.walk(base):
        for f in files:
            if f.lower().endswith((".png", ".webp", ".jpg", ".jpeg")):
                salida[f.lower()] = os.path.join(root, f)

    return salida


def plantilla(nombre, sufijo):
    c = catalogo()
    base = f"{normalizar(nombre)}{sufijo}"

    for ext in (".png", ".webp", ".jpg", ".jpeg"):
        if base + ext in c:
            return c[base + ext]

    return None


def estampar(img, hora):
    """Estampa la hora usando una altura comun para todos los numeros.
    Los dos puntos tienen exactamente el 75%% de la altura de los numeros.
    """
    cargados = []
    ancho_total = 0
    espacio = 4

    # Usamos la mediana de las alturas originales para que un archivo
    # anormalmente grande (como el 1.jpg) no agrande todos los numeros.
    alturas = []
    for numero in "0123456789":
        ruta = NUMEROS.get(numero)
        if ruta and os.path.exists(ruta):
            with Image.open(ruta) as imagen_numero:
                alturas.append(imagen_numero.height)

    if not alturas:
        return

    alturas.sort()
    altura_referencia = alturas[len(alturas) // 2]
    altura_numero = max(1, round(altura_referencia * 0.15))
    altura_dos_puntos = max(1, round(altura_numero * 0.75))

    for c in hora:
        p = NUMEROS.get(c)

        if not p or not os.path.exists(p):
            cargados.append((None, c))
            ancho_total += 20
            continue

        d = Image.open(p).convert("RGBA")
        altura_objetivo = altura_dos_puntos if c == ":" else altura_numero
        ancho_objetivo = max(1, round(d.width * altura_objetivo / d.height))
        d = d.resize((ancho_objetivo, altura_objetivo), Image.Resampling.LANCZOS)
        cargados.append((d, c))
        ancho_total += d.width

    if len(cargados) > 1:
        ancho_total += espacio * (len(cargados) - 1)

    x = (img.width - ancho_total) // 2
    y = int(img.height * 0.83)

    for d, c in cargados:
        if d:
            y_digito = y + ((altura_numero - d.height) // 2 if c == ":" else 0)
            img.paste(d, (x, y_digito), d)
            x += d.width + espacio
        else:
            x += 20 + espacio


async def canal(bot, id_):
    if not id_:
        return None

    c = bot.get_channel(int(id_))

    if c is None:
        try:
            c = await bot.fetch_channel(int(id_))
        except Exception as e:
            logger.error("No se pudo obtener canal %s: %s", id_, e)

    return c


def obtener_datetime(item):
    """
    Convierte cualquier fecha/hora proveniente del JSON a
    America/Argentina/Buenos_Aires.

    Prioridad:
    1. datetime
    2. datetime_iso
    3. tiempo_str / tiempo / hora

    Una fecha sin zona se interpreta como hora Argentina.
    Una fecha con zona/offset se convierte a hora Argentina.
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

    tiempo = str(
        item.get("tiempo_str")
        or item.get("tiempo")
        or item.get("hora")
        or ""
    ).strip()

    if not tiempo or tiempo.upper() in {"VIVO", "ALIVE", "-", "NONE"}:
        return None

    for fmt in ("%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M"):
        try:
            return datetime.strptime(tiempo, fmt).replace(
                tzinfo=ZONA_ARGENTINA
            )
        except ValueError:
            pass

    if len(tiempo) == 5 and tiempo[2] == ":":
        try:
            h, m = map(int, tiempo.split(":"))
            ahora = datetime.now(ZONA_ARGENTINA)

            return ahora.replace(
                hour=h,
                minute=m,
                second=0,
                microsecond=0,
            )
        except Exception:
            pass

    return None


def obtener_estado(item):
    """
    Obtiene el estado VIVO/MUERTO del registro.
    """
    posibles = (
        item.get("estado"),
        item.get("status"),
        item.get("vivo_muerto"),
        item.get("vivo_o_muerto"),
    )

    for valor in posibles:
        if valor is not None:
            texto = str(valor).strip().lower()

            if texto in {"vivo", "alive"}:
                return "vivo"

            if texto in {"muerto", "dead"}:
                return "muerto"

    return None


def reset_memorias(ahora):
    global ULTIMO_RESET_DIA

    dia = ahora.strftime("%Y-%m-%d")

    if ahora.hour >= 4 and ULTIMO_RESET_DIA != dia:
        MEMORIA_DUPLICADOS.clear()
        MEMORIA_SALIDA_ESPECIALES.clear()
        ESTADO_ANTERIOR_VIVO_MUERTO.clear()

        ULTIMO_RESET_DIA = dia

        logger.info("Memorias SALIO limpiadas a las 04:00 Argentina.")


async def enviar_a_canal(canal_obj, ruta, nombre_archivo, img=None):
    if img is not None:
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "PNG")
        buf.seek(0)
        try:
            await canal_obj.send(file=discord.File(buf, filename=nombre_archivo))
        finally:
            buf.close()
    else:
        with open(ruta, "rb") as f:
            await canal_obj.send(file=discord.File(f, filename=nombre_archivo))


async def publicar(bot, nombre, sufijo, hora=None, clave=None):
    if clave and clave in MEMORIA_DUPLICADOS:
        return False

    nombre = normalizar(nombre)
    ruta = plantilla(nombre, sufijo)

    if not ruta:
        logger.warning("No existe plantilla SALIO: %s%s", nombre, sufijo)
        return False

    principal = await canal(bot, getattr(config, "ENVIAR_MENSAJE_CHANNEL_ID", None)) if PUBLICAR_SERVIDOR_1 == "si" else None

    clan = None
    if PUBLICAR_SERVIDOR_1 == "si" and nombre in RAIDS_DOBLE_CANAL:
        clan = await canal(bot, getattr(config, "MENSAJE_CLAN_CHANNEL_ID", None))

    secundarios = []
    if PUBLICAR_SERVIDOR_2 == "si":
        canal_secundario = await canal(bot, 1556550803928653844)
        if canal_secundario:
            secundarios.append(canal_secundario)
    if PUBLICAR_SERVIDOR_3 == "si":
        canal_secundario = await canal(bot, 1556552846168821832)
        if canal_secundario:
            secundarios.append(canal_secundario)

    if not principal and not clan and not secundarios:
        return False

    img = None
    try:
        if hora is not None:
            img = Image.open(ruta).convert("RGBA")
            estampar(img, hora.strftime("%H:%M"))

        if principal:
            await enviar_a_canal(principal, ruta, f"{nombre}{sufijo}.png", img)

        if clan and clan != principal:
            await enviar_a_canal(clan, ruta, f"{nombre}{sufijo}.png", img)

        for canal_secundario in secundarios:
            if canal_secundario != principal and canal_secundario != clan:
                await enviar_a_canal(canal_secundario, ruta, f"{nombre}{sufijo}.png", img)

    finally:
        if img is not None:
            img.close()

    if clave:
        MEMORIA_DUPLICADOS.add(clave)

    logger.info(
        "[SALIO] publicado %s%s%s",
        nombre,
        sufijo,
        " en ambos canales" if clan and clan != principal else " en ENVIAR_MENSAJE_CHANNEL_ID",
    )

    return True


async def procesar_especial_vivo_muerto(
    bot_instance,
    item,
    lista,
    ahora,
):
    """
    Los 11 raids especiales NO se consideran salidos simplemente
    porque llegue la fecha/hora programada.

    Su nacimiento real se confirma cuando el estado de la página
    cambia de MUERTO a VIVO.

    La fecha/hora del JSON solamente se utiliza como referencia
    para no aceptar una fecha futura.
    """
    if lista != "vivo_o_muerto":
        return

    nombre = normalizar(item.get("nombre"))

    if not nombre or nombre not in RAIDS_VIVO_O_MUERTO:
        return

    if not filtro_ok(nombre, lista):
        return

    estado = obtener_estado(item)

    if estado is None:
        return

    anterior = ESTADO_ANTERIOR_VIVO_MUERTO.get(nombre)

    # Primera lectura: solamente guardamos el estado.
    # No publicamos para evitar falsos "SALIO" al reiniciar el bot.
    if anterior is None:
        ESTADO_ANTERIOR_VIVO_MUERTO[nombre] = estado
        return

    ESTADO_ANTERIOR_VIVO_MUERTO[nombre] = estado

    # Solamente MUERTO -> VIVO confirma que realmente nació.
    if anterior != "muerto" or estado != "vivo":
        return

    programado = obtener_datetime(item)

    # Si existe fecha en el JSON, nunca aceptamos una fecha futura.
    if programado and programado.date() > ahora.date():
        logger.info(
            "[SALIO] %s está VIVO pero su fecha JSON es futura: %s",
            nombre,
            programado.strftime("%Y-%m-%d %H:%M"),
        )
        return

    fecha = (
        programado.strftime("%Y-%m-%d")
        if programado
        else ahora.strftime("%Y-%m-%d")
    )

    # Valakas y Antharas usan 4 al detectar el nacimiento.
    # Fafureon también usa 4.
    # Los restantes usan 2.
    sufijo = "4" if nombre in {
        "valakas",
        "antharas",
        "fafureon",
    } else "2"

    clave = f"{nombre}|{fecha}|salio"

    poner_hora = nombre in {"valakas", "antharas"} and sufijo == "4"

    if await publicar(
        bot_instance,
        nombre,
        sufijo,
        ahora if poner_hora else None,
        clave,
    ):
        MEMORIA_SALIDA_ESPECIALES[nombre] = ahora

        logger.info(
            "[SALIO] %s detectado por VIVO/MUERTO: MUERTO -> VIVO a %s",
            nombre,
            ahora.strftime("%d-%m-%Y %H:%M"),
        )


async def procesar_segundo_mensaje_especial(
    bot_instance,
    nombre,
    ahora,
):
    """
    Valakas y Antharas tienen una segunda plantilla (+30 minutos)
    si existe la plantilla correspondiente.
    """
    nombre = normalizar(nombre)

    if nombre not in {"valakas", "antharas"}:
        return

    inicio = MEMORIA_SALIDA_ESPECIALES.get(nombre)

    if not inicio:
        return

    if ahora - inicio < timedelta(minutes=30):
        return

    fecha = inicio.strftime("%Y-%m-%d")
    clave = f"{nombre}|{fecha}|salio_30"

    if clave in MEMORIA_DUPLICADOS:
        return

    await publicar(
        bot_instance,
        nombre,
        "5",
        None,
        clave,
    )


async def procesar_por_hora(
    bot_instance,
    item,
    lista,
    ahora,
):
    """
    Para los raids que NO pertenecen a los 11 especiales,
    la salida se determina por la fecha/hora del JSON.

    Ventana: desde la hora programada hasta 5 minutos después.
    """
    if not isinstance(item, dict):
        return

    nombre = normalizar(item.get("nombre"))

    if not nombre or nombre in RAIDS_VIVO_O_MUERTO:
        return

    if not filtro_ok(nombre, lista):
        return

    programado = obtener_datetime(item)

    if not programado:
        return

    # Nunca publicamos raids de otra fecha.
    if programado.date() != ahora.date():
        return

    diferencia = (ahora - programado).total_seconds()

    if diferencia < 0 or diferencia > 300:
        return

    fecha = programado.strftime("%Y-%m-%d")
    clave = f"{nombre}|{fecha}|salio"

    # Los raids normales usan plantilla 2.
    sufijo = "2"

    if await publicar(
        bot_instance,
        nombre,
        sufijo,
        None,
        clave,
    ):
        logger.info(
            "[SALIO] %s detectado por fecha/hora %s",
            nombre,
            programado.strftime("%d-%m-%Y %H:%M"),
        )


async def servicio_publicar_raids_salio(
    bot_instance,
    ruta_json,
    json_lock,
):
    await bot_instance.wait_until_ready()

    logger.info(
        "Servicio PUBLICAR_RAIDS_SALIO iniciado correctamente."
    )

    while not bot_instance.is_closed():
        try:
            ahora = datetime.now(ZONA_ARGENTINA)
            reset_memorias(ahora)

            if os.path.exists(ruta_json):
                async with json_lock:
                    with open(ruta_json, encoding="utf-8") as f:
                        data = json.load(f)

                for item, lista in cargar_raids(data):
                    try:
                        nombre = normalizar(item.get("nombre")) if isinstance(item, dict) else "<sin nombre>"

                        if nombre in RAIDS_VIVO_O_MUERTO:
                            await procesar_especial_vivo_muerto(
                                bot_instance,
                                item,
                                lista,
                                ahora,
                            )
                        else:
                            await procesar_por_hora(
                                bot_instance,
                                item,
                                lista,
                                ahora,
                            )
                    except Exception as e:
                        logger.exception(
                            "Error procesando PUBLICAR_RAIDS_SALIO para %s: %s",
                            nombre,
                            e,
                        )

                # La segunda publicación de Valakas/Antharas
                # se comprueba en cada ciclo de 30 segundos.
                for nombre in ("valakas", "antharas"):
                    try:
                        await procesar_segundo_mensaje_especial(
                            bot_instance,
                            nombre,
                            ahora,
                        )
                    except Exception as e:
                        logger.exception(
                            "Error procesando segunda salida de %s: %s",
                            nombre,
                            e,
                        )

        except Exception as e:
            logger.exception(
                "Error en PUBLICAR_RAIDS_SALIO: %s",
                e,
            )

        await asyncio.sleep(5)
