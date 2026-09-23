import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont 
import discord
import config

logger = logging.getLogger("SalidaHorario")

# Definir zonas horarias
ZONA_ARGENTINA = ZoneInfo(getattr(config, "TZ", "America/Argentina/Buenos_Aires"))
ZONA_CHILE = ZoneInfo("America/Santiago")
ZONA_VENEZUELA = ZoneInfo("America/Caracas")
ZONA_ESPANA = ZoneInfo("Europe/Madrid")

def _hex_a_rgb(hex_str):
    """Convierte un color hexadecimal (#RRGGBB) a una tupla RGB para PIL."""
    hex_str = hex_str.lstrip('#')
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))

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
    
    if "blooded" in texto_lower or "baium" in texto_lower:
        return getattr(config, "TABLA_BLOODED", None)
    elif "floating" in texto_lower or "valakas" in texto_lower:
        return getattr(config, "TABLA_FLOATING", None)
    elif "portal" in texto_lower or "antharas" in texto_lower:
        return getattr(config, "TABLA_PORTAL", None)
    elif "scroll" in texto_lower or "frintezza" in texto_lower:
        return getattr(config, "TABLA_SCROLL", None)
        
    return None

def _obtener_nombre_item(texto_referencia):
    """Devuelve el texto descriptivo del ítem según el raid/texto."""
    if not texto_referencia:
        return None
    texto_lower = texto_referencia.lower()
    if "blooded" in texto_lower or "baium" in texto_lower:
        return "Blooded"
    elif "floating" in texto_lower or "valakas" in texto_lower:
        return "Floating"
    elif "portal" in texto_lower or "antharas" in texto_lower:
        return "Portal"
    elif "scroll" in texto_lower or "frintezza" in texto_lower:
        return "Scroll"
    return None

def _cargar_fuente_aptos():
    """Carga la fuente FUENTE_APTOS con tamaño 19."""
    fuente_path = getattr(config, "FUENTE_APTOS", None)
    if fuente_path:
        try:
            return ImageFont.truetype(fuente_path, 19)
        except Exception:
            pass
            
    logger.warning("⚠️ No se pudo cargar FUENTE_APTOS. Usando fuente por defecto.")
    return ImageFont.load_default()

def _cargar_fuente_biome():
    """Carga la fuente FUENTE_BIOME con tamaño 19."""
    fuente_path = getattr(config, "FUENTE_BIOME", None)
    if fuente_path:
        try:
            return ImageFont.truetype(fuente_path, 19)
        except Exception:
            pass
            
    logger.warning("⚠️ No se pudo cargar FUENTE_BIOME. Usando fuente por defecto.")
    return ImageFont.load_default()

