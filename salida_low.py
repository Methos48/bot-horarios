import logging
from datetime import datetime
from zoneinfo import ZoneInfo
import os
import config
from PIL import Image, ImageDraw, ImageFont
import discord

logger = logging.getLogger("EntradaPagina")

# Definir la zona horaria estricta de Argentina
ZONA_ARGENTINA = ZoneInfo(getattr(config, "TZ", "America/Argentina/Buenos_Aires"))

# Variable global opcional para rastreo rápido
_mensaje_anterior_low_id = None


# ==========================================
# PROCESAMIENTO Y ORDENAMIENTO DE LA DATA
# ==========================================

def procesar_y_ordenar_datos(jefes_crudos):
    """
    Recibe la data cruda, la divide asegurando un máximo de 26 raids por columna
    (columna izquierda, columna del medio y columna derecha)
    y asegura el ordenamiento estricto: Vivos arriba, muertos ordenados cronológicamente.
    Retorna una tupla con (tabla_1, tabla_2, tabla_3).
    """
    if not jefes_crudos:
        logger.warning("salida_low: No se recibieron datos de jefes para procesar.")
        return [], [], []

    # Ordenar la lista completa (Vivos arriba, luego muertos cronológicamente)
    tabla_ordenada = _ordenar_tabla(jefes_crudos)

    # Dividir estrictamente con un máximo de 26 por columna (de arriba hacia abajo)
    tabla_1 = tabla_ordenada[:26]        # Columna Izquierda (máximo 26)
    tabla_2 = tabla_ordenada[26:52]      # Columna del Medio (máximo 26 siguientes)
    tabla_3 = tabla_ordenada[52:78]      # Columna Derecha (máximo 26 siguientes)

    logger.info(f"Datos procesados con éxito. Tabla 1: {len(tabla_1)} jefes | Tabla 2: {len(tabla_2)} jefes | Tabla 3: {len(tabla_3)} jefes")
    return tabla_1, tabla_2, tabla_3


def _ordenar_tabla(lista_jefes):
    """
    Ordena una lista de jefes bajo el huso horario estricto argentino:
    1. Primero los VIVOS arriba.
    2. Luego los MUERTOS ordenados de forma ascendente por fecha y hora.
    """
    vivos = [j for j in lista_jefes if str(j.get("estado", "")).upper() == "VIVO"]
    muertos = [j for j in lista_jefes if str(j.get("estado", "")).upper() != "VIVO"]
    
    def parsear_fecha(jefe):
        t_str = jefe.get("tiempo_str", "-")
        if not t_str or t_str == "-":
            return datetime.max.replace(tzinfo=ZONA_ARGENTINA)
        try:
            return datetime.strptime(t_str, "%d/%m/%Y %H:%M").replace(tzinfo=ZONA_ARGENTINA)
        except ValueError:
            return datetime.max.replace(tzinfo=ZONA_ARGENTINA)

    muertos_ordenados = sorted(muertos, key=parsear_fecha)
    return vivos + muertos_ordenados


# ==========================================
# GENERACIÓN DE IMAGEN CON FUENTES Y ESTILOS
# ==========================================

