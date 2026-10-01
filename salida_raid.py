import os
import logging
import json
import io
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter
import discord
import config

logger = logging.getLogger("SalidaRaid")

ZONA_ARGENTINA = ZoneInfo(getattr(config, "TZ", "America/Argentina/Buenos_Aires"))

# ==========================================
# CACHÉ DE HISTORIAL Y CONTROL DINÁMICO (Antiduplicados)
# ==========================================
HISTORIAL_ENVIADOS_CACHE = {}
ULTIMO_RESET_CACHE_DIA = None  

# ==========================================
# CONFIGURACIÓN DE TEMA / ESTILO VISUAL Y FUENTES
# ==========================================
TEMA_ACTIVO = "rojo"  # Puede cambiar a "morado", etc.

FUENTE_BANKGOTHIC = getattr(config, "FUENTE_BANKGOTHIC", "arial.ttf")
FUENTE_APTOS = getattr(config, "FUENTE_APTOS", "arial.ttf")
FUENTE_BIOME = getattr(config, "FUENTE_BIOME", "arial.ttf")
DIR_TEXTURA = getattr(config, "DIR_TEXTURA", None)

# ==========================================
# POSICIÓN MANUAL DE LA HORA (Modifica aquí para calibrar X e Y)
# ==========================================
POS_X = 20
POS_Y = 565

JEFS_ESPECIALES_RANDOM = {
    "core", "orfen", "baium", "zaken", "freya", 
    "zariche", "frintezza", "queen ant", "electrical", "balrog"
}

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


def aplicar_textura_a_texto(imagen_base, texto, x, y, ruta_fuente, ruta_textura, tamano_fuente=60):
    try:
        fuente = ImageFont.truetype(ruta_fuente, size=tamano_fuente)
    except IOError:
        fuente = ImageFont.load_default()

    txt_capa = Image.new("L", imagen_base.size, 0)
    draw_txt = ImageDraw.Draw(txt_capa)
    draw_txt.text((x, y), texto, fill=255, font=fuente)

    if ruta_textura and os.path.exists(ruta_textura):
        try:
            textura = Image.open(ruta_textura).convert("RGBA")
            textura = textura.resize(imagen_base.size)
        except Exception:
            textura = Image.new("RGBA", imagen_base.size, (200, 200, 200, 255))
    else:
        textura = Image.new("RGBA", imagen_base.size, (200, 200, 200, 255))

    imagen_base.paste(textura, (0, 0), txt_capa)


def obtener_catalogo_imagenes_raid():
    directorio_base = getattr(config, "DIR_RAID", "imagen/raid")
    catalogo = {}
    
    if not os.path.exists(directorio_base):
        logger.warning(f"⚠️ El directorio de raids '{directorio_base}' no existe.")
        return catalogo

    for root, dirs, files in os.walk(directorio_base):
        for archivo in files:
            if archivo.lower().endswith(('.png', '.webp', '.jpg', '.jpeg')):
                ruta_completa = os.path.join(root, archivo)
                clave_relativa = os.path.relpath(ruta_completa, directorio_base).replace("\\", "/")
                catalogo[clave_relativa.lower()] = ruta_completa
                catalogo[archivo.lower()] = ruta_completa
                
    return catalogo


def obtener_imagen_raid(catalogo, nombre_base_raid, tema=TEMA_ACTIVO, tipo_filtro="PUBLICAR_RAIDS"):
    nombre_limpio = nombre_base_raid.strip().lower()
    
    rutas_candidatas = [
        f"{tema}/raid/{nombre_limpio}.png",
        f"{tema}/{nombre_limpio}.png",
        f"raid/{tema}/raid/{nombre_limpio}.png",
        f"raid/{tema}/{nombre_limpio}.png",
        f"antes/{nombre_limpio}.png",
        f"{nombre_limpio}.png"
    ]

    for sufijo in ['h', 'm']:
        rutas_candidatas.insert(0, f"{tema}/raid/{nombre_limpio}{sufijo}.png")
        rutas_candidatas.insert(0, f"raid/{tema}/raid/{nombre_limpio}{sufijo}.png")

    for ruta in rutas_candidatas:
        for clave_cat in catalogo:
            if clave_cat.endswith(ruta.lower()) or clave_cat == ruta.lower():
                return catalogo[clave_cat]
                
    for clave, ruta_completa in catalogo.items():
        if nombre_limpio in clave:
            return ruta_completa

    return None