async def ejecutar(bot_instance, datos_horario):
    """
    Función principal que ejecuta el módulo de salida horario.
    Borra el mensaje anterior del bot, procesa la fecha/hora para Argentina/Chile,
    Venezuela y España, aplica colores, separación de días y renderiza elementos e ítems.
    """
    logger.info("⚙️ Ejecutando servicio de salida horario (Generación de imagen)...")
    
    plantilla = _obtener_plantilla_activa()
    
    if not plantilla:
        logger.error("❌ No se pudo determinar ninguna plantilla válida para salida_horario.")
        return

    try:
        canal_id = getattr(config, "HORARIO_CHANNEL_ID", None)
        if not canal_id:
            logger.error("❌ No se encontró el ID del canal HORARIO_CHANNEL_ID en config.")
            return

        channel = bot_instance.get_channel(canal_id)
        if not channel:
            logger.warning(f"⚠️ No se pudo encontrar el canal de Discord con ID: {canal_id}")
            return

        # ==========================================
        # 2. BORRAR EL MENSAJE ANTERIOR DEL BOT
        # ==========================================
        try:
            async for mensaje in channel.history(limit=20):
                if mensaje.author == bot_instance.user:
                    await mensaje.delete()
                    logger.info("🗑️ Mensaje anterior de salida_horario eliminado con éxito.")
                    break
        except Exception as err_del:
            logger.warning(f"⚠️ No se pudo eliminar el mensaje anterior (puede que no exista o falten permisos): {err_del}")

        # ==========================================
        # 3. PROCESAMIENTO Y LIMPIEZA DE FECHA/HORA
        # ==========================================
        dias_espanol = {
            0: "lunes", 1: "martes", 2: "miércoles", 3: "jueves", 
            4: "viernes", 5: "sábado", 6: "domingo"
        }

        datos_procesados = []
        for jefe in datos_horario:
            registro = jefe.copy()
            estado = registro.get("estado", "").upper()
            tiempo_str = registro.get("tiempo_str", "-")
            
            es_vivo = (estado == "VIVO" or registro.get("es_vivo", False))
            
            nombre = registro.get("nombre", "")
            dia_str = "-"
            fecha_str = "-"
            hora_arg = "-"
            hora_ven = "-"
            hora_esp = "-"

            if es_vivo:
                hora_arg = "VIVO"
                hora_ven = "VIVO"
                hora_esp = "VIVO"
            elif tiempo_str and tiempo_str != "-":
                try:
                    dt_arg = datetime.strptime(tiempo_str, "%d/%m/%Y %H:%M").replace(tzinfo=ZONA_ARGENTINA)
                    
                    # Restar 30 minutos si el raid es Valakas, Antharas o Fafureon
                    if nombre.lower() in ["valakas", "antharas", "fafureon"]:
                        dt_arg -= timedelta(minutes=30)

                    dia_str = dias_espanol.get(dt_arg.weekday(), "-")
                    fecha_str = dt_arg.strftime("%d/%m")
                    hora_arg = dt_arg.strftime("%H:%M")

                    dt_ven = dt_arg.astimezone(ZONA_VENEZUELA)
                    dt_esp = dt_arg.astimezone(ZONA_ESPANA)

                    hora_ven = dt_ven.strftime("%H:%M")
                    hora_esp = dt_esp.strftime("%H:%M")

                except ValueError:
                    hora_arg = tiempo_str[-5:] if len(tiempo_str) >= 5 else tiempo_str
                    hora_ven = hora_arg
                    hora_esp = hora_arg

            registro["nombre_final"] = nombre
            registro["dia_final"] = dia_str
            registro["fecha_final"] = fecha_str
            registro["hora_arg"] = hora_arg
            registro["hora_ven"] = hora_ven
            registro["hora_esp"] = hora_esp
            
            datos_procesados.append(registro)

        # ==========================================
        # 4. LÓGICA DE CONSTRUCCIÓN DE LA IMAGEN
        # ==========================================
        canvas = Image.open(plantilla).convert("RGBA")
        draw = ImageDraw.Draw(canvas)

        fuente_aptos = _cargar_fuente_aptos()
        fuente_biome = _cargar_fuente_biome()
        
        color_negro = _hex_a_rgb("#000000")
        color_verde = _hex_a_rgb("#40A309") 
        color_rojo = _hex_a_rgb("#FF0000")
        color_azul_especial = _hex_a_rgb("#4D93D9")

        y_inicial = 165
        espaciado_base = 26
        
        x_nombre = 30
        x_dia = 140
        x_fecha = 255
        x_arg = 440
        x_ven = 555
        x_esp = 650

        # Agrupación y renderizado con separación de espacio dinámico solo entre los primeros elementos al cambiar de día
        dia_anterior = None
        y_cursor = y_inicial
        cambios_de_dia_contador = 0
        
        for index, jefe in enumerate(datos_procesados):
            nombre = jefe.get("nombre_final", "")
            dia = jefe.get("dia_final", "-")
            fecha = jefe.get("fecha_final", "-")
            h_arg = jefe.get("hora_arg", "-")
            h_ven = jefe.get("hora_ven", "-")
            h_esp = jefe.get("hora_esp", "-")

            # Aplicar separación solo si cambia de día y el contador es menor a 2 (primer y segundo cambio)
            if index > 0 and dia != dia_anterior:
                if cambios_de_dia_contador < 2:
                    y_cursor += 30
                    cambios_de_dia_contador += 1
            
            dia_anterior = dia

            # Determinar colores según el tipo de raid/evento
            nombre_lower = nombre.lower()
            es_rojo = nombre_lower in ["valakas", "antharas", "fafureon"]
            es_azul = nombre_lower in ["asedio", "p v p", "x 9", "foto mes"]

            if es_rojo:
                color_texto_fila = color_rojo
                color_hora_fila = color_rojo
            elif es_azul:
                color_texto_fila = color_azul_especial
                color_hora_fila = color_azul_especial
            else:
                color_texto_fila = color_negro
                color_hora_fila = color_verde

            # Dibujar campos de texto principales (con simulación de negrita por desplazamiento si es rojo o azul especial)
            draw.text((x_nombre, y_cursor), nombre, fill=color_texto_fila, font=fuente_aptos)
            if es_rojo or es_azul:
                draw.text((x_nombre + 1, y_cursor), nombre, fill=color_texto_fila, font=fuente_aptos)

            draw.text((x_dia, y_cursor), dia, fill=color_texto_fila, font=fuente_aptos)
            if es_rojo or es_azul:
                draw.text((x_dia + 1, y_cursor), dia, fill=color_texto_fila, font=fuente_aptos)

            draw.text((x_fecha, y_cursor), fecha, fill=color_texto_fila, font=fuente_aptos)
            if es_rojo or es_azul:
                draw.text((x_fecha + 1, y_cursor), fecha, fill=color_texto_fila, font=fuente_aptos)
            
            draw.text((x_arg, y_cursor), h_arg, fill=color_hora_fila, font=fuente_biome)
            if es_rojo or es_azul:
                draw.text((x_arg + 1, y_cursor), h_arg, fill=color_hora_fila, font=fuente_biome)

            draw.text((x_ven, y_cursor), h_ven, fill=color_hora_fila, font=fuente_biome)
            if es_rojo or es_azul:
                draw.text((x_ven + 1, y_cursor), h_ven, fill=color_hora_fila, font=fuente_biome)

            draw.text((x_esp, y_cursor), h_esp, fill=color_hora_fila, font=fuente_biome)
            if es_rojo or es_azul:
                draw.text((x_esp + 1, y_cursor), h_esp, fill=color_hora_fila, font=fuente_biome)

            # Estampar la imagen del ítem y su texto descriptivo al lado si corresponde
            ruta_img_item = _obtener_ruta_imagen_item(nombre)
            if ruta_img_item:
                try:
                    img_item = Image.open(ruta_img_item).convert("RGBA")
                    img_item.thumbnail((18, 18))
                    canvas.paste(img_item, (310, y_cursor + 2), img_item)
                    
                    nombre_item = _obtener_nombre_item(nombre)
                    if nombre_item:
                        draw.text((333, y_cursor), nombre_item, fill=color_texto_fila, font=fuente_aptos)
                        if es_rojo or es_azul:
                            draw.text((334, y_cursor), nombre_item, fill=color_texto_fila, font=fuente_aptos)
                except Exception as img_err:
                    logger.error(f"No se pudo cargar la imagen webp del ítem: {img_err}")

            y_cursor += espaciado_base

        # Guardar imagen generada temporalmente
        nombre_archivo_salida = "horario_generado.png"
        canvas.save(nombre_archivo_salida)

        # ==========================================
        # 5. ENVÍO DE LA IMAGEN RESULTANTE A DISCORD
        # ==========================================
        archivo_discord = discord.File(nombre_archivo_salida, filename="horario.png")
        await channel.send(file=archivo_discord)
        
        logger.info("✅ Imagen de salida_horario generada y enviada correctamente.")

    except Exception as e:
        logger.error(f"❌ Error al ejecutar salida_horario: {e}")
