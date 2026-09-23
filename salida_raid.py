import os
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter
import discord
import config

logger = logging.getLogger("SalidaRaid")

ZONA_ARGENTINA = ZoneInfo(getattr(config, "TZ", "America/Argentina/Buenos_Aires"))

# ==========================================
# CONFIGURACIÓN DE TEMA / ESTIVO VISUAL rojo, morado, navidad
# ==========================================
TEMA_ACTIVO = "rojo"

# ==========================================
# POSICIÓN MANUAL DE LA HORA (Coordenadas X e Y)
# ==========================================
POS_X = 20
POS_Y = 565

# ==========================================
# FILTROS DE PUBLICACIÓN POR RAID ("si" o "no")
# ==========================================
# 1. Filtro original / predeterminado
FILTRO_PUBLICAR_RAIDS = {
    "Valakas": "si",
    "Antharas": "si",
    "Fafureon": "si",
    "Balrog": "no",
    "Electrical": "no",
    "Baium": "no",
    "Zaken": "no",
    "Core": "no",
    "Orfen": "no",
    "Queen Ant": "no",
    "Frintezza": "no",
    "Freya": "no",
    "Zariche": "no",
    "Decarbia": "si",
    "Hekaton": "no",
    "Queen shyeed": "no",
    "Golkonda": "no",
    "Galaxia": "no",
    "Barakiel": "no",
    "otros_60_mas": "no",
    "otros_60_menos": "no"
}

# 2. Segundo filtro ("antes" - se evaluará con margen de 10 min previos)
FILTRO_PUBLICAR_RAIDS_ANTES = {
    "Valakas": "si",
    "Antharas": "si",
    "Fafureon": "si",
    "Balrog": "no",
    "Electrical": "no",
    "Baium": "no",
    "Zaken": "no",
    "Core": "no",
    "Orfen": "no",
    "Queen Ant": "no",
    "Frintezza": "no",
    "Freya": "no",
    "Zariche": "no",
    "Decarbia": "si",
    "Hekaton": "no",
    "Queen shyeed": "no",
    "Golkonda": "no",
    "Galaxia": "no",
    "Barakiel": "no",
    "otros_60_mas": "no",
    "otros_60_menos": "no"
}

# 3. Tercer filtro ("salio" - se evaluará cuando la hora ya llegó o pasó)
FILTRO_PUBLICAR_RAIDS_SALIO = {
    "Valakas": "si",
    "Antharas": "si",
    "Fafureon": "si",
    "Balrog": "no",
    "Electrical": "no",
    "Baium": "no",
    "Zaken": "no",
    "Core": "no",
    "Orfen": "no",
    "Queen Ant": "no",
    "Frintezza": "no",
    "Freya": "no",
    "Zariche": "no",
    "Decarbia": "si",
    "Hekaton": "no",
    "Queen shyeed": "no",
    "Golkonda": "no",
    "Galaxia": "no",
    "Barakiel": "no",
    "otros_60_mas": "no",
    "otros_60_menos": "no"
}


def debe_publicar_raid(nombre_jefe, nivel_jefe=None, filtro_usado=None):
    """
    Evalúa de forma independiente si un raid debe publicarse según el diccionario de filtros especificado.
    """
    if not nombre_jefe:
        return False
        
    nombre_limpio = nombre_jefe.strip()
    filtro = filtro_usado if filtro_usado is not None else FILTRO_PUBLICAR_RAIDS
    
    for raid_clave, estado in filtro.items():
        if raid_clave.lower() in ["otros_60_mas", "otros_60_menos"]:
            continue
        if raid_clave.lower() == nombre_limpio.lower():
            return estado.lower() == "si"
            
    if nivel_jefe is not None:
        try:
            if int(nivel_jefe) >= 60:
                return filtro.get("otros_60_mas", "si").lower() == "si"
            else:
                return filtro.get("otros_60_menos", "si").lower() == "si"
        except ValueError:
            pass
            
    return True


