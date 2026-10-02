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
CACHE_SALIO = {}
ESTADOS_PREVIOS_RAIDS = {}      # Guarda el estado anterior ("muerto" / "vivo") de cada raid para el servicio SALIO
TIEMPOS_CAMBIO_VIVO = {}        # Guarda el timestamp exacto en que un raid pasó a "vivo"
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

FILTRO_PUBLICAR_RAIDS_SALIO = {
    "Valakas": "si", "Antharas": "si", "Fafureon": "si", "Balrog": "si",
    "Electrical": "si", "Baium": "si", "Zaken": "si", "Core": "si",
    "Orfen": "si", "Queen Ant": "si", "Frintezza": "si", "Freya": "si",
    "Zariche": "si", "Decarbia": "si", "Hekaton": "si", "Queen shyeed": "si",
    "Golkonda": "si", "Galaxia": "si", "Barakiel": "si",
    "otros_60_mas": "si", "otros_60_menos": "no"
}

# Lista de épicos y dragones para validaciones de doble canal en ANTES
EPICOS_Y_DRAGONES = [
    "Baium", "Zaken", "Core", "Orfen", "Queen Ant", 
    "Frintezza", "Freya", "Zariche", "Valakas", "Antharas", "Fafureon"
]

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
    elif tipo_servicio == "PUBLICAR_RAIDS_SALIO":
        rutas_candidatas = [f"raid/antes/{nombre_limpio}.png", f"salio/{nombre_limpio}.png", f"{TEMA_ACTIVO}/salio/{nombre_limpio}.png"]

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
    global ULTIMO_RESET_CACHE_DIA, CACHE_PUBLICAR_RAIDS, CACHE_ANTES, CACHE_SALIO, ESTADOS_PREVIOS_RAIDS, TIEMPOS_CAMBIO_VIVO
    ahora_arg = datetime.now(ZONA_ARGENTINA)
    hoy_str = ahora_arg.strftime("%Y-%m-%d")
    
    if ahora_arg.hour >= 4 and ULTIMO_RESET_CACHE_DIA != hoy_str:
        CACHE_PUBLICAR_RAIDS.clear()
        CACHE_ANTES.clear()
        CACHE_SALIO.clear()
        ESTADOS_PREVIOS_RAIDS.clear()
        TIEMPOS_CAMBIO_VIVO.clear()
        ULTIMO_RESET_CACHE_DIA = hoy_str
        logger.info("🧹 Memoria caché de los 3 servicios limpiada exitosamente a las 04:00 AM.")

async def enviar_a_canales_salio(bot_instance, ruta_imagen, nombre_archivo_discord, es_epico=False):
    """Envía la imagen a ENVIAR_MENSAJE_CHANNEL_ID y, si es épico, también a MENSAJE_CLAN_CHANNEL_ID."""
    canal_principal_id = getattr(config, "ENVIAR_MENSAJE_CHANNEL_ID", None)
    canal_clan_id = getattr(config, "MENSAJE_CLAN_CHANNEL_ID", None)
    
    canales_destino = []
    if canal_principal_id:
        c1 = bot_instance.get_channel(canal_principal_id)
        if c1:
            canales_destino.append(c1)
            
    if es_epico and canal_clan_id:
        c2 = bot_instance.get_channel(canal_clan_id)
        if c2 and c2 not in canales_destino:
            canales_destino.append(c2)

    for canal in canales_destino:
        try:
            if os.path.exists(ruta_imagen):
                with open(ruta_imagen, "rb") as binary:
                    await canal.send(file=discord.File(binary, filename=nombre_archivo_discord))
        except Exception as e:
            logger.error(f"❌ Error al enviar imagen de SALIO al canal {canal.id}: {e}")

# ==========================================
# SERVICIO 1: PUBLICAR_RAIDS (Usa MENSAJE_CLAN_CHANNEL_ID)
# ==========================================
async def servicio_publicar_raids(bot_instance, ruta_json):
    while not bot_instance.is_closed():
        try:
            limpiar_memoria_cache_diaria()
            canal_id = getattr(config, "MENSAJE_CLAN_CHANNEL_ID", None)
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

                        match_hora = re.search(r'\d{1,2}:\d{2}', tiempo_bruto)
                        if not match_hora:
                            continue
                        
                        hora_raid_str = match_hora.group(0)
                        
                        fecha_raid_str = hoy_str
                        match_fecha = re.search(r'\d{4}-\d{2}-\d{2}', tiempo_bruto)
                        if match_fecha:
                            fecha_raid_str = match_fecha.group(0)

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
                                logger.info(f"✅ [PUBLICAR_RAIDS] Raid '{nombre}' enviado con éxito al canal de clan (Ventana: {tipo_ventana}).")
                                await asyncio.sleep(1.5)
        except Exception as e:
            logger.error(f"❌ Error en servicio_publicar_raids: {e}")
        
        await asyncio.sleep(30)

