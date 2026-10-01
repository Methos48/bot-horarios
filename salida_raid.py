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
TEMA_ACTIVO = "rojo"

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
                catalogo[clave_relativa] = ruta_completa
                
    return catalogo


def obtener_imagen_raid(catalogo, nombre_base_raid, tema=TEMA_ACTIVO, tipo_filtro="PUBLICAR_RAIDS"):
    if tipo_filtro in ["PUBLICAR_RAIDS_ANTES", "PUBLICAR_RAIDS_SALIO", "super_epicos", "antes", "salio"]:
        subcarpetas_a_probar = ["raid/antes/", ""]
    else:
        subcarpetas_a_probar = [f"{tema}/raid/", f"{tema}/"]

    for sub in subcarpetas_a_probar:
        for ext in ['.png', '.jpg', '.webp', '.jpeg']:
            claves_intento = [
                f"{sub}{nombre_base_raid}{ext}",
                f"raid/{sub}{nombre_base_raid}{ext}"
            ]
            
            for clave_intento in claves_intento:
                if clave_intento in catalogo:
                    return catalogo[clave_intento]

    return None


async def procesar_ciclo_raids(bot_instance, ruta_json, tipo_filtro, intervalo_segundos=30):
    ahora_actual = datetime.now(ZONA_ARGENTINA)

    canal_id = 1549577944999927999 if tipo_filtro == "PUBLICAR_RAIDS" else getattr(config, "ENVIAR_MENSAJE_CHANNEL_ID", None)
    
    if not canal_id:
        return

    # ==========================================
    # MODO CALIBRACIÓN / PRUEBA: VALAKASH CON HORA FIJA 22:30
    # ==========================================
    if tipo_filtro == "PUBLICAR_RAIDS":
        # Usamos una clave fija o única de inicio para asegurar que se mande apenas arranque
        clave_id_calibracion = "valakash_calibracion_2230_inicios"
        
        if clave_id_calibracion not in HISTORIAL_ENVIADOS_CACHE:
            HISTORIAL_ENVIADOS_CACHE[clave_id_calibracion] = ahora_actual
            
            catalogo_raids = obtener_catalogo_imagenes_raid()
            nombre_imagen_base = "valakash"  # Buscará directamente 'valakash.png' en tus carpetas
            
            ruta_imagen = obtener_imagen_raid(catalogo_raids, nombre_imagen_base, tema=TEMA_ACTIVO, tipo_filtro=tipo_filtro)
            
            if not ruta_imagen:
                # Respaldo por si no encuentra la terminación 'h' exacta
                ruta_imagen = obtener_imagen_raid(catalogo_raids, "valakas", tema=TEMA_ACTIVO, tipo_filtro=tipo_filtro)
                nombre_imagen_base = "valakas"

            if ruta_imagen:
                channel_destino = bot_instance.get_channel(canal_id)
                if channel_destino:
                    img = Image.open(ruta_imagen).convert("RGBA")
                    texto_hora = "22:30"  # Hora fija solicitada para calibrar
                    
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
                        await channel_destino.send(file=discord.File(image_binary, filename=f"raid_{nombre_imagen_base}_2230.png"))
                        logger.info(f"🎯 [CALIBRACIÓN] Valakash enviado con éxito a las 22:30 al canal {canal_id}")
                else:
                    logger.error(f"❌ No se pudo encontrar el canal de destino con ID {canal_id}")
            else:
                logger.error(f"❌ No se encontró ninguna imagen para valakash en el catálogo de raids.")
        return

    # Lógica de los demás servicios basada en JSON...
    if not os.path.exists(ruta_json):
        return

    try:
        with open(ruta_json, "r", encoding="utf-8") as f:
            contenido_json = json.load(f)
            
        vivo_o_muerto = contenido_json.get("vivo_o_muerto", [])
        raid_60_plus = contenido_json.get("raid_60_plus", [])
        datos_horario = vivo_o_muerto + raid_60_plus
    except Exception as e:
        logger.error(f"❌ Error al leer JSON: {e}")
        return


async def iniciar_monitoreo_permanente(bot_instance, ruta_json="horarios.json", intervalo_segundos=30):
    global HISTORIAL_ENVIADOS_CACHE, ULTIMO_RESET_CACHE_DIA
    logger.info(f"🔄 Bucle permanente de monitoreo de Raids iniciado. Intervalo: {intervalo_segundos}s")
    
    await bot_instance.wait_until_ready()

    while not bot_instance.is_closed():
        try:
            ahora_actual = datetime.now(ZONA_ARGENTINA)

            fecha_hoy = ahora_actual.date()
            if ULTIMO_RESET_CACHE_DIA is None or fecha_hoy > ULTIMO_RESET_CACHE_DIA:
                # Opcional: si quieres que se mande cada vez que reinicies el bot para probar, 
                # puedes comentar la línea de abajo o dejarla para que limpie solo al cambiar de día.
                # HISTORIAL_ENVIADOS_CACHE.clear() 
                ULTIMO_RESET_CACHE_DIA = fecha_hoy

            for tipo in ["PUBLICAR_RAIDS", "PUBLICAR_RAIDS_ANTES", "PUBLICAR_RAIDS_SALIO", "super_epicos"]:
                await procesar_ciclo_raids(bot_instance, ruta_json, tipo, intervalo_segundos)
                
        except Exception as e:
            logger.error(f"❌ Error en el ciclo de monitoreo permanente: {e}")
        
        await asyncio.sleep(intervalo_segundos)
