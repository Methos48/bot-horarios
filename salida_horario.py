import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont  # Asegúrate de tener PIL para el manejo de imágenes
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

def _obtener_ruta_imagen_item(texto_referencia):
    """
    Verifica el texto de referencia y devuelve la ruta del archivo .webp 
    configurado en config.py para Blooded, Floating, Portal o Scroll.
    """
    if not texto_referencia:
        return None
    
    texto_lower = texto_referencia.lower()
    
    if "blooded" in texto_lower:
        return getattr(config, "TABLA_BLOODED", None)
    elif "floating" in texto_lower:
        return getattr(config, "TABLA_FLOATING", None)
    elif "portal" in texto_lower:
        return getattr(config, "TABLA_PORTAL", None)
    elif "scroll" in texto_lower:
        return getattr(config, "TABLA_SCROLL", None)
        
    return None

async def ejecutar(bot_instance, datos_horario):
    """
    Función principal que ejecuta el módulo de salida horario.
    Selecciona la plantilla, genera la imagen combinada con los ítems y realiza el envío en Discord.
    """
    logger.info("⚙️ Ejecutando servicio de salida horario (Generación de imagen)...")
    
    # 1. Obtener la plantilla de forma interna y automática
    plantilla = _obtener_plantilla_activa()
    
    if not plantilla:
        logger.error("❌ No se pudo determinar ninguna plantilla válida para salida_horario.")
        return

    try:
        canal_id = getattr(config, "HORARIO", None)
        if not canal_id:
            logger.error("❌ No se encontró el ID del canal HORARIO en config.")
            return

        channel = bot_instance.get_channel(canal_id)
        if not channel:
            logger.warning(f"⚠️ No se pudo encontrar el canal de Discord con ID: {canal_id}")
            return

        # ==========================================
        # 2. LÓGICA DE CONSTRUCCIÓN DE LA IMAGEN
        # ==========================================
        # Aquí es donde abres tu imagen base (la plantilla o fondo) y dibujas los datos.
        # Ejemplo conceptual usando Pillow:
        # 
        # canvas = Image.open(plantilla).convert("RGBA")
        # draw = ImageDraw.Draw(canvas)
        # 
        # y_offset = posicion_inicial_y
        # for jefe in datos_horario:
        #     nombre = jefe.get("nombre", "")
        #     item_texto = jefe.get("item", "") # o de donde saques la referencia
        #     
        #     # Dibujar texto del jefe...
        #     
        #     # Obtener y estampar la imagen del ítem al lado si corresponde
        #     ruta_img_item = _obtener_ruta_imagen_item(item_texto)
        #     if ruta_img_item:
        #         try:
        #             img_item = Image.open(ruta_img_item).convert("RGBA")
        #             # Redimensionar si es necesario para que encaje al lado del texto:
        #             # img_item = img_item.resize((ancho, alto))
        #             
        #             # Pegar en la coordenada X, Y al lado del texto
        #             # canvas.paste(img_item, (pos_x, pos_y), img_item)
        #         except Exception as img_err:
        #             logger.error(f"No se pudo cargar la imagen webp del ítem: {img_err}")
        #     
        #     y_offset += espaciado_renglon
        # 
        # canvas.save("horario_generado.png")
        # 
        # ==========================================

        # 3. Envío de la imagen resultante a Discord
        # archivo_discord = discord.File("horario_generado.png", filename="horario.png")
        # await channel.send(file=archivo_discord)
        
        logger.info("✅ Imagen de salida_horario generada y enviada correctamente.")

    except Exception as e:
        logger.error(f"❌ Error al ejecutar salida_horario: {e}")
