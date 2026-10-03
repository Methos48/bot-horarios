import os
import logging
import json
import io
import asyncio
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import discord
from PIL import Image
import config
from config import (
    NUMERO_0, NUMERO_1, NUMERO_2, NUMERO_3, NUMERO_4,
    NUMERO_5, NUMERO_6, NUMERO_7, NUMERO_8, NUMERO_9,
    NUMERO_DOS_PUNTOS
)

logger = logging.getLogger("SalidaRaid")

ZONA_ARGENTINA = ZoneInfo(getattr(config, "TZ", "America/Argentina/Buenos_Aires"))

# Lock global para sincronizar el acceso concurrente al archivo JSON
json_lock = asyncio.Lock()

# Cachés independientes para evitar cruces
CACHE_PUBLICAR_RAIDS = {}
CACHE_ANTES = {}
ULTIMO_RESET_CACHE_DIA = None  

TEMA_ACTIVO = "morado"  # Puede cambiarse a "rojo", etc.
POS_X = 80
POS_Y = 590

# ==========================================
# DICCIONARIOS DE FILTROS 100% INDEPENDIENTES
# ==========================================
FILTRO_PUBLICAR_RAIDS = {
    "Valakas": "si", "Antharas": "si", "Fafureon": "si", "Balrog": "no",
    "Electrical": "no", "Baium": "si", "Zaken": "si", "Core": "si",
    "Orfen": "si", "Queen Ant": "si", "Frintezza": "si", "Freya": "si",
    "Zariche": "si", "Decarbia": "si", "Hekaton": "si", "Queen shyeed": "si",
    "Golkonda": "si", "Galaxia": "si", "Barakiel": "si",
    "otros_60_mas": "no", "otros_60_menos": "no"
}

FILTRO_PUBLICAR_RAIDS_ANTES = {
    "Valakas": "si", "Antharas": "si", "Fafureon": "si", "Balrog": "si",
    "Electrical": "si", "Baium": "si", "Zaken": "si", "Core": "si",
    "Orfen": "si", "Queen Ant": "si", "Frintezza": "si", "Freya": "si",
    "Zariche": "si", "Decarbia": "si", "Hekaton": "si", "Queen shyeed": "si",
    "Golkonda": "si", "Galaxia": "si", "Barakiel": "si",
    "otros_60_mas": "si", "otros_60_menos": "no"
}

# ==========================================
# FUNCIONES AUXILIARES VISUALES
# ==========================================
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

def obtener_imagen_raid(catalogo, nombre_base_raid, tipo_servicio):
    nombre_limpio = nombre_base_raid.strip().lower()
    rutas_candidatas = []
    
    if tipo_servicio == "PUBLICAR_RAIDS_ANTES":
        rutas_candidatas = [f"raid/antes/{nombre_limpio}.png", f"antes/{nombre_limpio}.png", f"{TEMA_ACTIVO}/raid/antes/{nombre_limpio}.png"]

    rutas_candidatas.extend([
        f"{TEMA_ACTIVO}/raid/{nombre_limpio}.png", f"{TEMA_ACTIVO}/{nombre_limpio}.png",
        f"{nombre_limpio}.png"
    ])

    for ruta in rutas_candidatas:
        for clave_cat in catalogo:
            if clave_cat.endswith(ruta.lower()) or clave_cat == ruta.lower():
                return catalogo[clave_cat]
                
    for clave, ruta_completa in catalogo.items():
        if nombre_limpio in clave:
            return ruta_completa
    return None

def limpiar_memoria_cache_diaria():
    global ULTIMO_RESET_CACHE_DIA, CACHE_PUBLICAR_RAIDS, CACHE_ANTES
    ahora_arg = datetime.now(ZONA_ARGENTINA)
    hoy_str = ahora_arg.strftime("%Y-%m-%d")
    
    if ahora_arg.hour >= 4 and ULTIMO_RESET_CACHE_DIA != hoy_str:
        CACHE_PUBLICAR_RAIDS.clear()
        CACHE_ANTES.clear()
        ULTIMO_RESET_CACHE_DIA = hoy_str
        logger.info("🧹 Memoria caché de los servicios limpiada exitosamente a las 04:00 AM.")