def generar_imagen_tabla_jefes(tabla_1, tabla_2, tabla_3, ruta_salida="estado_jefes_low.png"):
    """
    Genera una imagen organizando los jefes en tres columnas:
    - Máximo 26 raids por columna.
    - Fuentes: 17 para nombres, 16 para datos.
    - Margen superior ampliado (135) y columnas ajustadas para centrar LVL y Hora.
    """
    ancho_img = 1350  # Ancho ampliado para soportar 3 columnas
    alto_linea = 25
    margen_superior = 135  # Espacio superior para separar de la cabecera
    
    # Coordenadas X horizontales para cada una de las 3 columnas
    col_izq_x = 15
    col_cen_x = 465
    col_der_x = 915
    
    max_filas = max(len(tabla_1), len(tabla_2), len(tabla_3))
    alto_img = max(700, margen_superior + (max_filas + 2) * alto_linea)

    # Obtener la ruta de la plantilla desde config
    plantilla_path = getattr(config, "PLANTILLA_RONDALOW", "template_low.png")

    # Cargar plantilla base si existe o crear fondo claro
    if os.path.exists(plantilla_path):
        img = Image.open(plantilla_path).convert("RGB")
        if img.size != (ancho_img, alto_img):
            img = img.resize((ancho_img, alto_img))
    else:
        logger.warning(f"Plantilla '{plantilla_path}' no encontrada. Usando fondo por defecto.")
        img = Image.new("RGB", (ancho_img, alto_img), color=(245, 235, 215))
        
    draw = ImageDraw.Draw(img)

    # Cargar fuentes desde config con fallbacks seguros
    path_aptos = getattr(config, "FUENTE_APTOS", "Aptos Narrow.ttf")
    path_biome = getattr(config, "FUENTE_BIOME", "Biome.ttf")

    try:
        font_nombre = ImageFont.truetype(path_aptos, 17)
    except IOError:
        try:
            font_nombre = ImageFont.truetype("arial.ttf", 17)
        except IOError:
            font_nombre = ImageFont.load_default()

    try:
        font_datos = ImageFont.truetype(path_biome, 16)
    except IOError:
        try:
            font_datos = ImageFont.truetype("arial.ttf", 16)
        except IOError:
            font_datos = ImageFont.load_default()

    # Colores requeridos
    COLOR_NEGRO = (20, 20, 20)
    COLOR_VERDE = (0, 130, 0)

    # Función auxiliar para pintar una columna completa
    def dibujar_columna(lista_jefes, x_base):
        y = margen_superior
        for jefe in lista_jefes:
            nombre = jefe.get('nombre', '')
            nivel = str(jefe.get('nivel', '-'))
            if nivel == "" or nivel is None:
                nivel = "-"
                
            estado = str(jefe.get('estado', '')).upper()
            
            # Estado o Hora
            if estado == "VIVO":
                estado_hora = "VIVO"
            else:
                t_str = jefe.get('tiempo_str', '-')
                estado_hora = t_str.split(" ")[1] if " " in t_str else t_str

            # 1. Nombre del jefe en Negro
            draw.text((x_base, y), nombre, fill=COLOR_NEGRO, font=font_nombre)
            
            # 2. Nivel (LVL) desplazado a la derecha para centrarlo (+335 en lugar de +300)
            draw.text((x_base + 265, y), nivel, fill=COLOR_NEGRO, font=font_nombre)
            
            # 3. VIVO u Hora ajustado proporcionalmente (+385 en lugar de +360)
            draw.text((x_base + 355, y), estado_hora, fill=COLOR_VERDE, font=font_datos)
            
            y += alto_linea

    # Dibujar las 3 Columnas (Izquierda, Media y Derecha)
    if tabla_1:
        dibujar_columna(tabla_1, col_izq_x)
    if tabla_2:
        dibujar_columna(tabla_2, col_cen_x)
    if tabla_3:
        dibujar_columna(tabla_3, col_der_x)

    # Guardar imagen resultante
    img.save(ruta_salida)
    logger.info(f"🖼️ Imagen de jefes generada con éxito en 3 columnas (máx 26 c/u) usando plantilla '{plantilla_path}': {ruta_salida}")
    return ruta_salida


# ==========================================
# FUNCIÓN DE LLAMADA PRINCIPAL DESDE MAIN
# ==========================================

async def ejecutar(client_discord, data_recibida):
    """
    Función llamada desde main.py:
    Procesa la data, genera la imagen y la publica en config.LOW_CHANNEL_ID.
    """
    global _mensaje_anterior_low_id

    try:
        logger.info("⚙️ Ejecutando salida_low: Procesando data enviada por main, orden y 3 columnas...")
        
        # 1. Procesar y ordenar la data que mandó main en 3 tablas
        tabla_1, tabla_2, tabla_3 = procesar_y_ordenar_datos(data_recibida)
        
        if not tabla_1 and not tabla_2 and not tabla_3:
            logger.warning("salida_low: La data recibida está vacía o no se pudo procesar.")
            return None

        # 2. Generar la imagen visual utilizando las configuraciones de config.py
        ruta_imagen = generar_imagen_tabla_jefes(tabla_1, tabla_2, tabla_3, ruta_salida="estado_jefes_low.png")

        # 3. Obtener el ID del canal directamente desde config.LOW_CHANNEL_ID
        channel_id = getattr(config, "LOW_CHANNEL_ID", None)

        if client_discord and channel_id:
            try:
                canal = client_discord.get_channel(channel_id)
                if not canal:
                    canal = await client_discord.fetch_channel(channel_id)
                
                if canal:
                    # ==========================================================
                    # LIMPIEZA SEGURA: Borra cualquier mensaje previo del bot en el canal
                    # ==========================================================
                    try:
                        async for mensaje in canal.history(limit=10):
                            if mensaje.author == client_discord.user:
                                await mensaje.delete()
                                logger.info("🗑️ Mensaje anterior de salida_low eliminado con éxito.")
                    except Exception as e_del:
                        logger.warning(f"No se pudo limpiar el historial anterior de salida_low: {e_del}")

                    # Enviar la nueva imagen generada
                    nuevo_mensaje = await canal.send(file=discord.File(ruta_imagen))
                    _mensaje_anterior_low_id = nuevo_mensaje.id
                    logger.info("📤 Imagen de salida_low enviada y publicada con éxito en Discord (LOW_CHANNEL_ID).")
                else:
                    logger.error(f"salida_low: No se encontró el canal de Discord con ID {channel_id} (config.LOW_CHANNEL_ID)")
            except Exception as ex_discord:
                logger.error(f"Error al enviar/borrar la imagen de salida_low en Discord: {ex_discord}")
        else:
            logger.warning("⚠️ salida_low generada localmente, pero 'LOW_CHANNEL_ID' no está definido en config.py o falta el cliente de Discord.")

        return ruta_imagen

    except Exception as e:
        logger.error(f"Error en la ejecución de salida_low: {e}")
        return None
