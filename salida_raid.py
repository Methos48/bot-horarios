import os
import logging
import json
import io
import asyncio
import re
from datetime import datetime
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

# Cachés independientes para evitar cruces
CACHE_PUBLICAR_RAIDS = {}
CACHE_ANTES = {}
CACHE_SALIO = {}
CACHE_SUPER_EPICOS = {}
ULTIMO_RESET_CACHE_DIA = None  

TEMA_ACTIVO = "rojo"  
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

FILTRO_PUBLICAR_RAIDS_SALIO = {
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
        rutas_candidatas = [f"antes/{nombre_limpio}.png", f"{TEMA_ACTIVO}/antes/{nombre_limpio}.png"]
    elif tipo_servicio == "PUBLICAR_RAIDS_SALIO":
        rutas_candidatas = [f"salio/{nombre_limpio}.png", f"{TEMA_ACTIVO}/salio/{nombre_limpio}.png"]

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


# ==========================================
# SERVICIO 1: PUBLICAR_RAIDS (Independiente - Acceso a las 3 tablas)
# ==========================================
async def servicio_publicar_raids(bot_instance, ruta_json):
    while not bot_instance.is_closed():
        try:
            canal_id = getattr(config, "ENVIAR_MENSAJE_CHANNEL_ID", None)
            if canal_id and os.path.exists(ruta_json):
                with open(ruta_json, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Acceso independiente y disponible a las 3 tablas del JSON
                raid_60_plus = data.get("raid_60_plus", [])
                raid_60_menos = data.get("raid_60_menos", [])
                vivo_o_muerto = data.get("vivo_o_muerto", [])

                catalogo = obtener_catalogo_imagenes_raid()
                channel = bot_instance.get_channel(canal_id)

                # Por ahora, procesamos raid_60_plus (las otras tablas quedan disponibles en memoria para su lógica futura)
                if channel and raid_60_plus:
                    for item in raid_60_plus:
                        nombre = str(item.get("nombre", "")).strip()
                        if FILTRO_PUBLICAR_RAIDS.get(nombre, "no") != "si":
                            continue

                        tiempo_bruto = str(item.get("tiempo_str") or item.get("tiempo") or item.get("hora") or "").strip()
                        if not tiempo_bruto or tiempo_bruto in ["-", "None", "null", ""]:
                            continue

                        match_hora = re.search(r'\d{1,2}:\d{2}', tiempo_bruto)
                        tiempo_str = match_hora.group(0) if match_hora else ""
                        if not tiempo_str:
                            continue

                        # Validación estricta de hora exacta
                        hora_actual_str = datetime.now(ZONA_ARGENTINA).strftime("%H:%M")
                        if hora_actual_str != tiempo_str:
                            continue

                        clave_cache = f"{nombre}_{tiempo_str}"
                        if CACHE_PUBLICAR_RAIDS.get(clave_cache):
                            continue

                        ruta_img = obtener_imagen_raid(catalogo, nombre, "PUBLICAR_RAIDS")
                        if ruta_img and os.path.exists(ruta_img):
                            img = Image.open(ruta_img).convert("RGBA")
                            estampar_hora_con_imagenes(img, tiempo_str, POS_X, POS_Y, altura_deseada=95, espacio_entre_digitos=4)
                            
                            with io.BytesIO() as binary:
                                img.convert("RGB").save(binary, "PNG")
                                binary.seek(0)
                                await channel.send(file=discord.File(binary, filename=f"raid_{nombre.lower()}_{tiempo_str.replace(':', '')}.png"))
                                CACHE_PUBLICAR_RAIDS[clave_cache] = True
                                logger.info(f"✅ [PUBLICAR_RAIDS] Raid '{nombre}' enviado con hora {tiempo_str}.")
                                await asyncio.sleep(1.5)
        except Exception as e:
            logger.error(f"❌ Error en servicio_publicar_raids: {e}")
        
        await asyncio.sleep(30)


# ==========================================
# SERVICIO 2: PUBLICAR_RAIDS_ANTES (Independiente - Acceso a las 3 tablas)
# ==========================================
async def servicio_publicar_raids_antes(bot_instance, ruta_json):
    while not bot_instance.is_closed():
        try:
            canal_id = getattr(config, "ENVIAR_MENSAJE_CHANNEL_ID", None)
            if canal_id and os.path.exists(ruta_json):
                with open(ruta_json, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Acceso independiente y disponible a las 3 tablas del JSON
                raid_60_plus = data.get("raid_60_plus", [])
                raid_60_menos = data.get("raid_60_menos", [])
                vivo_o_muerto = data.get("vivo_o_muerto", [])

                catalogo = obtener_catalogo_imagenes_raid()
                channel = bot_instance.get_channel(canal_id)
                fecha_hoy = datetime.now(ZONA_ARGENTINA).strftime("%Y-%m-%d")

                if channel and raid_60_plus:
                    for item in raid_60_plus:
                        nombre = str(item.get("nombre", "")).strip()
                        if FILTRO_PUBLICAR_RAIDS_ANTES.get(nombre, "no") != "si":
                            continue

                        clave_cache = f"{nombre}_{fecha_hoy}"
                        if CACHE_ANTES.get(clave_cache):
                            continue

                        ruta_img = obtener_imagen_raid(catalogo, nombre, "PUBLICAR_RAIDS_ANTES")
                        if ruta_img and os.path.exists(ruta_img):
                            with open(ruta_img, "rb") as binary:
                                await channel.send(file=discord.File(binary, filename=f"raid_{nombre.lower()}_antes.png"))
                                CACHE_ANTES[clave_cache] = True
                                logger.info(f"✅ [ANTES] Aviso previo enviado para '{nombre}'.")
                                await asyncio.sleep(1.5)
        except Exception as e:
            logger.error(f"❌ Error en servicio_publicar_raids_antes: {e}")

        await asyncio.sleep(30)


# ==========================================
# SERVICIO 3: PUBLICAR_RAIDS_SALIO (Independiente - Acceso a las 3 tablas)
# ==========================================
async def servicio_publicar_raids_salio(bot_instance, ruta_json):
    while not bot_instance.is_closed():
        try:
            canal_id = getattr(config, "ENVIAR_MENSAJE_CHANNEL_ID", None)
            if canal_id and os.path.exists(ruta_json):
                with open(ruta_json, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Acceso independiente y disponible a las 3 tablas del JSON
                raid_60_plus = data.get("raid_60_plus", [])
                raid_60_menos = data.get("raid_60_menos", [])
                vivo_o_muerto = data.get("vivo_o_muerto", [])

                catalogo = obtener_catalogo_imagenes_raid()
                channel = bot_instance.get_channel(canal_id)
                fecha_hoy = datetime.now(ZONA_ARGENTINA).strftime("%Y-%m-%d")

                if channel and raid_60_plus:
                    for item in raid_60_plus:
                        nombre = str(item.get("nombre", "")).strip()
                        if FILTRO_PUBLICAR_RAIDS_SALIO.get(nombre, "no") != "si":
                            continue

                        clave_cache = f"{nombre}_{fecha_hoy}"
                        if CACHE_SALIO.get(clave_cache):
                            continue

                        ruta_img = obtener_imagen_raid(catalogo, nombre, "PUBLICAR_RAIDS_SALIO")
                        if ruta_img and os.path.exists(ruta_img):
                            with open(ruta_img, "rb") as binary:
                                await channel.send(file=discord.File(binary, filename=f"raid_{nombre.lower()}_salio.png"))
                                CACHE_SALIO[clave_cache] = True
                                logger.info(f"✅ [SALIO] Aviso de salida enviado para '{nombre}'.")
                                await asyncio.sleep(1.5)
        except Exception as e:
            logger.error(f"❌ Error en servicio_publicar_raids_salio: {e}")

        await asyncio.sleep(30)


# ==========================================
# GESTOR CENTRAL DE TAREAS (Inicia los servicios en paralelo)
# ==========================================
async def iniciar_monitoreo_permanente_raids(bot_instance, ruta_json="jefes_activos.json", intervalo_segundos=30):
    logger.info("🔄 Iniciando servicios independientes de Raids en paralelo...")
    await bot_instance.wait_until_ready()

    # Lanzamos cada servicio de forma totalmente independiente como tareas concurrentes en background
    asyncio.create_task(servicio_publicar_raids(bot_instance, ruta_json))
    asyncio.create_task(servicio_publicar_raids_antes(bot_instance, ruta_json))
    asyncio.create_task(servicio_publicar_raids_salio(bot_instance, ruta_json))
