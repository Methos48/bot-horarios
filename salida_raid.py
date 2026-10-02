import os
import logging
import json
import io
import asyncio
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from PIL import Image
import config

from config import (
    NUMERO_0, NUMERO_1, NUMERO_2, NUMERO_3, NUMERO_4,
    NUMERO_5, NUMERO_6, NUMERO_7, NUMERO_8, NUMERO_9,
    NUMERO_DOS_PUNTOS
)

logger = logging.getLogger("SalidaRaid")

ZONA_ARGENTINA = ZoneInfo(getattr(config, "TZ", "America/Argentina/Buenos_Aires"))

# Memoria de caché independiente para PUBLICAR_RAIDS
CACHE_PUBLICAR_RAIDS = {}
ULTIMO_RESET_CACHE_DIA = None  

TEMA_ACTIVO = "morado"  # Puede cambiarse a "rojo", etc.
POS_X = 80
POS_Y = 590

# Diccionario de filtros específico para PUBLICAR_RAIDS
FILTRO_PUBLICAR_RAIDS = {
    "Valakas": "si", "Antharas": "si", "Fafureon": "si", "Balrog": "no",
    "Electrical": "no", "Baium": "si", "Zaken": "si", "Core": "si",
    "Orfen": "si", "Queen Ant": "si", "Frintezza": "si", "Freya": "si",
    "Zariche": "si", "Decarbia": "si", "Hekaton": "si", "Queen shyeed": "si",
    "Golkonda": "si", "Galaxia": "si", "Barakiel": "si",
    "otros_60_mas": "no", "otros_60_menos": "no"
}

MAPEO_NUMEROS = {
    '0': NUMERO_0, '1': NUMERO_1, '2': NUMERO_2, '3': NUMERO_3, '4': NUMERO_4,
    '5': NUMERO_5, '6': NUMERO_6, '7': NUMERO_7, '8': NUMERO_8, '9': NUMERO_9,
    ':': NUMERO_DOS_PUNTOS
}

def estampar_hora_con_imagenes(imagen_base, texto_hora, x_inicial, y_inicial, altura_deseada=250, espacio_entre_digitos=12):
    cursor_x = x_inicial
    for caracter in texto_hora:
        ruta_img_num = MAPEO_NUMEROS.get(caracter)
        if ruta_img_num and os.path.exists(ruta_img_num):
            try:
                img_digito = Image.open(ruta_img_num).convert("RGBA")
                w_original, h_original = img_digito.size
                if caracter == ':':
                    altura_actual = int(altura_deseada * 0.75)
                    nuevo_ancho = int(w_original * (altura_actual / h_original))
                    img_digito = img_digito.resize((nuevo_ancho, altura_actual), Image.Resampling.LANCZOS)
                    offset_y = y_inicial + int((altura_deseada - altura_actual) / 2)
                    imagen_base.paste(img_digito, (cursor_x, offset_y), img_digito)
                else:
                    altura_actual = altura_deseada
                    nuevo_ancho = int(w_original * (altura_actual / h_original))
                    img_digito = img_digito.resize((nuevo_ancho, altura_actual), Image.Resampling.LANCZOS)
                    imagen_base.paste(img_digito, (cursor_x, y_inicial), img_digito)
                cursor_x += nuevo_ancho + espacio_entre_digitos
            except Exception as e:
                logger.error(f"❌ Error al estampar dígito '{caracter}': {e}")

def obtener_catalogo_imagenes_raid():
    directorio_base = getattr(config, "DIR_RAID", "imagen/raid")
    catalogo = {}
    if not os.path.exists(directorio_base):
        return catalogo
    for root, dirs, files in os.walk(directorio_base):
        for archivo in files:
            if archivo.lower().endswith(('.png', '.webp', '.jpg', '.jpeg')):
                ruta_completa = os.path.join(root, archivo)
                clave_relativa = os.path.relpath(ruta_completa, directorio_base).replace("\\", "/")
                catalogo[clave_relativa.lower()] = ruta_completa
                catalogo[archivo.lower()] = ruta_completa
    return catalogo

def obtener_imagen_raid_dinamica(catalogo, nombre_archivo_buscado):
    nombre_buscado_lower = nombre_archivo_buscado.strip().lower()
    
    # Ruta basada en estructura exacta: imagen/raid/{TEMA_ACTIVO}/raid/{nombre}.png[cite: 1]
    rutas_candidatas = [
        f"{TEMA_ACTIVO}/raid/{nombre_buscado_lower}.png",
        f"{TEMA_ACTIVO}/{nombre_buscado_lower}.png",
        f"{nombre_buscado_lower}.png"
    ]

    for ruta in rutas_candidatas:
        for clave_cat in catalogo:
            if clave_cat.endswith(ruta.lower()) or clave_cat == ruta.lower():
                return catalogo[clave_cat]
                
    for clave, ruta_completa in catalogo.items():
        if nombre_buscado_lower in clave:
            return ruta_completa
    return None

