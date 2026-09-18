import logging
import os
from datetime import datetime
import discord
from PIL import Image, ImageDraw, ImageFont
import config

logger = logging.getLogger("SalidaHorario")

def ordenar_cronologicamente_nacimiento(datos_horario):
    """
    Ordena la lista recibida:
    1. Primero los jefes vivos ('Alive' o 'Vivo').
    2. Luego cronológicamente por la fecha y hora de nacimiento/aparición (más próximo arriba).
    """
    if not datos_horario:
        return []

    def clave_orden(item):
        tiempo_str = str(item.get("tiempo_str", "")).lower()
        es_vivo = "alive" in tiempo_str or "vivo" in tiempo_str
        
        # Si es vivo, va al tope (0). Si no, va después (1).
        # Luego ordenamos por el objeto datetime real para que el primero en nacer esté arriba.
        dt = item.get("datetime", datetime.max)
        if dt is None:
            dt = datetime.max
            
        return (0 if es_vivo else 1, dt)

    return sorted(datos_horario, key=clave_orden)

def generar_imagen_horario(datos_ordenados):
    """
    Dibuja los horarios sobre la plantilla configurada utilizando las fuentes y tablas de config.py.
    """
    # 1. Cargar plantilla (puedes alternar entre PLANTILLA_HORARIO y PLANTILLA_HORARIO2 según tu preferencia)
    ruta_plantilla = getattr(config, 'PLANTILLA_HORARIO', None)
    if not ruta_plantilla or not os.path.exists(ruta_plantilla):
        # Fallback a PLANTILLA_HORARIO2 si la primera no existe
        ruta_plantilla = getattr(config, 'PLANTILLA_HORARIO2', None)
        
    if not ruta_plantilla or not os.path.exists(ruta_plantilla):
        logger.error("❌ No se encontró ninguna plantilla de horario válida en config.py")
        return None

    img = Image.open(ruta_plantilla).convert("RGBA")
    draw = ImageDraw.Draw(img)

    # 2. Cargar fuentes configuradas
    fuente_aptos_path = getattr(config, 'FUENTE_APTOS', None)
    fuente_biome_path = getattr(config, 'FUENTE_BIOME', None)

    try:
        # Usamos Fuentes predeterminadas del sistema si las rutas de config fallan o no existen
        font_principal = ImageFont.truetype(fuente_aptos_path, 16) if fuente_aptos_path and os.path.exists(fuente_aptos_path) else ImageFont.load_default()
        font_secundaria = ImageFont.truetype(fuente_biome_path, 14) if fuente_biome_path and os.path.exists(fuente_biome_path) else ImageFont.load_default()
    except Exception as e:
        logger.warning(f"No se pudieron cargar las fuentes personalizadas, usando por defecto: {e}")
        font_principal = ImageFont.load_default()
        font_secundaria = ImageFont.load_default()

    # (Opcional) Puedes hacer uso de las tablas decorativas o de coordenadas aquí:
    # TABLA_BLOODED, TABLA_FLOATING, TABLA_PORTAL, TABLA_SCROLL según el diseño visual que requieras.

    # 3. Dibujar los datos ordenados sobre la imagen (ejemplo de renderizado base en coordenadas iniciales)
    # Ajusta X e Y según el diseño gráfico de tu plantilla
    x_inicio = 50
    y_inicio = 100
    espaciado_y = 25
    max_filas = 15  # Límite visual por imagen si es necesario

    for i, item in enumerate(datos_ordenados[:max_filas]):
        nombre = item.get("nombre", "Desconocido")
        tiempo = item.get("tiempo_str", "Sin horario")
        
        texto_linea = f"{nombre} - {tiempo}"
        
        # Color diferenciador si está vivo
        color_texto = (0, 255, 0) if ("alive" in tiempo.lower() or "vivo" in tiempo.lower()) else (255, 255, 255)
        
        draw.text((x_inicio, y_inicio + (i * espaciado_y)), texto_linea, fill=color_texto, font=font_principal)

    # Guardar temporalmente la imagen generada
    ruta_salida = "temp_horario.png"
    img.save(ruta_salida)
    return ruta_salida

async def ejecutar(bot_instance, datos_horario):
    """
    Función principal llamada desde main.py:
    - Ordena cronológicamente (vivos primero, luego por fecha/hora de nacimiento).
    - Genera la imagen usando los recursos de config.py.
    - La publica o edita en HORARIO_CHANNEL_ID.
    """
    channel_id = getattr(config, 'HORARIO_CHANNEL_ID', None)
    if not channel_id:
        logger.warning("⚠️ HORARIO_CHANNEL_ID no está configurado en config.py. Omitiendo salida_horario.")
        return

    channel = bot_instance.get_channel(channel_id)
    if not channel:
        try:
            channel = await bot_instance.fetch_channel(channel_id)
        except Exception as e:
            logger.error(f"No se pudo encontrar el canal con ID {channel_id} para salida_horario: {e}")
            return

    try:
        # 1. Ordenar datos: Vivos primero, luego por fecha/hora de nacimiento (nacen primero arriba)
        datos_ordenados = ordenar_cronologicamente_nacimiento(datos_horario)

        # 2. Generar la imagen con las fuentes y plantillas de config
        ruta_imagen = generar_imagen_horario(datos_ordenados)
        if not ruta_imagen or not os.path.exists(ruta_imagen):
            logger.error("Error al generar la imagen del horario.")
            return

        file_to_send = discord.File(ruta_imagen, filename="horarios.png")

        # 3. Buscar mensaje previo del bot en el canal para editarlo o enviar uno nuevo
        mensaje_existente = None
        async for msg in channel.history(limit=10):
            if msg.author == bot_instance.user and msg.attachments:
                mensaje_existente = msg
                break

        if mensaje_existente:
            # Editar mensaje existente con la nueva imagen
            await mensaje_existente.edit(attachments=[file_to_send], content=None)
            logger.info("🖼️ Imagen de salida_horario actualizada (editada) exitosamente en Discord.")
        else:
            # Enviar nuevo mensaje si no existía
            await channel.send(file=file_to_send)
            logger.info("📤 Nueva imagen de salida_horario enviada exitosamente a Discord.")

        # Limpiar archivo temporal local
        if os.path.exists(ruta_imagen):
            os.remove(ruta_imagen)

    except Exception as e:
        logger.error(f"Error al ejecutar salida_horario: {e}")
