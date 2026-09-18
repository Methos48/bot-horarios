import logging
from datetime import datetime
from zoneinfo import ZoneInfo
import config

logger = logging.getLogger("SalidaHorario")

# Definir zonas horarias
ZONA_ARGENTINA = ZoneInfo(getattr(config, "TZ", "America/Argentina/Buenos_Aires"))
ZONA_CHILE = ZoneInfo("America/Santiago")

def obtener_plantilla_activa():
    """
    Compara en tiempo real la zona horaria de Argentina y Chile para decidir la plantilla:
    - Si coinciden (misma hora): usa PLANTILLA_HORARIO2.
    - Si Chile tiene 1 hora menos que Argentina: usa PLANTILLA_HORARIO.
    """
    try:
        now_utc = datetime.now(ZoneInfo("UTC"))
        dt_arg = now_utc.astimezone(ZONA_ARGENTINA)
        dt_chile = now_utc.astimezone(ZONA_CHILE)
        
        # Calcular la diferencia de offset en horas (Argentina - Chile)
        diferencia_horas = (dt_arg.utcoffset() - dt_chile.utcoffset()).total_seconds() / 3600
        
        if diferencia_horas == 0:
            logger.info("El horario de Chile coincide con el de Argentina. Seleccionando PLANTILLA_HORARIO2.")
            return getattr(config, "PLANTILLA_HORARIO2", None)
            
        elif diferencia_horas == 1:
            logger.info("El horario de Chile es 1 hora menos que el de Argentina. Seleccionando PLANTILLA_HORARIO.")
            return getattr(config, "PLANTILLA_HORARIO", None)
            
        else:
            logger.warning(f"Diferencia horaria inusual detectada ({diferencia_horas}h). Usando PLANTILLA_HORARIO por defecto.")
            return getattr(config, "PLANTILLA_HORARIO", None)
            
    except Exception as e:
        logger.error(f"Error al calcular la diferencia horaria entre Chile y Argentina: {e}")
        return getattr(config, "PLANTILLA_HORARIO", None)