def limpiar_memoria_cache_diaria():
    global ULTIMO_RESET_CACHE_DIA, CACHE_PUBLICAR_RAIDS
    ahora_arg = datetime.now(ZONA_ARGENTINA)
    hoy_str = ahora_arg.strftime("%Y-%m-%d")
    
    # Si pasa de las 04:00 AM y no se ha hecho hoy, limpiamos la caché
    if ahora_arg.hour >= 4 and ULTIMO_RESET_CACHE_DIA != hoy_str:
        CACHE_PUBLICAR_RAIDS.clear()
        ULTIMO_RESET_CACHE_DIA = hoy_str
        logger.info("🧹 [PUBLICAR_RAIDS] Memoria caché limpiada exitosamente a las 04:00 AM.")


# ==========================================
# SERVICIO PRINCIPAL: PUBLICAR_RAIDS
# ==========================================
async def servicio_publicar_raids(bot_instance, ruta_json):
    while not bot_instance.is_closed():
        try:
            # 1. Limpieza automática de caché a las 04:00 AM
            limpiar_memoria_cache_diaria()

            canal_id = getattr(config, "ENVIAR_MENSAJE_CHANNEL_ID", None)
            if canal_id and os.path.exists(ruta_json):
                with open(ruta_json, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Acceso a las 3 tablas para tener la data disponible
                raid_60_plus = data.get("raid_60_plus", [])
                raid_60_menos = data.get("raid_60_menos", [])
                vivo_o_muerto = data.get("vivo_o_muerto", [])

                catalogo = obtener_catalogo_imagenes_raid()
                channel = bot_instance.get_channel(canal_id)

                ahora_arg = datetime.now(ZONA_ARGENTINA)
                hora_actual_minutos = ahora_arg.hour * 60 + ahora_arg.minute
                hoy_fecha_str = ahora_arg.strftime("%Y-%m-%d")

                # Procesamos la lista principal (raid_60_plus + vivo_o_muerto según aplique, o filtramos)
                # Unificamos registros para evaluar todos los que estén habilitados en el filtro
                todos_los_registros = raid_60_plus + vivo_o_muerto

                if channel and todos_los_registros:
                    for item in todos_los_registros:
                        nombre_original = str(item.get("nombre", "")).strip()
                        if FILTRO_PUBLICAR_RAIDS.get(nombre_original, "no") != "si":
                            continue

                        tiempo_bruto = str(item.get("tiempo_str") or item.get("tiempo") or item.get("hora") or "").strip()
                        if not tiempo_bruto or tiempo_bruto in ["-", "None", "null", ""]:
                            continue

                        match_dt = re.search(r'(\d{4}-\d{2}-\d{2})?\s*(\d{1,2}:\d{2})', tiempo_bruto)
                        if not match_dt:
                            continue

                        fecha_raid_str = match_dt.group(1) if match_dt.group(1) else hoy_fecha_str
                        hora_raid_str = match_dt.group(2)

                        try:
                            dt_raid_original = datetime.strptime(f"{fecha_raid_str} {hora_raid_str}", "%Y-%m-%d %H:%M").replace(tzinfo=ZONA_ARGENTINA)
                        except ValueError:
                            continue

                        # Identificar si es excepción (Valakas, Antharas, Fafureon)
                        es_excepcion = nombre_original.lower() in ["valakas", "antharas", "fafureon"]

                        if es_excepcion:
                            # 1. Restar 30 minutos a la hora del raid para los cálculos e impresión
                            dt_raid = dt_raid_original - timedelta(minutes=30)
                            
                            # Publicaciones especiales:
                            # A) El día antes a las 10:00 (10:00 AM) usando plantilla terminada en 'm'
                            # B) El mismo día a las 10:00 y a las 18:00 usando plantilla terminada en 'h'
                            
                            dt_dia_antes_10 = (dt_raid_original.date() - timedelta(days=1))
                            dt_mismo_dia = dt_raid_original.date()
                            
                            horarios_objetivo = []
                            # (Fecha, HoraMinutosObjetivo, TipoPlantillaSufijo)
                            
                            # Día antes a las 10:00 -> Plantilla 'm'
                            horarios_objetivo.append((datetime.combine(dt_dia_antes_10, datetime.strptime("10:00", "%H:%M").time()).replace(tzinfo=ZONA_ARGENTINA), 'm'))
                            
                            # Mismo día a las 10:00 y 18:00 -> Plantilla 'h'
                            horarios_objetivo.append((datetime.combine(dt_mismo_dia, datetime.strptime("10:00", "%H:%M").time()).replace(tzinfo=ZONA_ARGENTINA), 'h'))
                            horarios_objetivo.append((datetime.combine(dt_mismo_dia, datetime.strptime("18:00", "%H:%M").time()).replace(tzinfo=ZONA_ARGENTINA), 'h'))

                            for dt_meta, sufijo in horarios_objetivo:
                                meta_minutos = dt_meta.hour * 60 + dt_meta.minute
                                # Margen de 3 minutos para que se puedan publicar
                                if ahora_arg.date() == dt_meta.date() and 0 <= (hora_actual_minutos - meta_minutos) <= 3:
                                    clave_cache = f"{nombre_original}_{sufijo}_{dt_meta.strftime('%Y%m%d_%H%M')}"
                                    if CACHE_PUBLICAR_RAIDS.get(clave_cache):
                                        continue

                                    nombre_archivo_buscado = f"{nombre_original.lower()}{sufijo}"
                                    ruta_img = obtener_imagen_raid_dinamica(catalogo, nombre_archivo_buscado)

                                    if ruta_img and os.path.exists(ruta_img):
                                        img = Image.open(ruta_img).convert("RGBA")
                                        hora_a_imprimir = dt_raid.strftime("%H:%M")
                                        estampar_hora_con_imagenes(img, hora_a_imprimir, POS_X, POS_Y, altura_deseada=95, espacio_entre_digitos=4)
                                        
                                        with io.BytesIO() as binary:
                                            img.convert("RGB").save(binary, "PNG")
                                            binary.seek(0)
                                            await channel.send(file=discord.File(binary, filename=f"raid_{nombre_archivo_buscado}_{hora_a_imprimir.replace(':', '')}.png"))
                                            CACHE_PUBLICAR_RAIDS[clave_cache] = True
                                            logger.info(f"✅ [PUBLICAR_RAIDS] Excepción '{nombre_original}' ({sufijo}) publicada correctamente.")
                                            await asyncio.sleep(1.5)

                        else:
                            # Resto de raids normales:
                            # - Salen hoy
                            # - Hora entre las 16:00 y las 23:59 (16 y 23)
                            # - Se publica el mismo día a las 14:00 con 3 minutos de margen (14:00 a 14:03)
                            
                            if dt_raid_original.date() == ahora_arg.date():
                                hora_original_raid = dt_raid_original.hour
                                if 16 <= hora_original_raid <= 23:
                                    # Hora de publicación objetivo: 14:00 del mismo día
                                    minutos_publicacion = 14 * 60 + 0  # 14:00
                                    
                                    if 0 <= (hora_actual_minutos - minutos_publicacion) <= 3:
                                        clave_cache = f"{nombre_original}_{dt_raid_original.strftime('%Y%m%d')}"
                                        if CACHE_PUBLICAR_RAIDS.get(clave_cache):
                                            continue

                                        nombre_archivo_buscado = f"{nombre_original.lower()}"
                                        ruta_img = obtener_imagen_raid_dinamica(catalogo, nombre_archivo_buscado)

                                        if ruta_img and os.path.exists(ruta_img):
                                            img = Image.open(ruta_img).convert("RGBA")
                                            hora_a_imprimir = dt_raid_original.strftime("%H:%M")
                                            estampar_hora_con_imagenes(img, hora_a_imprimir, POS_X, POS_Y, altura_deseada=95, espacio_entre_digitos=4)
                                            
                                            with io.BytesIO() as binary:
                                                img.convert("RGB").save(binary, "PNG")
                                                binary.seek(0)
                                                await channel.send(file=discord.File(binary, filename=f"raid_{nombre_archivo_buscado}_{hora_a_imprimir.replace(':', '')}.png"))
                                                CACHE_PUBLICAR_RAIDS[clave_cache] = True
                                                logger.info(f"✅ [PUBLICAR_RAIDS] Raid normal '{nombre_original}' publicado correctamente a las 14:00.")
                                                await asyncio.sleep(1.5)

        except Exception as e:
            logger.error(f"❌ Error en servicio_publicar_raids: {e}")
        
        await asyncio.sleep(30)