# ==========================================
# SERVICIO 2: PUBLICAR_RAIDS_ANTES (ENVIAR_MENSAJE_CHANNEL_ID + MENSAJE_CLAN_CHANNEL_ID para la lista indicada)
# ==========================================
async def servicio_publicar_raids_antes(bot_instance, ruta_json):
    while not bot_instance.is_closed():
        try:
            limpiar_memoria_cache_diaria()
            canal_principal_id = getattr(config, "ENVIAR_MENSAJE_CHANNEL_ID", None)
            canal_clan_id = getattr(config, "MENSAJE_CLAN_CHANNEL_ID", None)
            
            if canal_principal_id and os.path.exists(ruta_json):
                async with json_lock:
                    with open(ruta_json, "r", encoding="utf-8") as f:
                        data = json.load(f)

                raid_60_plus = data.get("raid_60_plus", [])
                raid_60_menos = data.get("raid_60_menos", [])
                vivo_o_muerto = data.get("vivo_o_muerto", [])

                todos_los_jefes = list(raid_60_plus) + list(raid_60_menos) + list(vivo_o_muerto)
                
                channel_principal = bot_instance.get_channel(canal_principal_id)
                channel_clan = bot_instance.get_channel(canal_clan_id) if canal_clan_id else None

                ahora_arg = datetime.now(ZONA_ARGENTINA)
                hoy_str = ahora_arg.strftime("%Y-%m-%d")

                if channel_principal and todos_los_jefes:
                    for item in todos_los_jefes:
                        nombre = str(item.get("nombre", "")).strip()
                        if FILTRO_PUBLICAR_RAIDS_ANTES.get(nombre, "no") != "si":
                            continue

                        tiempo_bruto = str(item.get("tiempo_str") or item.get("tiempo") or item.get("hora") or "").strip()
                        if not tiempo_bruto or tiempo_bruto in ["-", "None", "null", ""]:
                            continue

                        match_hora = re.search(r'\d{1,2}:\d{2}', tiempo_bruto)
                        if not match_hora:
                            continue
                        
                        hora_raid_str = match_hora.group(0)
                        fecha_raid_str = hoy_str
                        match_fecha = re.search(r'\d{4}-\d{2}-\d{2}', tiempo_bruto)
                        if match_fecha:
                            fecha_raid_str = match_fecha.group(0)

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

                                nombre_archivo = f"{nombre.lower()}{sufijo}.png"
                                # Ruta actualizada según la imagen proporcionada (imagen/raid/raid/antes/)
                                ruta_personalizada = f"imagen/raid/raid/antes/{nombre_archivo}"
                                
                                ruta_img = None
                                if os.path.exists(ruta_personalizada):
                                    ruta_img = ruta_personalizada
                                else:
                                    catalogo = obtener_catalogo_imagenes_raid()
                                    ruta_img = obtener_imagen_raid(catalogo, f"{nombre}{sufijo}", "PUBLICAR_RAIDS_ANTES")

                                if ruta_img and os.path.exists(ruta_img):
                                    # 1. Enviar siempre al canal principal (ENVIAR_MENSAJE_CHANNEL_ID)
                                    with open(ruta_img, "rb") as binary:
                                        await channel_principal.send(file=discord.File(binary, filename=f"raid_{nombre.lower()}_antes_{sufijo}.png"))
                                    
                                    # 2. Si pertenece a la lista indicada, enviar también al canal de clan (MENSAJE_CLAN_CHANNEL_ID)
                                    if nombre in EPICOS_Y_DRAGONES and channel_clan:
                                        try:
                                            with open(ruta_img, "rb") as binary_clan:
                                                await channel_clan.send(file=discord.File(binary_clan, filename=f"raid_{nombre.lower()}_antes_{sufijo}.png"))
                                        except Exception as e_clan:
                                            logger.error(f"❌ Error al enviar aviso ANTES al canal de clan para '{nombre}': {e_clan}")

                                    CACHE_ANTES[clave_cache] = True
                                    logger.info(f"✅ [ANTES] Aviso previo enviado para '{nombre}' (Sufijo: {sufijo}).")
                                    await asyncio.sleep(1.5)
                                break
        except Exception as e:
            logger.error(f"❌ Error en servicio_publicar_raids_antes: {e}")

        await asyncio.sleep(30)