def obtener_catalogo_imagenes_raid():
    """
    Escanea recursivamente el directorio base 'imagen/raid' y todas las subcarpetas 
    para registrar todas las imágenes disponibles.
    """
    directorio_base = getattr(config, "DIR_RAID", "imagen/raid")
    catalogo = {}
    
    if not os.path.exists(directorio_base):
        logger.warning(f"⚠️ El directorio de raids '{directorio_base}' no existe o no es accesible.")
        return catalogo

    for root, dirs, files in os.walk(directorio_base):
        for archivo in files:
            if archivo.lower().endswith(('.png', '.webp', '.jpg', '.jpeg')):
                ruta_completa = os.path.join(root, archivo)
                clave_relativa = os.path.relpath(ruta_completa, directorio_base).replace("\\", "/")
                catalogo[clave_relativa] = ruta_completa
                
    return catalogo


def obtener_imagen_raid(catalogo, nombre_base_raid, tema=TEMA_ACTIVO, tipo_filtro="principal"):
    """
    Busca la imagen del raid en la subcarpeta correspondiente según el filtro:
    - 'antes' -> {tema}/raid/antes/{nombre}{ext}
    - 'salio' -> {tema}/raid/salio/{nombre}{ext}
    - 'principal' (o por defecto) -> {tema}/raid/{nombre}{ext}
    """
    subcarpeta_filtro = ""
    if tipo_filtro == "antes":
        subcarpeta_filtro = "antes/"
    elif tipo_filtro == "salio":
        subcarpeta_filtro = "salio/"

    for ext in ['.png', '.jpg', '.webp', '.jpeg']:
        # Intenta buscar en la subcarpeta específica del filtro
        clave_intento = f"{tema}/raid/{subcarpeta_filtro}{nombre_base_raid}{ext}"
        if clave_intento in catalogo:
            return catalogo[clave_intento]
            
    # Si no la encuentra en la subcarpeta específica, busca en la raíz del tema como respaldo
    if subcarpeta_filtro != "":
        for ext in ['.png', '.jpg', '.webp', '.jpeg']:
            clave_respaldo = f"{tema}/raid/{nombre_base_raid}{ext}"
            if clave_respaldo in catalogo:
                return catalogo[clave_respaldo]

    return None


