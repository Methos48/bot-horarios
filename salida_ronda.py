# ============================================================
# ACTIVAR / DESACTIVAR SERVIDORES
# Pon "si" para publicar en ese servidor o "no" para desactivarlo.
# ============================================================
PUBLICAR_SERVIDOR_1 = "si"
PUBLICAR_SERVIDOR_2 = "si"
PUBLICAR_SERVIDOR_3 = "si"

import logging
import asyncio
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont
import discord
import config

logger = logging.getLogger("SalidaRonda")
ZONA_ARGENTINA = ZoneInfo(getattr(config, "TZ", "America/Argentina/Buenos_Aires"))
CANAL_RONDA_CORTA = 1568910613659394098
PLANTILLA_RONDA_CORTA = os.path.join("imagen", "bot", "ronda.png")

SERVIDORES_RONDA = []
if PUBLICAR_SERVIDOR_1 == "si":
    SERVIDORES_RONDA.append(getattr(config, "RONDA_CHANNEL_ID", None))
if PUBLICAR_SERVIDOR_2 == "si":
    SERVIDORES_RONDA.append(1556550647979966504)
if PUBLICAR_SERVIDOR_3 == "si":
    SERVIDORES_RONDA.append(1533270483997298981)


def _hex_a_rgb(hex_str):
    hex_str = hex_str.lstrip('#')
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))

def _es_jefe_especial(nombre):
    if not nombre:
        return False
    return nombre.lower().strip() in ["valakas", "antharas", "fafurion", "fafureon"]

def _filtrar_y_clasificar(jefe):
    nombre = jefe.get("nombre", "").strip()
    n_lower = nombre.lower()
    if "orfen's handmaiden" in n_lower or "orfens handmaiden" in n_lower:
        return False
    excepciones_permitidas = [
        "zaken", "core", "orfen", "queen ant", "asedio", "p v p", "pvp",
        "x9", "x 9", "foto mes", "electrical", "balrog"
    ]
    es_excepcion = any(exc in n_lower for exc in excepciones_permitidas)
    nivel_raw = jefe.get("nivel", 0)
    nivel = 0
    try:
        if isinstance(nivel_raw, (int, float)):
            nivel = int(nivel_raw)
        elif isinstance(nivel_raw, str):
            solo_nums = "".join(filter(str.isdigit, nivel_raw))
            nivel = int(solo_nums) if solo_nums else 0
    except Exception:
        nivel = 0
    return nivel >= 60 or es_excepcion

def _obtener_color_hora(nombre, es_vivo):
    n_lower = nombre.lower().strip()
    if es_vivo:
        return _hex_a_rgb("#40A309")
    if n_lower in ["valakas", "antharas", "fafurion", "fafureon"]:
        return _hex_a_rgb("#FF0000")
    azules_exactos = ["core", "orfen", "baium", "zaken", "freya", "zariche", "frintezza", "queen ant", "asedio", "p v p", "pvp", "x9", "x 9", "foto mes", "electrical", "balrog"]
    if any(azul in n_lower for azul in azules_exactos):
        return _hex_a_rgb("#4D93D9")
    return _hex_a_rgb("#40A309")

def _obtener_color_fila_entera(nombre, es_vivo):
    if not nombre:
        return False, None
    n_lower = nombre.lower().strip()
    if n_lower in ["valakas", "antharas", "fafurion", "fafureon"]:
        return True, _hex_a_rgb("#FF0000")
    azules_exactos = ["core", "orfen", "baium", "zaken", "freya", "zariche", "frintezza", "queen ant", "asedio", "p v p", "pvp", "x9", "x 9", "foto mes", "electrical", "balrog"]
    if any(azul in n_lower for azul in azules_exactos):
        return True, _hex_a_rgb("#4D93D9")
    if n_lower in ["decarbia", "hekaton", "queen shyeed"]:
        return True, _hex_a_rgb("#40A309")
    if es_vivo:
        return True, _hex_a_rgb("#FFB366")
    return False, None

async def _obtener_canal(bot_instance, canal_id):
    if not canal_id:
        return None
    channel = bot_instance.get_channel(int(canal_id))
    if not channel:
        try:
            channel = await bot_instance.fetch_channel(int(canal_id))
        except Exception as e:
            logger.warning("No se pudo obtener el canal %s: %s", canal_id, e)
    return channel

