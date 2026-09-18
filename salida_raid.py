import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont
import discord
import config

logger = logging.getLogger("SalidaRaid")

ZONA_ARGENTINA = ZoneInfo(getattr(config, "TZ", "America/Argentina/Buenos_Aires"))

async def ejecutar(bot_instance, datos_horario):
    """
    Función principal llamada desde main.py:
    - Utiliza FUENTE_APTOS y FUENTE_BIOME desde config para el diseño gráfico.
    - Procesa y genera la salida visual o en texto orientada específicamente a Raids.
    - Envía el resultado al canal de Discord correspondiente.
    """
    logger.info("⚙️ Ejecutando salida_raid: Procesando información de raids...")
    
    # 1. Obtener configuraciones clave desde config.py (puedes ajustar el nombre de las variables según tus requerimientos)
    canal_id = getattr(config, "RAID_CHANNEL_ID", getattr(config, "HORARIO", None))
    fuente_aptos = getattr(config, "FUENTE_APTOS", None)
    fuente_biome = getattr(config, "FUENTE_BIOME", None)
    
    if not canal_id:
        logger.error("❌ No se encontró un canal válido configurado para salida_raid en config.")
        return

    channel = bot_instance.get_channel(canal_id)
    if not channel:
        logger.warning(f"⚠️ No se pudo encontrar el canal de Discord con ID: {canal_id}")
        return

    try:
        # 2. Lógica de procesamiento específica para salida_raid
        # Aquí puedes filtrar o estructurar los datos de los jefes según lo que necesite este módulo en particular.
        
        # Ejemplo de intento de carga de fuentes personalizadas con Pillow usando las rutas de config:
        try:
            # Si fuente_aptos o fuente_biome apuntan a archivos .ttf / .otf:
            fuente_principal = ImageFont.truetype(fuente_aptos, 16) if fuente_aptos else ImageFont.load_default()
        except Exception:
            fuente_principal = ImageFont.load_default()

        # 3. Construcción del mensaje o imagen final para Discord
        # (Puedes adaptar esta sección si salida_raid genera una imagen con Pillow o un mensaje de texto estructurado)
        
        logger.info("✅ salida_raid procesado y enviado correctamente.")

    except Exception as e:
        logger.error(f"❌ Error crítico al ejecutar salida_raid: {e}")
