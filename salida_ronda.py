import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont
import discord
import config

logger = logging.getLogger("SalidaRonda")

ZONA_ARGENTINA = ZoneInfo(getattr(config, "TZ", "America/Argentina/Buenos_Aires"))

def _es_jefe_especial(nombre):
    """
    Verifica si el jefe requiere la resta de 30 minutos (Valakas, Antharas, Fafurion).
    """
    if not nombre:
        return False
    n_lower = nombre.lower()
    return "valakas" in n_lower or "antharas" in n_lower or "fafurion" in n_lower

async def ejecutar(bot_instance, datos_horario):
    """
    Función principal llamada desde main.py:
    - Ajusta la hora de Valakas, Antharas y Fafurion (-30 minutos).
    - Ordena priorizando los Vivos y luego por fecha/hora de nacimiento.
    - Dibuja la información sobre PLANTILLA_RONDA y la envía a RONDA_CHANNEL_ID.
    """
    logger.info("⚙️ Ejecutando salida_ronda: Procesando datos y aplicando reglas especiales...")
    
    # 1. Obtener configuraciones clave desde config.py
    canal_id = getattr(config, "RONDA_CHANNEL_ID", None)
    ruta_plantilla = getattr(config, "PLANTILLA_RONDA", None)
    
    if not canal_id:
        logger.error("❌ No se encontró RONDA_CHANNEL_ID en config.")
        return
        
    if not ruta_plantilla:
        logger.error("❌ No se encontró PLANTILLA_RONDA en config.")
        return

    channel = bot_instance.get_channel(canal_id)
    if not channel:
        logger.warning(f"⚠️ No se pudo encontrar el canal de Discord con ID: {canal_id}")
        return

    try:
        datos_procesados = []

        # 2. Procesar y aplicar la regla de los -30 minutos a Valakas, Antharas y Fafurion
        for jefe in datos_horario:
            registro = jefe.copy()
            nombre = registro.get("nombre", "")
            dt_obj = registro.get("datetime")

            if _es_jefe_especial(nombre) and dt_obj and dt_obj != datetime.max.replace(tzinfo=dt_obj.tzinfo if dt_obj.tzinfo else ZONA_ARGENTINA):
                # Restar 30 minutos
                dt_ajustado = dt_obj - timedelta(minutes=30)
                registro["datetime"] = dt_ajustado
                registro["tiempo_str"] = dt_ajustado.strftime("%d/%m %H:%M")
                logger.info(f"⏰ Aplicado ajuste de -30 minutos a {nombre}")

            datos_procesados.append(registro)

        # 3. Ordenar: Primero los Vivos (es_vivo = True), luego por datetime cronológico
        datos_ordenados = sorted(
            datos_procesados,
            key=lambda x: (
                not x.get("es_vivo", False),  # False (True invertido) va antes que True -> Vivos arriba
                x.get("datetime", datetime.max.replace(tzinfo=ZONA_ARGENTINA))
            )
        )

        # 4. Cargar la plantilla base de imagen con Pillow
        canvas = Image.open(ruta_plantilla).convert("RGBA")
        draw = ImageDraw.Draw(canvas)

        # ⚠️ AJUSTA ESTAS COORDENADAS SEGÚN EL DISEÑO DE TU PLANTILLA_RONDA
        x_nombre = 50
        x_estado = 250
        x_fecha = 350
        y_cursor = 150        
        espaciado_renglon = 35 

        # Cargar fuentes configuradas o usar por defecto
        # (Puedes usar config.FUENTE_APTOS y config.FUENTE_BIOME para tamaños/tipos si lo deseas)
        try:
            fuente = ImageFont.truetype("arial.ttf", 16)
        except IOError:
            fuente = ImageFont.load_default()

        # 5. Rellenar la imagen con los datos ordenados
        for jefe in datos_ordenados:
            nombre = jefe.get("nombre", "Desconocido")
            tiempo_str = jefe.get("tiempo_str", "-")
            es_vivo = jefe.get("es_vivo", False)
            
            estado_str = "VIVO" if es_vivo else "Próximo"
            
            # Dibujar textos
            draw.text((x_nombre, y_cursor), nombre, fill="lime" if es_vivo else "white", font=fuente)
            draw.text((x_estado, y_cursor), estado_str, fill="yellow" if es_vivo else "gray", font=fuente)
            draw.text((x_fecha, y_cursor), tiempo_str, fill="white", font=fuente)
            
            y_cursor += espaciado_renglon

        # 6. Guardar y enviar imagen resultante a Discord
        nombre_archivo_salida = "ronda_horario_final.png"
        canvas.save(nombre_archivo_salida)

        archivo_discord = discord.File(nombre_archivo_salida, filename="horario_ronda.png")
        await channel.send(file=archivo_discord)
        
        logger.info("✅ Imagen de salida_ronda generada y enviada correctamente.")

    except Exception as e:
        logger.error(f"❌ Error crítico al ejecutar salida_ronda: {e}")