def _generar_imagen(datos_ordenados, ruta_plantilla, nombre_archivo, filas_por_columna,
                    fuente_aptos_path, fuente_biome_path):
    canvas = Image.open(ruta_plantilla).convert("RGBA")
    draw = ImageDraw.Draw(canvas)
    try: fuente_texto = ImageFont.truetype(fuente_aptos_path, 15) if fuente_aptos_path else ImageFont.load_default()
    except Exception: fuente_texto = ImageFont.load_default()
    try: fuente_texto_grande = ImageFont.truetype(fuente_aptos_path, 17) if fuente_aptos_path else ImageFont.load_default()
    except Exception: fuente_texto_grande = ImageFont.load_default()
    try: fuente_hora = ImageFont.truetype(fuente_biome_path, 15) if fuente_biome_path else ImageFont.load_default()
    except Exception: fuente_hora = ImageFont.load_default()
    try: fuente_hora_grande = ImageFont.truetype(fuente_biome_path, 17) if fuente_biome_path else ImageFont.load_default()
    except Exception: fuente_hora_grande = ImageFont.load_default()
    try: fuente_en_curso = ImageFont.truetype(fuente_biome_path, 9) if fuente_biome_path else ImageFont.load_default()
    except Exception: fuente_en_curso = ImageFont.load_default()
    color_negro = _hex_a_rgb("#000000")
    x_nombre_izq, x_lvl_izq, x_hora_izq = 16, 220, 265
    x_nombre_der, x_lvl_der, x_hora_der = 340, 540, 590
    y_inicial, espaciado_renglon = 110, 24
    for index, jefe in enumerate(datos_ordenados):
        nombre = jefe.get("nombre", "Desconocido")
        nivel = str(jefe.get("nivel", ""))
        tiempo_mostrar = jefe.get("tiempo_str_final", "-")
        es_vivo = jefe.get("es_vivo", False)
        if index < filas_por_columna: columna, y_cursor = "izq", y_inicial + index * espaciado_renglon
        elif index < 2 * filas_por_columna: columna, y_cursor = "der", y_inicial + (index - filas_por_columna) * espaciado_renglon
        else: break
        x_n, x_l, x_h = (x_nombre_izq, x_lvl_izq, x_hora_izq) if columna == "izq" else (x_nombre_der, x_lvl_der, x_hora_der)
        y_centro = y_cursor + espaciado_renglon // 2
        debe_pintar_fondo, color_fondo_especial = _obtener_color_fila_entera(nombre, es_vivo)
        if debe_pintar_fondo:
            draw.rectangle([x_n - 4, y_centro - 10, x_h + 50, y_centro + 10], fill=color_fondo_especial)
            if color_fondo_especial == _hex_a_rgb("#FFB366"):
                color_texto_fila = _hex_a_rgb("#000000"); color_hora = _hex_a_rgb("#000000")
            else:
                color_texto_fila = _hex_a_rgb("#FFFFFF"); color_hora = _hex_a_rgb("#FFFFFF")
            font_t, font_h = fuente_texto_grande, fuente_hora_grande
            if tiempo_mostrar == "EN CURSO":
                font_h = fuente_en_curso
            for dx in (0,1):
                draw.text((x_n+dx, y_centro), nombre, fill=color_texto_fila, font=font_t, anchor="lm")
                draw.text((x_l+dx, y_centro), nivel, fill=color_texto_fila, font=font_t, anchor="lm")
                draw.text((x_h+dx, y_centro), tiempo_mostrar, fill=color_hora, font=font_h, anchor="lm")
        else:
            draw.text((x_n, y_centro), nombre, fill=color_negro, font=fuente_texto, anchor="lm")
            draw.text((x_l, y_centro), nivel, fill=color_negro, font=fuente_texto, anchor="lm")
            draw.text((x_h, y_centro), tiempo_mostrar, fill=_obtener_color_hora(nombre, es_vivo), font=fuente_hora, anchor="lm")
    canvas.save(nombre_archivo)

