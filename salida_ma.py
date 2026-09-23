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

def _cargar_fuente(tipo_fuente_attr, tamano=26):
    """
    Intenta cargar una fuente específica desde config, con fallbacks seguros.
    """
    fuente_path = getattr(config, tipo_fuente_attr, None)
    
    if fuente_path:
        try:
            return ImageFont.truetype(fuente_path, tamano)
        except Exception:
            pass
            
    # Fallback a Aptos o Biome genéricas si falla la específica
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
                
    logger.warning(f"⚠️ No se pudo cargar la fuente '{tipo_fuente_attr}'. Usando fuente por defecto.")
    return ImageFont.load_default()

async def ejecutar(bot_instance, datos_horario):
    """
    Función principal llamada desde main.py:
    - Borra el mensaje anterior del bot en el canal para mantenerlo limpio.
    - Procesa y extrae automáticamente Día, Fecha (dd/mm), Inicio, Armamos (-30 min) y Fin (+30 min).
    - Ordena los datos cronológicamente (por fecha y hora).
    - Dibuja los textos sobre PLANTILLA_MA aplicando fuentes y colores específicos.
    """
    logger.info("⚙️ Ejecutando salida_ma: Procesando, calculando tiempos y ordenando datos...")
    
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
        # ==========================================
        # 2. BORRAR EL MENSAJE ANTERIOR DEL BOT
        # ==========================================
        try:
            async for mensaje in channel.history(limit=20):
                if mensaje.author == bot_instance.user:
                    await mensaje.delete()
                    logger.info("🗑️ Mensaje anterior de salida_ma eliminado con éxito.")
                    break
        except Exception as err_del:
            logger.warning(f"⚠️ No se pudo eliminar el mensaje anterior en salida_ma (puede que no exista o falten permisos): {err_del}")

        # ==========================================
        # 3. PROCESAMIENTO Y EXTRACCIÓN DE DATOS
        # ==========================================
        dias_espanol = {
            0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 
            4: "Viernes", 5: "Sábado", 6: "Domingo"
        }

        datos_procesados = []
        for jefe in datos_horario:
            registro = jefe.copy()
            
            # Extraer nombre del raid
            nombre = registro.get("name", registro.get("nombre", "Desconocido"))
            
            # Obtener el objeto datetime base
            dt_obj = registro.get("datetime")
            if not dt_obj:
                raw_inicio = registro.get("inicio", registro.get("tiempo_str"))
                if raw_inicio and isinstance(raw_inicio, str):
                    try:
                        dt_obj = datetime.strptime(raw_inicio, "%d/%m/%Y %H:%M")
                    except ValueError:
                        pass

            # Si tenemos un objeto datetime válido, calculamos automáticamente todos los campos
            if dt_obj:
                if dt_obj.tzinfo is None:
                    dt_obj = dt_obj.replace(tzinfo=ZONA_ARGENTINA)
                
                registro["datetime"] = dt_obj
                
                # Extraer Día y Fecha en formato corto dd/mm
                dia = dias_espanol.get(dt_obj.weekday(), "-")
                fecha = dt_obj.strftime("%d/%m")  # Modificado a dd/mm
                inicio = dt_obj.strftime("%H:%M")
                
                # Armamos: Resta 30 minutos a la hora de inicio
                dt_armamos = dt_obj - timedelta(minutes=30)
                armamos = dt_armamos.strftime("%H:%M")
                
                # Fin: Suma 30 minutos a la hora de inicio
                dt_fin = dt_obj + timedelta(minutes=30)
                fin = dt_fin.strftime("%H:%M")
            else:
                # Valores por defecto si no hay un datetime válido
                dia = registro.get("dia", "-")
                fecha = registro.get("fecha", "-")
                armamos = registro.get("armamos", "-")
                inicio = registro.get("inicio", registro.get("tiempo_str", "-"))
                fin = registro.get("fin", "-")

            registro["nombre_final"] = nombre
            registro["dia_final"] = dia
            registro["fecha_final"] = fecha
            registro["armamos_final"] = armamos
            registro["inicio_final"] = inicio
            registro["fin_final"] = fin
            
            datos_procesados.append(registro)

        # 4. Ordenar los datos cronológicamente
        datos_ordenados = sorted(
            datos_procesados, 
            key=lambda x: x.get("datetime", datetime.max.replace(tzinfo=ZONA_ARGENTINA))
        )

        # 5. Cargar la plantilla base de imagen
        canvas = Image.open(ruta_plantilla).convert("RGBA")
        draw = ImageDraw.Draw(canvas)

        # Coordenadas X exactas para cada columna según el diseño de tu plantilla
        x_nombre = 30   # Columna RAID
        x_dia = 240     # Columna DÍA
        x_fecha = 420   # Columna FECHA
        x_armamos = 645 # Columna ARMAMOS (Rojo)
        x_inicio = 841  # Columna INICIO (Verde)
        x_fin = 974     # Columna FIN (Verde)

        y_cursor = 270       # Coordenada Y inicial exacta debajo de la cabecera
        espaciado_renglon = 50 # Espacio vertical entre cada fila de raids

        # Carga de fuentes 
        fuente_aptos = _cargar_fuente("FUENTE_APTOS", tamano=34)
        fuente_biome = _cargar_fuente("FUENTE_BIOME", tamano=32)
        
        # Colores personalizados acordes a tu diseño de referencia
        color_negro = _hex_a_rgb("#000000")
        color_rojo = _hex_a_rgb("#FF0000")
        color_verde = _hex_a_rgb("#008000")

        # 6. Rellenar la imagen con los datos ordenados en sus respectivas columnas y fuentes asignadas
        for jefe in datos_ordenados:
            nombre = jefe.get("nombre_final", "Desconocido")
            dia = jefe.get("dia_final", "-")
            fecha = jefe.get("fecha_final", "-")
            armamos = jefe.get("armamos_final", "-")
            inicio = jefe.get("inicio_final", "-")
            fin = jefe.get("fin_final", "-")
            
            # Dibujar columnas con negro y FUENTE_APTOS (Raid, Día, Fecha)
            draw.text((x_nombre, y_cursor), nombre, fill=color_negro, font=fuente_aptos)
            draw.text((x_dia, y_cursor), dia, fill=color_negro, font=fuente_aptos)
            draw.text((x_fecha, y_cursor), fecha, fill=color_negro, font=fuente_aptos)
            
            # Dibujar columnas con colores específicos y FUENTE_BIOME (Armamos, Inicio, Fin)
            draw.text((x_armamos, y_cursor), armamos, fill=color_rojo, font=fuente_biome)
            draw.text((x_inicio, y_cursor), inicio, fill=color_verde, font=fuente_biome)
            draw.text((x_fin, y_cursor), fin, fill=color_verde, font=fuente_biome)
            
            y_cursor += espaciado_renglon

        # 7. Guardar la imagen generada temporalmente
        nombre_archivo_salida = "ma_horario_final.png"
        canvas.save(nombre_archivo_salida)

        # 8. Enviar la imagen resultante al canal MA_CHANNEL_ID en Discord
        archivo_discord = discord.File(nombre_archivo_salida, filename="horario_ma.png")
        await channel.send(file=archivo_discord)
        
        logger.info("✅ Imagen de salida_ma generada y enviada correctamente a Discord.")

    except Exception as e:
        logger.error(f"❌ Error crítico al ejecutar salida_ma: {e}")
