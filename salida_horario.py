import logging
from datetime import datetime
from zoneinfo import ZoneInfo
import config

logger = logging.getLogger("SalidaHorario")

# Definir zonas horarias
ZONA_ARGENTINA = ZoneInfo(getattr(config, "TZ", "America/Argentina/Buenos_Aires"))
ZONA_CHILE = ZoneInfo("America/Santiago")

def _obtener_plantilla_activa():
    """
    Decide internamente qué plantilla usar comparando el offset de Chile y Argentina:
    - Misma hora -> PLANTILLA_HORARIO2
    - Chile 1 hora menos -> PLANTILLA_HORARIO
    """
    try:
        now_utc = datetime.now(ZoneInfo("UTC"))
        dt_arg = now_utc.astimezone(ZONA_ARGENTINA)
        dt_chile = now_utc.astimezone(ZONA_CHILE)
        
        diferencia_horas = (dt_arg.utcoffset() - dt_chile.utcoffset()).total_seconds() / 3600
        
        if diferencia_horas == 0:
            logger.info("Horario de Chile coincide con Argentina. Usando PLANTILLA_HORARIO2.")
            return getattr(config, "PLANTILLA_HORARIO2", None)
        else:
            logger.info("Horario de Chile es 1 hora menos que Argentina. Usando PLANTILLA_HORARIO.")
            return getattr(config, "PLANTILLA_HORARIO", None)
            
    except Exception as e:
        logger.error(f"Error al calcular la diferencia horaria: {e}")
        return getattr(config, "PLANTILLA_HORARIO", None)

async def ejecutar(bot_instance, datos_horario):
    """
    Función principal que ejecuta el módulo de salida horario.
    Selecciona la plantilla automáticamente y realiza el envío en Discord.
    """
    logger.info("⚙️ Ejecutando servicio de salida horario...")
    
    # 1. Obtener la plantilla de forma interna y automática
    plantilla = _obtener_plantilla_activa()
    
    if not plantilla:
        logger.error("❌ No se pudo determinar ninguna plantilla válida para salida_horario.")
        return

    try:
        # 2. Aquí armas tu lógica de envío a Discord usando los datos y la plantilla seleccionada
        # (canal_id = config.HORARIO o el ID correspondiente que tengas configurado)
        canal_id = getattr(config, "HORARIO", None)
        if not canal_id:
            logger.error("❌ No se encontró el ID del canal HORARIO en config.")
            return

        channel = bot_instance.get_channel(canal_id)
        if channel:
            # Ejemplo de envío (ajusta esto según cómo formatees tus mensajes con la plantilla):
            # mensaje_final = ...
            # await channel.send(mensaje_final)
            logger.info("✅ Mensaje de salida_horario enviado correctamente.")
        else:
            logger.warning(f"⚠️ No se pudo encontrar el canal de Discord con ID: {canal_id}")

    except Exception as e:
        logger.error(f"❌ Error al ejecutar salida_horario: {e}")
