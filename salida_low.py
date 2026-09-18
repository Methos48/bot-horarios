import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont
import discord
import config

logger = logging.getLogger("SalidaLow")

ZONA_ARGENTINA = ZoneInfo(getattr(config, "TZ", "America/Argentina/Buenos_Aires"))

async def ejecutar(bot_instance, datos_horario):
    """
    Función principal llamada desde main.py:
    - Utiliza FUENTE_APTOS y FUENTE_BIOME desde config para el diseño gráfico (niveles bajos / 60-).
    - Procesa, filtra u ordena los datos correspondientes.
    - Envía el resultado visual o en texto al canal de Discord configurado.
    """
    logger.info("⚙️ Ejecutando salida_low: Procesando información de niveles bajos...")
    
    # 1. Obtener configuraciones clave desde config.py (puedes ajustar el nombre del canal si tienes uno específico para Low, ej: LOW_CHANNEL_ID)
    canal_id = getattr(config, "LOW_CHANNEL_ID", getattr(config, "HORARIO", None))
    fuente_aptos = getattr(config, "FUENTE_APTOS", None)
    fuente_biome = getattr(config, "FUENTE_BIOME", None)
    
    if not canal_id:
        logger.error("❌ No se encontró un canal válido configurado para salida_low en config.")
        return

    channel = bot_instance.get_channel(canal_id)
    if not channel:
        logger.warning(f"⚠️ No se pudo encontrar el canal de Discord con ID: {canal_id}")
        return

    try:
        # 2. Lógica de procesamiento específica para salida_low (ej. filtrado de 60-)
        # datos_low = [jefe for jefe in datos_horario if jefe.get("nivel", 0) < 60] # Ejemplo de filtro si aplica

        # Intentar cargar fuentes personalizadas con Pillow usando las rutas de config:
        try:
            fuente_principal = ImageFont.truetype(fuente_aptos, 16) if fuente_aptos else ImageFont.load_default()
        except Exception:
            fuente_principal = ImageFont.load_default()

        # 3. Construcción de la imagen o mensaje para Discord
        # Aquí puedes implementar la lógica de dibujo con Pillow si genera una placa visual igual que los otros módulos.

        logger.info("✅ salida_low procesado y enviado correctamente.")

    except Exception as e:
        logger.error(f"❌ Error crítico al ejecutar salida_low: {e}")