# ==========================================
# SERVICIO 1: PUBLICAR_RAIDS (Usa ID fijo)
# ==========================================
async def servicio_publicar_raids(bot_instance, ruta_json):
    while not bot_instance.is_closed():
        try:
            limpiar_memoria_cache_diaria()
            canal_id = 1549577944999927999
            
            if canal_id and os.path.exists(ruta_json):
                async with json_lock:
                    with open(ruta_json, "r", encoding="utf-8") as f:
                        data = json.load(f)

                raid_60_plus = data.get("raid_60_plus", [])
                raid_60_menos = data.get("raid_60_menos", [])
                vivo_o_muerto = data.get("vivo_o_muerto", [])

                todos_los_jefes = list(raid_60_plus) + list(raid_60_menos) + list(vivo_o_muerto)

                catalogo = obtener_catalogo_imagenes_raid()
                channel = bot_instance.get_channel(canal_id)

                ahora_arg = datetime.now(ZONA_ARGENTINA)
                hoy_str = ahora_arg.strftime("%Y-%m-%d")

                if channel and todos_los_jefes:
                    for item in todos_los_jefes:
                        nombre = str(item.get("nombre", "")).strip()
                        if FILTRO_PUBLICAR_RAIDS.get(nombre, "no") != "si":
                            continue

                        tiempo_bruto = str(item.get("tiempo_str") or item.get("tiempo") or item.get("hora") or "").strip()
                        if not tiempo_bruto or tiempo_bruto in ["-", "None", "null", ""]:
                            continue

                        # Parseo formato DD-MM-YYYY HH:MM del JSON (Día-Mes-Año)
                        match_dt = re.search(r'(\d{2})-(\d{2})-(\d{4})\s+(\d{1,2}:\d{2})', tiempo_bruto)
                        if not match_dt:
                            match_hora = re.search(r'\d{1,2}:\d{2}', tiempo_bruto)
                            if not match_hora:
                                continue
                            hora_raid_str = match_hora.group(0)
                            fecha_raid_str = hoy_str
                        else:
                            dia, mes, anio, hora_raid_str = match_dt.groups()
                            # Reordenamos a YYYY-MM-DD para que datetime lo procese y compare bien
                            fecha_raid_str = f"{anio}-{mes}-{dia}"

                        try:
                            dt_raid = datetime.strptime(f"{fecha_raid_str} {hora_raid_str}", "%Y-%m-%d %H:%M").replace(tzinfo=ZONA_ARGENTINA)
                        except ValueError:
                            continue

                        sufijo_imagen = None
                        tipo_ventana = None
                        texto_a_estampar = hora_raid_str

                        if nombre in ["Valakas", "Antharas", "Fafureon"]:
                            dt_raid_ajustado = dt_raid - timedelta(minutes=30)
                            texto_a_estampar = dt_raid_ajustado.strftime("%H:%M")
                            
                            dt_dia_anterior_10 = (dt_raid_ajustado - timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
                            dt_mismo_dia_10 = dt_raid_ajustado.replace(hour=10, minute=0, second=0, microsecond=0)
                            dt_mismo_dia_18 = dt_raid_ajustado.replace(hour=18, minute=0, second=0, microsecond=0)

                            if dt_dia_anterior_10 <= ahora_arg < dt_dia_anterior_10 + timedelta(minutes=5):
                                tipo_ventana = "dia_anterior_10m"
                                sufijo_imagen = "m"
                            elif dt_mismo_dia_10 <= ahora_arg < dt_mismo_dia_10 + timedelta(minutes=5):
                                tipo_ventana = "mismo_dia_10h"
                                sufijo_imagen = "h"
                            elif dt_mismo_dia_18 <= ahora_arg < dt_mismo_dia_18 + timedelta(minutes=5):
                                tipo_ventana = "mismo_dia_18h"
                                sufijo_imagen = "h"
                        else:
                            if 16 <= dt_raid.hour <= 23:
                                dt_publicacion = dt_raid.replace(hour=14, minute=0, second=0, microsecond=0)
                                if dt_publicacion <= ahora_arg < dt_publicacion + timedelta(minutes=5):
                                    tipo_ventana = "normal_1400"
                                    sufijo_imagen = hora_raid_str.replace(':', '')

                        if not tipo_ventana or not sufijo_imagen:
                            continue

                        clave_cache = f"{nombre}_{fecha_raid_str}_{tipo_ventana}"
                        if CACHE_PUBLICAR_RAIDS.get(clave_cache):
                            continue

                        nombre_archivo_busqueda = f"{nombre.lower()}{sufijo_imagen}.png"
                        ruta_personalizada_tema = f"imagen/raid/{TEMA_ACTIVO}/raid/{nombre_archivo_busqueda}"
                        
                        ruta_img = None
                        if os.path.exists(ruta_personalizada_tema):
                            ruta_img = ruta_personalizada_tema
                        else:
                            ruta_img = obtener_imagen_raid(catalogo, f"{nombre}{sufijo_imagen}", "PUBLICAR_RAIDS")

                        if ruta_img and os.path.exists(ruta_img):
                            img = Image.open(ruta_img).convert("RGBA")
                            estampar_hora_con_imagenes(img, texto_a_estampar, POS_X, POS_Y, altura_deseada=95, espacio_entre_digitos=4)
                            
                            with io.BytesIO() as binary:
                                img.convert("RGB").save(binary, "PNG")
                                binary.seek(0)
                                await channel.send(file=discord.File(binary, filename=f"raid_{nombre.lower()}_{sufijo_imagen}.png"))
                                CACHE_PUBLICAR_RAIDS[clave_cache] = True
                                logger.info(f"✅ [PUBLICAR_RAIDS] Raid '{nombre}' enviado con éxito al canal ({canal_id}) (Ventana: {tipo_ventana}).")
                                await asyncio.sleep(1.5)
        except Exception as e:
            logger.error(f"❌ Error en servicio_publicar_raids: {e}")
        
        await asyncio.sleep(30)

# ==========================================
# SERVICIO 2: PUBLICAR_RAIDS_ANTES (Solo ENVIAR_MENSAJE_CHANNEL_ID)
# ==========================================
async def servicio_publicar_raids_antes(bot_instance, ruta_json):
    while not bot_instance.is_closed():
        try:
            limpiar_memoria_cache_diaria()
            canal_principal_id = getattr(config, "ENVIAR_MENSAJE_CHANNEL_ID", None)
            
            if canal_principal_id and os.path.exists(ruta_json):
                async with json_lock:
                    with open(ruta_json, "r", encoding="utf-8") as f:
                        data = json.load(f)

                raid_60_plus = data.get("raid_60_plus", [])
                raid_60_menos = data.get("raid_60_menos", [])
                vivo_o_muerto = data.get("vivo_o_muerto", [])

                todos_los_jefes = list(raid_60_plus) + list(raid_60_menos) + list(vivo_o_muerto)
                
                channel_principal = bot_instance.get_channel(canal_principal_id)

                ahora_arg = datetime.now(ZONA_ARGENTINA)
                hoy_str = ahora_arg.strftime("%Y-%m-%d")

                if channel_principal and todos_los_jefes:
                    for item in todos_los_jefes:
                        nombre = str(item.get("nombre", "")).strip()
                        
                        es_60_plus = item in raid_60_plus
                        if es_60_plus and FILTRO_PUBLICAR_RAIDS_ANTES.get("otros_60_mas", "no") != "si":
                            if FILTRO_PUBLICAR_RAIDS_ANTES.get(nombre, "no") != "si":
                                continue
                        elif not es_60_plus and FILTRO_PUBLICAR_RAIDS_ANTES.get(nombre, "no") != "si":
                            continue

                        tiempo_bruto = str(item.get("tiempo_str") or item.get("tiempo") or item.get("hora") or "").strip()
                        if not tiempo_bruto or tiempo_bruto in ["-", "None", "null", ""]:
                            continue

                        # Parseo formato DD-MM-YYYY HH:MM del JSON (Día-Mes-Año)
                        match_dt = re.search(r'(\d{2})-(\d{2})-(\d{4})\s+(\d{1,2}:\d{2})', tiempo_bruto)
                        if not match_dt:
                            match_hora = re.search(r'\d{1,2}:\d{2}', tiempo_bruto)
                            if not match_hora:
                                continue
                            hora_raid_str = match_hora.group(0)
                            fecha_raid_str = hoy_str
                        else:
                            dia, mes, anio, hora_raid_str = match_dt.groups()
                            # Reordenamos a YYYY-MM-DD para comparar con hoy_str
                            fecha_raid_str = f"{anio}-{mes}-{dia}"

                        if fecha_raid_str != hoy_str:
                            continue

                        try:
                            dt_raid = datetime.strptime(f"{fecha_raid_str} {hora_raid_str}", "%Y-%m-%d %H:%M").replace(tzinfo=ZONA_ARGENTINA)
                        except ValueError:
                            continue

                        sufijos_a_evaluar = []

                        if nombre in ["Valakas", "Antharas", "Fafureon"]:
                            dt_60m = dt_raid - timedelta(minutes=60)
                            dt_30m = dt_raid - timedelta(minutes=30)
                            dt_0m = dt_raid
                            sufijos_a_evaluar = [
                                (dt_60m, "1"),
                                (dt_30m, "2"),
                                (dt_0m, "3")
                            ]
                        elif nombre in ["Baium", "Zaken", "Core", "Orfen", "Queen Ant", "Frintezza", "Freya", "Zariche"]:
                            sufijos_a_evaluar = [
                                (dt_raid, "1")
                            ]
                        else:
                            dt_10m_antes = dt_raid - timedelta(minutes=10)
                            sufijos_a_evaluar = [
                                (dt_10m_antes, "1")
                            ]

                        for dt_objetivo, sufijo in sufijos_a_evaluar:
                            if dt_objetivo <= ahora_arg < dt_objetivo + timedelta(minutes=5):
                                clave_cache = f"{nombre}_{fecha_raid_str}_antes_{sufijo}"
                                
                                if CACHE_ANTES.get(clave_cache):
                                    break

                                nombre_archivo = f"{nombre.lower().replace(' ', '')}{sufijo}.png"
                                ruta_personalizada = f"imagen/raid/raid/antes/{nombre_archivo}"
                                
                                ruta_img = None
                                if os.path.exists(ruta_personalizada):
                                    ruta_img = ruta_personalizada
                                else:
                                    catalogo = obtener_catalogo_imagenes_raid()
                                    ruta_img = obtener_imagen_raid(catalogo, f"{nombre}{sufijo}", "PUBLICAR_RAIDS_ANTES")

                                if ruta_img and os.path.exists(ruta_img):
                                    with open(ruta_img, "rb") as binary:
                                        await channel_principal.send(file=discord.File(binary, filename=f"raid_{nombre.lower()}_antes_{sufijo}.png"))

                                    CACHE_ANTES[clave_cache] = True
                                    logger.info(f"✅ [ANTES] Aviso previo enviado para '{nombre}' (Sufijo: {sufijo}).")
                                    await asyncio.sleep(1.5)
                                break
        except Exception as e:
            logger.error(f"❌ Error en servicio_publicar_raids_antes: {e}")

        await asyncio.sleep(30)

# ==========================================
# GESTOR CENTRAL DE TAREAS (Inicia los servicios en paralelo)
# ==========================================
async def iniciar_monitoreo_permanente_raids(bot_instance, ruta_json="jefes_activos.json", intervalo_segundos=30):
    logger.info("🔄 Iniciando los servicios independientes de Raids en paralelo...")
    await bot_instance.wait_until_ready()

    asyncio.create_task(servicio_publicar_raids(bot_instance, ruta_json))
    asyncio.create_task(servicio_publicar_raids_antes(bot_instance, ruta_json))