# ==========================================
# SERVICIO 3: PUBLICAR_RAIDS_SALIO
# ==========================================
async def servicio_publicar_raids_salio(bot_instance, ruta_json):
    while not bot_instance.is_closed():
        try:
            limpiar_memoria_cache_diaria()
            if os.path.exists(ruta_json):
                # 🔒 LOCK APLICADO TAMBIÉN AQUÍ PARA EVITAR JSONDecodeError
                async with json_lock:
                    with open(ruta_json, "r", encoding="utf-8") as f:
                        data = json.load(f)

                vivo_o_muerto = data.get("vivo_o_muerto", [])
                ahora_arg = datetime.now(ZONA_ARGENTINA)
                hoy_str = ahora_arg.strftime("%Y-%m-%d")

                if vivo_o_muerto:
                    for item in vivo_o_muerto:
                        nombre = str(item.get("nombre", "")).strip()
                        
                        if FILTRO_PUBLICAR_RAIDS_SALIO.get(nombre, "no") != "si":
                            continue

                        estado_actual_json = str(item.get("estado") or item.get("status") or item.get("vivo_o_muerto") or "").strip().lower()
                        if not estado_actual_json:
                            continue

                        estado_anterior = ESTADOS_PREVIOS_RAIDS.get(nombre, "muerto")

                        if estado_anterior == "muerto" and estado_actual_json == "vivo":
                            ESTADOS_PREVIOS_RAIDS[nombre] = "vivo"
                            TIEMPOS_CAMBIO_VIVO[nombre] = ahora_arg
                            logger.info(f"⚡ [SALIO] Cambio detectado: '{nombre}' pasó de MUERTO a VIVO.")

                            if nombre in ["Baium", "Zaken", "Core", "Orfen", "Queen Ant", "Frintezza", "Freya", "Zariche"]:
                                sufijo = "2"
                                clave_cache = f"{nombre}_{hoy_str}_sufijo_{sufijo}"
                                
                                if not CACHE_SALIO.get(clave_cache):
                                    nombre_archivo = f"{nombre.lower()}{sufijo}.png"
                                    # Ruta actualizada según la imagen proporcionada (imagen/raid/raid/antes/)
                                    ruta_img = f"imagen/raid/raid/antes/{nombre_archivo}"

                                    if os.path.exists(ruta_img):
                                        await enviar_a_canales_salio(bot_instance, ruta_img, f"raid_{nombre.lower()}_salio_{sufijo}.png", es_epico=True)
                                        CACHE_SALIO[clave_cache] = True
                                        logger.info(f"✅ [SALIO] Publicado épico inmediato '{nombre}' (Sufijo {sufijo}).")
                                        await asyncio.sleep(1.0)

                            elif nombre in ["Valakas", "Antharas", "Fafureon"]:
                                sufijo = "4"
                                clave_cache = f"{nombre}_{hoy_str}_sufijo_{sufijo}"
                                
                                if not CACHE_SALIO.get(clave_cache):
                                    nombre_archivo = f"{nombre.lower()}{sufijo}.png"
                                    # Ruta actualizada según la imagen proporcionada (imagen/raid/raid/antes/)
                                    ruta_img = f"imagen/raid/raid/antes/{nombre_archivo}"

                                    if os.path.exists(ruta_img):
                                        await enviar_a_canales_salio(bot_instance, ruta_img, f"raid_{nombre.lower()}_salio_{sufijo}.png", es_epico=True)
                                        CACHE_SALIO[clave_cache] = True
                                        logger.info(f"✅ [SALIO] Publicado gran dragón inmediato '{nombre}' (Sufijo {sufijo}).")
                                        await asyncio.sleep(1.0)

                        if estado_actual_json == "muerto":
                            ESTADOS_PREVIOS_RAIDS[nombre] = "muerto"

                        if nombre in ["Valakas", "Antharas"] and ESTADOS_PREVIOS_RAIDS.get(nombre) == "vivo":
                            tiempo_cambio = TIEMPOS_CAMBIO_VIVO.get(nombre)
                            if tiempo_cambio:
                                tiempo_objetivo_35m = tiempo_cambio + timedelta(minutes=35)
                                
                                if tiempo_objetivo_35m <= ahora_arg < tiempo_objetivo_35m + timedelta(minutes=5):
                                    sufijo = "5"
                                    clave_cache = f"{nombre}_{hoy_str}_sufijo_{sufijo}_35m"
                                    
                                    if not CACHE_SALIO.get(clave_cache):
                                        nombre_archivo = f"{nombre.lower()}{sufijo}.png"
                                        # Ruta actualizada según la imagen proporcionada (imagen/raid/raid/antes/)
                                        ruta_img = f"imagen/raid/raid/antes/{nombre_archivo}"

                                        if os.path.exists(ruta_img):
                                            await enviar_a_canales_salio(bot_instance, ruta_img, f"raid_{nombre.lower()}_salio_{sufijo}.png", es_epico=True)
                                            CACHE_SALIO[clave_cache] = True
                                            logger.info(f"✅ [SALIO] Publicado '{nombre}' a los 35 minutos (Sufijo {sufijo}).")
                                            await asyncio.sleep(1.0)

        except Exception as e:
            logger.error(f"❌ Error en servicio_publicar_raids_salio: {e}")

        await asyncio.sleep(30)

# ==========================================
# GESTOR CENTRAL DE TAREAS (Inicia los 3 servicios en paralelo)
# ==========================================
async def iniciar_monitoreo_permanente_raids(bot_instance, ruta_json="jefes_activos.json", intervalo_segundos=30):
    logger.info("🔄 Iniciando los 3 servicios independientes de Raids en paralelo...")
    await bot_instance.wait_until_ready()

    asyncio.create_task(servicio_publicar_raids(bot_instance, ruta_json))
    asyncio.create_task(servicio_publicar_raids_antes(bot_instance, ruta_json))
    asyncio.create_task(servicio_publicar_raids_salio(bot_instance, ruta_json))