async def ejecutar(bot_instance, datos_horario, tipo_filtro="principal"):
    """
    Función principal:
    - Recibe todas las listas de jefes globales.
    - Filtra qué jefes deben imprimirse según el tipo de filtro solicitado ('principal', 'antes', 'salio').
    - 'antes': Filtra los jefes a los que les faltan exactamente entre 0 y 10 minutos para salir.
    - 'salio': Filtra los jefes cuya hora ya llegó/pasó o están marcados como VIVOS.
    """
    if tipo_filtro == "antes":
        filtro_activo = FILTRO_PUBLICAR_RAIDS_ANTES
        nombre_filtro_log = "antes"
    elif tipo_filtro == "salio":
        filtro_activo = FILTRO_PUBLICAR_RAIDS_SALIO
        nombre_filtro_log = "salio"
    else:
        filtro_activo = FILTRO_PUBLICAR_RAIDS
        nombre_filtro_log = "principal"

    logger.info(f"⚙️ Ejecutando salida_raid [Filtro: {nombre_filtro_log}] (Tema activo: {TEMA_ACTIVO}). Analizando datos globales...")
    
    canal_id = getattr(config, "ENVIAR_MENSAJE_CHANNEL_ID", None)
    fuente_bankgothic = getattr(config, "FUENTE_BANKGOTHIC", None)
    
    if not canal_id:
        logger.error("❌ No se encontró un canal válido configurado para ENVIAR_MENSAJE_CHANNEL_ID en config.")
        return

    channel = bot_instance.get_channel(canal_id)
    if not channel:
        logger.warning(f"⚠️ No se pudo encontrar el canal de Discord con ID: {canal_id}")
        return

    try:
        # 1. CARGAR CATÁLOGO DE IMÁGENES
        catalogo_raids = obtener_catalogo_imagenes_raid()
        if not catalogo_raids:
            logger.warning("⚠️ El catálogo de imágenes de raid está vacío.")
            return

        # 2. FILTRAR Y LIMPIAR LA INFORMACIÓN RECIBIDA
        datos_procesados = []
        nombres_procesados = set()
        ahora_actual = datetime.now(ZONA_ARGENTINA)

        for jefe in datos_horario:
            nombre_jefe = jefe.get("nombre", jefe.get("nombre_imagen", ""))
            nivel_jefe = jefe.get("nivel", None)
            
            # Comprobación básica del filtro de configuración (si/no)
            if not debe_publicar_raid(nombre_jefe, nivel_jefe, filtro_usado=filtro_activo):
                continue
                
            nombre_crudo = nombre_jefe.strip()
            nombre_imagen_base = "".join(c for c in nombre_crudo if c.isalnum()).lower()
            
            if not nombre_imagen_base or nombre_imagen_base in nombres_procesados:
                continue
            nombres_procesados.add(nombre_imagen_base)
                
            registro = jefe.copy()
            estado = registro.get("estado", "").upper()
            tiempo_str = registro.get("tiempo_str", "-")
            
            es_vivo = (estado == "VIVO" or estado == "ALIVE" or registro.get("es_vivo", False))
            
            # Parseo de fecha/hora de respawn
            dt_obj = None
            if tiempo_str and tiempo_str != "-":
                try:
                    dt_obj = datetime.strptime(tiempo_str, "%d/%m/%Y %H:%M").replace(tzinfo=ZONA_ARGENTINA)
                except ValueError:
                    pass

            # APLICAR LÓGICA DE TIEMPO SEGÚN EL TIPO DE FILTRO
            if tipo_filtro == "antes":
                # Condición: Debe faltar entre 0 y 10 minutos para que salga (y que no esté ya vivo)
                if es_vivo or not dt_obj:
                    continue
                diferencia_minutos = (dt_obj - ahora_actual).total_seconds() / 60
                # Margen estricto: entre 0 y 10 minutos restantes
                if not (0 <= diferencia_minutos <= 10):
                    continue

            elif tipo_filtro == "salio":
                # Condición: O la fuente dice que está VIVO, o la hora de respawn ya llegó o pasó
                if not es_vivo:
                    if not dt_obj or dt_obj > ahora_actual:
                        continue
            
            # Definir texto final de hora/estado
            if es_vivo or tipo_filtro == "salio":
                registro["tiempo_str_final"] = "VIVO"
            elif dt_obj:
                registro["tiempo_str_final"] = dt_obj.strftime("%H:%M")
            else:
                registro["tiempo_str_final"] = tiempo_str[-5:] if len(tiempo_str) >= 5 else tiempo_str
                
            registro["nombre_imagen_base"] = nombre_imagen_base
            datos_procesados.append(registro)

        if not datos_procesados:
            logger.info(f"ℹ️ salida_raid [{nombre_filtro_log}] no encontró ningún jefe activo en el rango temporal actual para imprimir.")
            return

        # 3. CARGA DE FUENTE BANKGOTHIC
        try:
            font_hora = ImageFont.truetype(fuente_bankgothic, 150) if fuente_bankgothic else ImageFont.load_default()
        except Exception as font_err:
            logger.warning(f"⚠️ No se pudo cargar BankGothic, usando predeterminada: {font_err}")
            font_hora = ImageFont.load_default()

        # 4. PROCESAMIENTO DE IMAGEN, ESTAMPADO Y ENVÍO A DISCORD
        for jefe in datos_procesados:
            nombre_imagen_base = jefe.get("nombre_imagen_base")
            texto_hora = jefe.get("tiempo_str_final", "21:30")
            
            # Buscar imagen pasando el tipo de filtro actual para que elija la subcarpeta correcta
            ruta_imagen = obtener_imagen_raid(catalogo_raids, nombre_imagen_base, tema=TEMA_ACTIVO, tipo_filtro=tipo_filtro)
            
            if not ruta_imagen:
                logger.warning(f"⚠️ No se encontró la imagen para el raid: {nombre_imagen_base} en el tema '{TEMA_ACTIVO}' (Filtro: {tipo_filtro})")
                continue
                
            img = Image.open(ruta_imagen).convert("RGBA")
            ancho_img, alto_img = img.size
            
            draw_temp = ImageDraw.Draw(img)
            bbox = draw_temp.textbbox((0, 0), texto_hora, font=font_hora)
            ancho_texto = bbox[2] - bbox[0]
            
            x = POS_X if POS_X is not None else (ancho_img - ancho_texto) / 2
            y = POS_Y if POS_Y is not None else (alto_img - 145)
            
            # Capa resplandor
            capa_resplandor = Image.new("RGBA", img.size, (0, 0, 0, 0))
            draw_resplandor = ImageDraw.Draw(capa_resplandor)
            draw_resplandor.text(
                (x, y), texto_hora, font=font_hora, fill=(0, 0, 0, 0),
                stroke_width=6, stroke_fill=(255, 30, 30, 220)
            )
            capa_resplandor = capa_resplandor.filter(ImageFilter.GaussianBlur(radius=3))

            # Capa texto principal y sombra
            capa_texto = Image.new("RGBA", img.size, (0, 0, 0, 0))
            draw_capa = ImageDraw.Draw(capa_texto)
            desplazamiento_sombra = 4
            draw_capa.text((x + desplazamiento_sombra, y + desplazamiento_sombra), texto_hora, font=font_hora, fill=(0, 0, 0, 200))
            draw_capa.text(
                (x, y), texto_hora, font=font_hora, fill=(255, 255, 255, 255), 
                stroke_width=4, stroke_fill=(230, 0, 38, 255)
            )
            
            # Textura metálica
            ruta_textura_metal = getattr(config, "TEXTURA_METAL", None)
            if ruta_textura_metal and os.path.exists(ruta_textura_metal):
                textura_metal = Image.open(ruta_textura_metal).convert("RGBA")
                textura_metal = textura_metal.resize((ancho_img, alto_img), Image.Resampling.LANCZOS)
            else:
                textura_metal = Image.new("RGBA", (ancho_img, alto_img), (140, 145, 150, 255))
            
            capa_interior_pura = Image.new("RGBA", img.size, (0, 0, 0, 0))
            draw_interior_pura = ImageDraw.Draw(capa_interior_pura)
            draw_interior_pura.text((x, y), texto_hora, font=font_hora, fill=(255, 255, 255, 255))
            textura_recortada = Image.composite(textura_metal, Image.new("RGBA", img.size, (0, 0, 0, 0)), capa_interior_pura)
            
            img.alpha_composite(capa_resplandor)
            img.alpha_composite(capa_texto)
            img.alpha_composite(textura_recortada)
            
            ruta_temporal = f"temp_{nombre_imagen_base}_{nombre_filtro_log}.png"
            img.convert("RGB").save(ruta_temporal, "PNG")
            
            archivo_discord = discord.File(ruta_temporal, filename=f"raid_{nombre_imagen_base}.png")
            await channel.send(file=archivo_discord)
            
            if os.path.exists(ruta_temporal):
                os.remove(ruta_temporal)

        logger.info(f"✅ salida_raid [{nombre_filtro_log}] procesó y envió {len(datos_procesados)} imágenes correctamente.")

    except Exception as e:
        logger.error(f"❌ Error crítico al ejecutar salida_raid [{nombre_filtro_log}]: {e}")
