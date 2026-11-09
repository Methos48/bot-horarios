# ============================================================
# ACTIVAR / DESACTIVAR SERVIDORES
# Pon "si" para publicar en ese servidor o "no" para desactivarlo.
# ============================================================
PUBLICAR_SERVIDOR_1 = "si"
PUBLICAR_SERVIDOR_2 = "si"
PUBLICAR_SERVIDOR_3 = "si"

import logging
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
import os
import config
from PIL import Image, ImageDraw, ImageFont
import discord

logger = logging.getLogger("EntradaPagina")
ZONA_ARGENTINA = ZoneInfo(getattr(config, "TZ", "America/Argentina/Buenos_Aires"))
_mensaje_anterior_low_id = None

def procesar_y_ordenar_datos(jefes_crudos):
    if not jefes_crudos:
        logger.warning("salida_low: No se recibieron datos de jefes para procesar.")
        return [], [], []
    tabla_ordenada = _ordenar_tabla(jefes_crudos)
    tabla_1, tabla_2, tabla_3 = tabla_ordenada[:26], tabla_ordenada[26:52], tabla_ordenada[52:78]
    logger.info(f"Datos procesados con éxito. Tabla 1: {len(tabla_1)} jefes | Tabla 2: {len(tabla_2)} jefes | Tabla 3: {len(tabla_3)} jefes")
    return tabla_1, tabla_2, tabla_3

def _ordenar_tabla(lista_jefes):
    vivos = [j for j in lista_jefes if str(j.get("estado", "")).upper() == "VIVO"]
    muertos = [j for j in lista_jefes if str(j.get("estado", "")).upper() != "VIVO"]
    def parsear_fecha(jefe):
        t_str = jefe.get("tiempo_str", "-")
        if not t_str or t_str == "-": return datetime.max.replace(tzinfo=ZONA_ARGENTINA)
        try: return datetime.strptime(t_str, "%d/%m/%Y %H:%M").replace(tzinfo=ZONA_ARGENTINA)
        except ValueError: return datetime.max.replace(tzinfo=ZONA_ARGENTINA)
    return vivos + sorted(muertos, key=parsear_fecha)

def generar_imagen_tabla_jefes(tabla_1, tabla_2, tabla_3, ruta_salida="estado_jefes_low.png"):
    ancho_img, alto_linea, margen_superior = 1350, 25, 135
    col_izq_x, col_cen_x, col_der_x = 15, 465, 915
    max_filas = max(len(tabla_1), len(tabla_2), len(tabla_3))
    alto_img = max(700, margen_superior + (max_filas + 2) * alto_linea)
    plantilla_path = getattr(config, "PLANTILLA_RONDALOW", "template_low.png")
    if os.path.exists(plantilla_path):
        img = Image.open(plantilla_path).convert("RGB")
        if img.size != (ancho_img, alto_img): img = img.resize((ancho_img, alto_img))
    else:
        logger.warning(f"Plantilla '{plantilla_path}' no encontrada. Usando fondo por defecto.")
        img = Image.new("RGB", (ancho_img, alto_img), color=(245, 235, 215))
    draw = ImageDraw.Draw(img)
    path_aptos = getattr(config, "FUENTE_APTOS", "Aptos Narrow.ttf")
    path_biome = getattr(config, "FUENTE_BIOME", "Biome.ttf")
    try: font_nombre = ImageFont.truetype(path_aptos, 17)
    except IOError:
        try: font_nombre = ImageFont.truetype("arial.ttf", 17)
        except IOError: font_nombre = ImageFont.load_default()
    try: font_datos = ImageFont.truetype(path_biome, 16)
    except IOError:
        try: font_datos = ImageFont.truetype("arial.ttf", 16)
        except IOError: font_datos = ImageFont.load_default()
    COLOR_NEGRO, COLOR_VERDE = (20,20,20), (0,130,0)
    def dibujar_columna(lista_jefes, x_base):
        y = margen_superior
        for jefe in lista_jefes:
            nombre = jefe.get('nombre', '')
            nivel = str(jefe.get('nivel', '-'))
            if nivel == "" or nivel is None: nivel = "-"
            estado = str(jefe.get('estado', '')).upper()
            if estado == "VIVO": estado_hora = "VIVO"
            else:
                t_str = jefe.get('tiempo_str', '-')
                estado_hora = t_str.split(" ")[1] if " " in t_str else t_str
            draw.text((x_base, y), nombre, fill=COLOR_NEGRO, font=font_nombre)
            draw.text((x_base + 265, y), nivel, fill=COLOR_NEGRO, font=font_nombre)
            draw.text((x_base + 355, y), estado_hora, fill=COLOR_VERDE, font=font_datos)
            y += alto_linea
    if tabla_1: dibujar_columna(tabla_1, col_izq_x)
    if tabla_2: dibujar_columna(tabla_2, col_cen_x)
    if tabla_3: dibujar_columna(tabla_3, col_der_x)
    img.save(ruta_salida)
    logger.info(f"🖼️ Imagen de jefes generada con éxito en 3 columnas (máx 26 c/u) usando plantilla '{plantilla_path}': {ruta_salida}")
    return ruta_salida

async def ejecutar(client_discord, data_recibida):
    global _mensaje_anterior_low_id
    try:
        logger.info("⚙️ Ejecutando salida_low: Procesando data enviada por main, orden y 3 columnas...")
        tabla_1, tabla_2, tabla_3 = procesar_y_ordenar_datos(data_recibida)
        if not tabla_1 and not tabla_2 and not tabla_3:
            logger.warning("salida_low: La data recibida está vacía o no se pudo procesar.")
            return None
        ruta_imagen = generar_imagen_tabla_jefes(tabla_1, tabla_2, tabla_3, ruta_salida="estado_jefes_low.png")
        channel_ids = []
        if PUBLICAR_SERVIDOR_1 == "si" and getattr(config, "LOW_CHANNEL_ID", None):
            channel_ids.append(int(config.LOW_CHANNEL_ID))
        if PUBLICAR_SERVIDOR_2 == "si":
            channel_ids.append(1556550711062564935)
        if PUBLICAR_SERVIDOR_3 == "si":
            channel_ids.append(1556552533927796767)
        async def publicar_en_canal(channel_id):
            try:
                canal = client_discord.get_channel(channel_id) or await client_discord.fetch_channel(channel_id)
                if not canal:
                    logger.error("salida_low: No se encontró el canal %s.", channel_id)
                    return
                try:
                    async for mensaje in canal.history(limit=10):
                        if mensaje.author == client_discord.user:
                            await mensaje.delete()
                            break
                except Exception as e_del:
                    logger.warning("No se pudo limpiar salida_low en %s: %s", channel_id, e_del)
                await canal.send(file=discord.File(ruta_imagen))
                logger.info("📤 salida_low enviada al canal %s.", channel_id)
            except Exception as ex:
                logger.error("Error al enviar/borrar salida_low en %s: %s", channel_id, ex)
        if client_discord and channel_ids:
            await asyncio.gather(*(publicar_en_canal(cid) for cid in channel_ids))
        else:
            logger.warning("⚠️ salida_low generada localmente, pero no hay destinos configurados.")
        return ruta_imagen
    except Exception as e:
        logger.error(f"Error en la ejecución de salida_low: {e}")
        return None