async def enviar_prueba_calibracion(bot_instance):
    """
    Función exclusiva para forzar el envío inmediato de Valakas con la hora 22:30 
    tan pronto el bot se conecta y está listo.
    """
    await bot_instance.wait_until_ready()
    await asyncio.sleep(3)
    
    canal_id = getattr(config, "ENVIAR_MENSAJE_CHANNEL_ID", None) or 1549577944999927999
    channel_destino = bot_instance.get_channel(canal_id)
    
    if not channel_destino:
        logger.error(f"❌ [CALIBRACIÓN] No se encontró el canal con ID {canal_id}")
        return

    catalogo_raids = obtener_catalogo_imagenes_raid()
    logger.info(f"📁 Catálogo de raids cargado con {len(catalogo_raids)} archivos detectados.")

    nombre_imagen_base = "valakas"
    ruta_imagen = obtener_imagen_raid(catalogo_raids, nombre_imagen_base, tema=TEMA_ACTIVO, tipo_filtro="PUBLICAR_RAIDS")

    if ruta_imagen and os.path.exists(ruta_imagen):
        try:
            img = Image.open(ruta_imagen).convert("RGBA")
            texto_hora = "22:30"
            
            aplicar_textura_a_texto(
                imagen_base=img,
                texto=texto_hora,
                x=POS_X,
                y=POS_Y,
                ruta_fuente=FUENTE_BANKGOTHIC,
                ruta_textura=DIR_TEXTURA,
                tamano_fuente=60
            )
            
            with io.BytesIO() as image_binary:
                img.convert("RGB").save(image_binary, "PNG")
                image_binary.seek(0)
                await channel_destino.send(
                    content="🧪 **[PRUEBA DE CALIBRACIÓN]**",
                    file=discord.File(image_binary, filename=f"raid_{nombre_imagen_base}_2230.png")
                )
                logger.info(f"🎯 [CALIBRACIÓN EXITOSA] Valakas enviado con la hora 22:30 al canal {canal_id}")
        except Exception as e:
            logger.error(f"❌ [CALIBRACIÓN] Error al generar/enviar la imagen: {e}")
    else:
        logger.error(f"❌ [CALIBRACIÓN] No se encontró la imagen de valakas en las rutas de carpetas de '{TEMA_ACTIVO}'.")


async def procesar_ciclo_raids(bot_instance, ruta_json, tipo_filtro, intervalo_segundos=30):
    """Procesa los ciclos regulares de raids leyendo del archivo JSON provisto."""
    try:
        canal_id = getattr(config, "ENVIAR_MENSAJE_CHANNEL_ID", None)
        if not canal_id or not os.path.exists(ruta_json):
            return

        with open(ruta_json, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Seleccionar la lista correspondiente según la estructura del json
        registros = data.get("raid_60_plus", []) or data.get("vivo_o_muerto", [])
        if not registros:
            return

        catalogo_raids = obtener_catalogo_imagenes_raid()
        channel_destino = bot_instance.get_channel(canal_id)
        if not channel_destino:
            return

        # Lógica de procesamiento de filtros y alertas programadas
        for item in registros:
            nombre = str(item.get("nombre", "")).strip()
            tiempo_str = str(item.get("tiempo_str", "")).strip()
            
            if not nombre or not tiempo_str or tiempo_str in ["-", "None"]:
                continue

            # Aquí se pueden integrar validaciones adicionales de tiempo o caché si es necesario

    except Exception as e:
        logger.error(f"❌ Error en procesar_ciclo_raids para {tipo_filtro}: {e}")


async def iniciar_monitoreo_permanente_raids(bot_instance, ruta_json="jefes_activos.json", intervalo_segundos=30):
    global HISTORIAL_ENVIADOS_CACHE, ULTIMO_RESET_CACHE_DIA
    logger.info(f"🔄 Bucle permanente de monitoreo de Raids iniciado. Intervalo: {intervalo_segundos}s")
    
    # Lanzar la prueba de calibración en segundo plano al arrancar
    asyncio.create_task(enviar_prueba_calibracion(bot_instance))

    await bot_instance.wait_until_ready()

    while not bot_instance.is_closed():
        try:
            ahora_actual = datetime.now(ZONA_ARGENTINA)
            fecha_hoy = ahora_actual.date()
            if ULTIMO_RESET_CACHE_DIA is None or fecha_hoy > ULTIMO_RESET_CACHE_DIA:
                ULTIMO_RESET_CACHE_DIA = fecha_hoy
                HISTORIAL_ENVIADOS_CACHE.clear()

            for tipo in ["PUBLICAR_RAIDS", "PUBLICAR_RAIDS_ANTES", "PUBLICAR_RAIDS_SALIO", "super_epicos"]:
                await procesar_ciclo_raids(bot_instance, ruta_json, tipo, intervalo_segundos)
                
        except Exception as e:
            logger.error(f"❌ Error en el ciclo de monitoreo permanente: {e}")
        
        await asyncio.sleep(intervalo_segundos)
