import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont
import discord
import config

logger = logging.getLogger("SalidaMa")

# Definir zona horaria de referencia (Argentina)
ZONA_ARGENTINA = ZoneInfo(getattr(config, "TZ", "America/Argentina/Buenos_Aires"))

def _obtener_ruta_icono_item(texto_referencia):
    """
    Verifica el texto y retorna la ruta del archivo .webp correspondiente 
    definido en config.py (TABLA_BLOODED, TABLA_FLOATING, TABLA_PORTAL, TABLA_SCROLL).
    """
    if not texto_referencia:
        return None
    
    texto_lower = str(texto_referencia).lower()
    
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
    Función principal llamada desde main.py:
    - Ordena los datos cronológicamente (por fecha y hora).
    - Dibuja los textos e iconos sobre PLANTILLA_MA.
    - Envía la imagen final al canal MA_CHANNEL_ID.
    """
    logger.info("⚙️ Ejecutando salida_ma: Procesando y ordenando datos...")
    
    # 1. Obtener configuraciones clave desde config.py
    canal_id = getattr(config, "MA_CHANNEL_ID", None)
    ruta_plantilla = getattr(config, "PLANTILLA_MA", None)
    
    if not canal_id:
        logger.error("❌ No se encontró MA_CHANNEL_ID en config.")
        return
        
    if not ruta_plantilla:
        logger.error("❌ No se encontró PLANTILLA_MA en config.")
        return

    channel = bot_instance.get_channel(canal_id)
    if not channel:
        logger.warning(f"⚠️ No se pudo encontrar el canal de Discord con ID: {canal_id}")
        return

    try:
        # 2. Ordenar los datos cronológicamente (por fecha y hora, lo que nace antes va arriba)
        # Se usa la clave "datetime" generada en las entradas, con un valor máximo por defecto si no existe.
        datos_ordenados = sorted(
            datos_horario, 
            key=lambda x: x.get("datetime", datetime.max.replace(tzinfo=ZONA_ARGENTINA))
        )

        # 3. Cargar la plantilla base de imagen
        canvas = Image.open(ruta_plantilla).convert("RGBA")
        draw = ImageDraw.Draw(canvas)

        # ⚠️ AJUSTA ESTAS COORDENADAS SEGÚN EL DISEÑO DE TU PLANTILLA_MA
        x_nombre = 50
        x_fecha = 250
        x_icono = 350
        y_cursor = 150        # Coordenada Y donde empieza la primera línea de raids
        espaciado_renglon = 35 # Distancia vertical entre cada raid

        # Intentar cargar una fuente, de lo contrario usar la por defecto
        try:
            fuente = ImageFont.truetype("arial.ttf", 16)
        except IOError:
            fuente = ImageFont.load_default()

        # 4. Rellenar la imagen con los datos ordenados
        for jefe in datos_ordenados:
            nombre = jefe.get("nombre", "Desconocido")
            tiempo_str = jefe.get("tiempo_str", "-")
            
            # Dibujar nombre del Raid
            draw.text((x_nombre, y_cursor), nombre, fill="white", font=fuente)
            
            # Dibujar fecha y hora
            draw.text((x_fecha, y_cursor), tiempo_str, fill="white", font=fuente)
            
            # Buscar y estampar el icono .webp del ítem al lado si corresponde
            ruta_webp = _obtener_ruta_icono_item(tiempo_str)
            if not ruta_webp:
                ruta_webp = _obtener_ruta_icono_item(nombre) # Revisar también por si el ítem viene en el nombre

            if ruta_webp:
                try:
                    img_icono = Image.open(ruta_webp).convert("RGBA")
                    # Opcional: redimensionar si es necesario (ej: 24x24 píxeles)
                    img_icono = img_icono.resize((24, 24))
                    canvas.paste(img_icono, (x_icono, y_cursor - 2), img_icono)
                except Exception as img_err:
                    logger.error(f"No se pudo cargar el archivo webp del ítem: {img_err}")
            
            y_cursor += espaciado_renglon

        # 5. Guardar la imagen generada temporalmente
        nombre_archivo_salida = "ma_horario_final.png"
        canvas.save(nombre_archivo_salida)

        # 6. Enviar la imagen resultante al canal MA_CHANNEL_ID en Discord
        archivo_discord = discord.File(nombre_archivo_salida, filename="horario_ma.png")
        await channel.send(file=archivo_discord)
        
        logger.info("✅ Imagen de salida_ma generada y enviada correctamente a Discord.")

    except Exception as e:
        logger.error(f"❌ Error crítico al ejecutar salida_ma: {e}")