async def ejecutar(bot_instance, datos_horario):
    logger.info("⚙️ Ejecutando salida_ronda: Renderizando datos recibidos...")
    canal_ids = [int(x) for x in SERVIDORES_RONDA if x]
    ruta_plantilla = getattr(config, "PLANTILLA_RONDA", None)
    fuente_aptos_path = getattr(config, "FUENTE_APTOS", None)
    fuente_biome_path = getattr(config, "FUENTE_BIOME", None)
    try:
        async def limpiar_canal(canal_id, channel):
            try:
                async for mensaje in channel.history(limit=20):
                    if mensaje.author == bot_instance.user:
                        await mensaje.delete()
                        logger.info("🗑️ Mensaje anterior de salida_ronda eliminado en %s.", canal_id)
                        break
            except Exception as e:
                logger.warning("⚠️ No se pudo limpiar salida_ronda en %s: %s", canal_id, e)
        datos_filtrados = [j for j in datos_horario if _filtrar_y_clasificar(j)]
        datos_procesados = []
        en_curso_set = {"asedio", "p v p", "pvp", "x9", "x 9", "foto mes"}
        ahora = datetime.now(ZONA_ARGENTINA)
        duracion_en_curso = timedelta(hours=2, minutes=30)
        for jefe in datos_filtrados:
            registro = jefe.copy()
            nombre = registro.get("nombre", "")
            tiempo_str = str(registro.get("tiempo_str", "-")).strip()
            estado = str(registro.get("estado", "")).upper()
            es_vivo = estado in ["VIVO", "ALIVE"] or tiempo_str.upper() in ["VIVO", "ALIVE"] or registro.get("es_vivo", False)
            registro["es_vivo"] = es_vivo
            if es_vivo:
                registro["tiempo_str_final"] = "VIVO"
                registro["datetime"] = datetime.min.replace(tzinfo=ZONA_ARGENTINA)
            else:
                dt_obj = registro.get("datetime")
                if not dt_obj or not isinstance(dt_obj, datetime):
                    try:
                        dt_obj = datetime.strptime(tiempo_str, "%d/%m/%Y %H:%M").replace(tzinfo=ZONA_ARGENTINA) if tiempo_str and tiempo_str not in ["-", "None"] else datetime.max.replace(tzinfo=ZONA_ARGENTINA)
                    except ValueError:
                        dt_obj = datetime.max.replace(tzinfo=ZONA_ARGENTINA)
                if dt_obj.tzinfo is None:
                    dt_obj = dt_obj.replace(tzinfo=ZONA_ARGENTINA)
                if _es_jefe_especial(nombre) and dt_obj != datetime.max.replace(tzinfo=ZONA_ARGENTINA):
                    dt_obj -= timedelta(minutes=30)
                registro["datetime"] = dt_obj
                registro["tiempo_str_final"] = dt_obj.strftime("%H:%M") if dt_obj != datetime.max.replace(tzinfo=ZONA_ARGENTINA) else tiempo_str[-5:] if len(tiempo_str) >= 5 else tiempo_str
                if nombre.lower().strip() in en_curso_set and dt_obj != datetime.max.replace(tzinfo=ZONA_ARGENTINA) and dt_obj <= ahora:
                    if ahora - dt_obj >= duracion_en_curso:
                        continue
                    registro["tiempo_str_final"] = "EN CURSO"
            datos_procesados.append(registro)

        rojos_set = {"valakas", "antharas", "fafurion", "fafureon"}
        azules_set = {"core", "orfen", "baium", "zaken", "freya", "zariche", "frintezza", "queen ant", "asedio", "p v p", "pvp", "x9", "x 9", "foto mes", "electrical", "balrog"}
        verdes_set = {"decarbia", "hekaton", "queen shyeed"}
        def clave_orden(item):
            nombre = item.get("nombre", "").lower().strip()
            es_vivo = item.get("es_vivo", False)
            dt = item.get("datetime", datetime.max.replace(tzinfo=ZONA_ARGENTINA))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZONA_ARGENTINA)
            if es_vivo or (nombre in en_curso_set and item.get("tiempo_str_final") == "EN CURSO"):
                if nombre in rojos_set: prioridad_vivo = 1
                elif any(b in nombre for b in azules_set): prioridad_vivo = 2
                elif nombre in verdes_set: prioridad_vivo = 3
                else: prioridad_vivo = 4
                return (0, prioridad_vivo, nombre)
            return (1, 0, dt)
        datos_ordenados = sorted(datos_procesados, key=clave_orden)

        async def enviar_canal(canal_id, channel, nombre_archivo):
            try:
                await limpiar_canal(canal_id, channel)
                await channel.send(file=discord.File(nombre_archivo, filename="horario_ronda.png"))
                logger.info("✅ salida_ronda enviada al canal %s.", canal_id)
            except Exception as e:
                logger.error("❌ No se pudo enviar salida_ronda al canal %s: %s", canal_id, e)

        async def publicar_variante(ids, plantilla, archivo, filas):
            if not ids:
                logger.warning("No hay canales configurados para %s.", archivo)
                return
            if not plantilla:
                logger.error("Falta la plantilla para %s.", archivo)
                return
            try:
                resultados = await asyncio.gather(*(_obtener_canal(bot_instance, cid) for cid in ids))
                channels = [(cid, ch) for cid, ch in zip(ids, resultados) if ch]
                if not channels:
                    logger.warning("No se pudo obtener ningún canal para %s.", archivo)
                    return
                _generar_imagen(datos_ordenados, plantilla, archivo, filas, fuente_aptos_path, fuente_biome_path)
                await asyncio.gather(*(enviar_canal(cid, ch, archivo) for cid, ch in channels))
            except Exception:
                logger.exception("Error al generar o publicar %s.", archivo)

        await asyncio.gather(
            publicar_variante(canal_ids, ruta_plantilla, "ronda_horario_final.png", 22),
            publicar_variante([CANAL_RONDA_CORTA], PLANTILLA_RONDA_CORTA, "ronda_horario_corto.png", 14),
        )
    except Exception as e:
        logger.error(f"❌ Error crítico al ejecutar salida_ronda: {e}")
