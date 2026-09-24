import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont 
import discord
import config

logger = logging.getLogger("SalidaMa")

# Definir zona horaria de referencia (Argentina)
ZONA_ARGENTINA = ZoneInfo(getattr(config, "TZ", "America/Argentina/Buenos_Aires"))

def _hex_a_rgb(hex_str):
    """Convierte un color hexadecimal (#RRGGBB) a una tupla RGB para PIL."""
    hex_str = hex_str.lstrip('#')
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))

def _obtener_ruta_icono_item(texto_referencia):
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

def _cargar_fuente(tipo_fuente_attr, tamano=26):
    fuente_path = getattr(config, tipo_fuente_attr, None)
    if fuente_path:
        try:
            return ImageFont.truetype(fuente_path, tamano)
        except Exception:
            pass
            
    fuentes_alternativas = [
        getattr(config, "FUENTE_APTOS", None),
        getattr(config, "FUENTE_BIOME", None),
        getattr(config, "FUENTE_BANKGOTHIC", None)
    ]
    for alt_path in fuentes_alternativas:
        if alt_path:
            try:
                return ImageFont.truetype(alt_path, tamano)
            except Exception:
                continue
    return ImageFont.load_default()

async def ejecutar(bot_instance, datos_horario):
    logger.info("⚙️ Ejecutando salida_ma: Procesando, calculando tiempos y ordenando datos...")
    
    canal_id = getattr(config, "MA_CHANNEL_ID", None)
    ruta_plantilla = getattr(config, "PLANTILLA_MA", None)
    
    if not canal_id or not ruta_plantilla:
        logger.error("❌ Faltan configuraciones de MA_CHANNEL_ID o PLANTILLA_MA en config.")
        return

    channel = bot_instance.get_channel(canal_id)
    if not channel:
        logger.warning(f"⚠️ No se pudo encontrar el canal con ID: {canal_id}")
        return

    try:
        # Borrar mensaje anterior del bot
        try:
            async for mensaje in channel.history(limit=20):
                if mensaje.author == bot_instance.user:
                    await mensaje.delete()
                    break
        except Exception as err_del:
            logger.warning(f"⚠️ No se pudo eliminar mensaje anterior: {err_del}")

        dias_espanol = {
            0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 
            4: "Viernes", 5: "Sábado", 6: "Domingo"
        }

        datos_procesados = []
        for jefe in datos_horario:
            registro = jefe.copy()
            nombre = registro.get("name", registro.get("nombre", "Desconocido"))
            
            dt_obj = registro.get("datetime")
            if not dt_obj:
                raw_inicio = registro.get("inicio", registro.get("tiempo_str"))
                if raw_inicio and isinstance(raw_inicio, str):
                    try:
                        dt_obj = datetime.strptime(raw_inicio, "%d/%m/%Y %H:%M")
                    except ValueError:
                        pass

            if dt_obj:
                if dt_obj.tzinfo is None:
                    dt_obj = dt_obj.replace(tzinfo=ZONA_ARGENTINA)
                registro["datetime"] = dt_obj
                
                dia = dias_espanol.get(dt_obj.weekday(), "-")
                fecha = dt_obj.strftime("%d/%m")
                inicio = dt_obj.strftime("%H:%M")
                armamos = (dt_obj - timedelta(minutes=30)).strftime("%H:%M")
                fin = (dt_obj + timedelta(minutes=30)).strftime("%H:%M")
            else:
                dia = registro.get("dia", "-")
                fecha = registro.get("fecha", "-")
                armamos = registro.get("armamos", "-")
                inicio = registro.get("inicio", registro.get("tiempo_str", "-"))
                fin = registro.get("fin", "-")

            registro.update({
                "nombre_final": nombre,
                "dia_final": dia,
                "fecha_final": fecha,
                "armamos_final": armamos,
                "inicio_final": inicio,
                "fin_final": fin
            })
            datos_procesados.append(registro)

        datos_ordenados = sorted(
            datos_procesados, 
            key=lambda x: x.get("datetime", datetime.max.replace(tzinfo=ZONA_ARGENTINA))
        )

        canvas = Image.open(ruta_plantilla).convert("RGBA")
        draw = ImageDraw.Draw(canvas)

        # ======================================================================
        # 📐 COORDENADAS X RECALIBRADAS SEGÚN LA IMAGEN DE TU PLANTILLA
        # ======================================================================
        x_nombre = 30   # Raid
        x_dia = 230     # Día
        x_fecha = 400   # Fecha
        x_armamos = 590 # Armamos (Alineado con el texto rojo)
        x_inicio = 760  # Inicio (Alineado con el título verde de la plantilla)
        x_fin = 890     # Fin (Movido hacia la izquierda para que no se corte)

        y_cursor = 240
        espaciado_renglon = 50

        fuente_aptos = _cargar_fuente("FUENTE_APTOS", tamano=34)
        fuente_biome = _cargar_fuente("FUENTE_BIOME", tamano=32)
        
        color_negro = _hex_a_rgb("#000000")
        color_rojo = _hex_a_rgb("#FF0000")
        color_verde = _hex_a_rgb("#008000")

        for jefe in datos_ordenados:
            draw.text((x_nombre, y_cursor), jefe["nombre_final"], fill=color_negro, font=fuente_aptos)
            draw.text((x_dia, y_cursor), jefe["dia_final"], fill=color_negro, font=fuente_aptos)
            draw.text((x_fecha, y_cursor), jefe["fecha_final"], fill=color_negro, font=fuente_aptos)
            
            draw.text((x_armamos, y_cursor), jefe["armamos_final"], fill=color_rojo, font=fuente_biome)
            draw.text((x_inicio, y_cursor), jefe["inicio_final"], fill=color_verde, font=fuente_biome)
            draw.text((x_fin, y_cursor), jefe["fin_final"], fill=color_verde, font=fuente_biome)
            
            y_cursor += espaciado_renglon

        nombre_archivo_salida = "ma_horario_final.png"
        canvas.save(nombre_archivo_salida)

        archivo_discord = discord.File(nombre_archivo_salida, filename="horario_ma.png")
        await channel.send(file=archivo_discord)
        logger.info("✅ Imagen de salida_ma generada y enviada correctamente.")

    except Exception as e:
        logger.error(f"❌ Error crítico al ejecutar salida_ma: {e}")
