import logging
import discord
import config

logger = logging.getLogger("SalidaHorario")

async def ejecutar(bot_instance, datos_horario):
    """
    Recibe la lista filtrada para el horario principal y actualiza (o crea) 
    un mensaje persistente en el canal de Discord configurado.
    """
    # Validar que el canal esté configurado en config.py
    channel_id = getattr(config, 'SALIDA_HORARIO_CHANNEL_ID', None)
    if not channel_id:
        logger.warning("⚠️ SALIDA_HORARIO_CHANNEL_ID no está configurado en config.py. Omitiendo salida.")
        return

    channel = bot_instance.get_channel(channel_id)
    if not channel:
        try:
            channel = await bot_instance.fetch_channel(channel_id)
        except Exception as e:
            logger.error(f"No se pudo encontrar el canal con ID {channel_id} para salida_horario: {e}")
            return

    try:
        # Construir el texto o embed que se enviará a Discord
        mensaje_formateado = construir_mensaje(datos_horario)

        # Buscar en el historial reciente del canal si el bot ya envió un mensaje antes (para editarlo)
        mensaje_existente = None
        async for msg in channel.history(limit=20):
            if msg.author == bot_instance.user:
                mensaje_existente = msg
                break

        if mensaje_existente:
            # Si ya existe un mensaje del bot, lo editamos para mantener el canal limpio
            await mensaje_existente.edit(content=mensaje_formateado)
            logger.info("✏️ Mensaje de salida_horario actualizado exitosamente.")
        else:
            # Si no hay mensajes previos, enviamos uno nuevo
            await channel.send(mensaje_formateado)
            logger.info("📤 Nuevo mensaje de salida_horario enviado exitosamente.")

    except Exception as e:
        logger.error(f"Error al ejecutar salida_horario: {e}")

def construir_mensaje(datos_horario):
    """
    Construye el formato de texto organizado para los jefes y eventos de salida_horario.
    Puedes personalizar el diseño a tu gusto (Markdown de Discord).
    """
    if not datos_horario:
        return "📜 **HORARIOS - PRINCIPAL**\n\n*No hay jefes ni eventos activos o registrados en este momento.*"

    lineas = [
        "╔══════════════════════════════════╗",
        "║     ⚔️ **HORARIOS DE JEFES & EVENTOS** ⚔️    ║",
        "╚══════════════════════════════════╝\n"
    ]

    for item in datos_horario:
        nombre = item.get("nombre", "Desconocido")
        tiempo = item.get("tiempo_str", "Sin horario")
        
        # Destacar visualmente si está vivo
        tiempo_lower = tiempo.lower()
        if "alive" in tiempo_lower or "vivo" in tiempo_lower:
            lineas.append(f"🟢 **{nombre}** ➔ **¡VIVO / ALIVE!**")
        else:
            lineas.append(f"⏱️ **{nombre}** ➔ `{tiempo}`")

    lineas.append("\n_🔄 Actualizado automáticamente en tiempo real._")
    return "\n".join(lineas)
