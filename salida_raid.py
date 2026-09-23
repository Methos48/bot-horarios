import os
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter
import discord
import config

logger = logging.getLogger("SalidaRaid")

ZONA_ARGENTINA = ZoneInfo(getattr(config, "TZ", "America/Argentina/Buenos_Aires"))

# ==========================================
# CONFIGURACIÓN DE TEMA / ESTILO VISUAL
# ==========================================
# Cambia esta variable libremente para usar los archivos de otra carpeta
# (Ej: "morado", "rojo", "navidad", etc.) dentro de imagen/raid/
TEMA_ACTIVO = "rojo"

# ==========================================
# POSICIÓN MANUAL DE LA HORA (Coordenadas X e Y)
# ==========================================
# Si dejas POS_X en None, se centrará automáticamente de forma horizontal.
# Si dejas POS_Y en None, se ubicará automáticamente abajo (alto_img - 145).
# Puedes colocar un número exacto de píxeles (ej: POS_X = 250, POS_Y = 1150) para moverlo libremente.
POS_X = 20
POS_Y = 565

# ==========================================
# FILTRO DE PUBLICACIÓN POR RAID ("si" o "no")
# ==========================================
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
    
    # Reglas generales para el resto de los raids
    "otros_60_mas": "no",  # "si" o "no" para los raids de nivel 60+
    "otros_60_menos": "no" # "si" o "no" para los raids de nivel 60-
}


def debe_publicar_raid(nombre_jefe, nivel_jefe=None):
    """
    Evalúa de forma independiente si un raid debe publicarse según el diccionario FILTRO_PUBLICAR_RAIDS.
    """
    if not nombre_jefe:
        return False
        
    nombre_limpio = nombre_jefe.strip()
    
    for raid_clave, estado in FILTRO_PUBLICAR_RAIDS.items():
        if raid_clave.lower() in ["otros_60_mas", "otros_60_menos"]:
            continue
        if raid_clave.lower() == nombre_limpio.lower():
            return estado.lower() == "si"
            
    if nivel_jefe is not None:
        try:
            if int(nivel_jefe) >= 60:
                return FILTRO_PUBLICAR_RAIDS.get("otros_60_mas", "si").lower() == "si"
            else:
                return FILTRO_PUBLICAR_RAIDS.get("otros_60_menos", "si").lower() == "si"
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


def obtener_imagen_raid(catalogo, nombre_base_raid, tema=TEMA_ACTIVO):
    """
    Busca la imagen del raid exclusivamente dentro de la subcarpeta 'raid' del tema activo.
    """
    for ext in ['.png', '.jpg', '.webp', '.jpeg']:
        clave_intento = f"{tema}/raid/{nombre_base_raid}{ext}"
        if clave_intento in catalogo:
            return catalogo[clave_intento]
            
    return None


async def ejecutar(bot_instance, datos_horario):
    """
    Función principal:
    - Recibe todas las listas de jefes globales.
    - Filtra por sí mismo qué jefes deben imprimirse según sus reglas internas.
    - Evita duplicados, procesa imágenes y las envía a Discord.
    """
    logger.info(f"⚙️ Ejecutando salida_raid (Tema activo: {TEMA_ACTIVO}). Analizando datos globales...")
    
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
        nombres_procesados = set() # Para evitar duplicados si un jefe aparece en varias listas

        for jefe in datos_horario:
            nombre_jefe = jefe.get("nombre", jefe.get("nombre_imagen", ""))
            nivel_jefe = jefe.get("nivel", None)
            
            # Evaluación propia del módulo para decidir si se publica
            if not debe_publicar_raid(nombre_jefe, nivel_jefe):
                continue
                
            # Limpieza robusta de nombre clave para evitar duplicados y buscar imagen
            nombre_crudo = nombre_jefe.strip()
            nombre_imagen_base = "".join(c for c in nombre_crudo if c.isalnum()).lower()
            
            if not nombre_imagen_base or nombre_imagen_base in nombres_procesados:
                continue
            nombres_procesados.add(nombre_imagen_base)
                
            registro = jefe.copy()
            estado = registro.get("estado", "").upper()
            tiempo_str = registro.get("tiempo_str", "-")
            
            es_vivo = (estado == "VIVO" or estado == "ALIVE" or registro.get("es_vivo", False))
            
            if es_vivo:
                registro["tiempo_str_final"] = "VIVO"
            elif tiempo_str and tiempo_str != "-":
                try:
                    dt_obj = datetime.strptime(tiempo_str, "%d/%m/%Y %H:%M").replace(tzinfo=ZONA_ARGENTINA)
                    registro["tiempo_str_final"] = dt_obj.strftime("%H:%M")
                except ValueError:
                    registro["tiempo_str_final"] = tiempo_str[-5:] if len(tiempo_str) >= 5 else tiempo_str
            else:
                registro["tiempo_str_final"] = "-"
                
            registro["nombre_imagen_base"] = nombre_imagen_base
            datos_procesados.append(registro)

        if not datos_procesados:
            logger.info("ℹ️ salida_raid no encontró ningún jefe activo permitido por sus filtros actuales para imprimir.")
            return

        # 3. CARGA DE FUENTE BANKGOTHIC (Tamaño aumentado a 140)
        try:
            font_hora = ImageFont.truetype(fuente_bankgothic, 150) if fuente_bankgothic else ImageFont.load_default()
        except Exception as font_err:
            logger.warning(f"⚠️ No se pudo cargar BankGothic, usando predeterminada: {font_err}")
            font_hora = ImageFont.load_default()

        # 4. PROCESAMIENTO DE IMAGEN, ESTAMPADO Y ENVÍO A DISCORD
        for jefe in datos_procesados:
            nombre_imagen_base = jefe.get("nombre_imagen_base")
            texto_hora = jefe.get("tiempo_str_final", "21:30")
            
            # Buscar la ruta de la imagen usando el tema activo y su subcarpeta raid
            ruta_imagen = obtener_imagen_raid(catalogo_raids, nombre_imagen_base, tema=TEMA_ACTIVO)
            
            if not ruta_imagen:
                logger.warning(f"⚠️ No se encontró la imagen para el raid: {nombre_imagen_base} en el tema '{TEMA_ACTIVO}'")
                continue
                
            # Abrir la plantilla con Pillow
            img = Image.open(ruta_imagen).convert("RGBA")
            ancho_img, alto_img = img.size
            
            draw_temp = ImageDraw.Draw(img)
            bbox = draw_temp.textbbox((0, 0), texto_hora, font=font_hora)
            ancho_texto = bbox[2] - bbox[0]
            
            # Coordenadas X e Y (manuales si se definen, automáticas si son None)
            x = POS_X if POS_X is not None else (ancho_img - ancho_texto) / 2
            y = POS_Y if POS_Y is not None else (alto_img - 145)
            
            # =========================================================
            # EFECTO METÁLICO CON BORDE Y RESPLANDOR ROJO INTENSO
            # =========================================================
            
            # 1. Capa para el resplandor (glow) y borde rojo exterior más grueso
            capa_resplandor = Image.new("RGBA", img.size, (0, 0, 0, 0))
            draw_resplandor = ImageDraw.Draw(capa_resplandor)
            
            # Dibujar trazo grueso rojo brillante para simular el neón/resplandor
            draw_resplandor.text(
                (x, y), 
                texto_hora, 
                font=font_hora, 
                fill=(0, 0, 0, 0),
                stroke_width=6, 
                stroke_fill=(255, 30, 30, 220)  # Rojo vivo e intenso
            )
            # Aplicar desenfoque para crear el efecto luminoso alrededor
            capa_resplandor = capa_resplandor.filter(ImageFilter.GaussianBlur(radius=3))

            # 2. Capa de sombra y definición del borde principal
            capa_texto = Image.new("RGBA", img.size, (0, 0, 0, 0))
            draw_capa = ImageDraw.Draw(capa_texto)
            
            desplazamiento_sombra = 4
            draw_capa.text(
                (x + desplazamiento_sombra, y + desplazamiento_sombra), 
                texto_hora, 
                font=font_hora, 
                fill=(0, 0, 0, 200)
            )
            
            # Borde interno más marcado y grueso (stroke_width=4)
            draw_capa.text(
                (x, y), 
                texto_hora, 
                font=font_hora, 
                fill=(255, 255, 255, 255), 
                stroke_width=4, 
                stroke_fill=(230, 0, 38, 255)  # Rojo carmesí profundo y sólido
            )
            
            # 3. Cargar la textura metálica desde config y ajustarla al tamaño de la imagen
            ruta_textura_metal = getattr(config, "TEXTURA_METAL", None)
            if ruta_textura_metal and os.path.exists(ruta_textura_metal):
                textura_metal = Image.open(ruta_textura_metal).convert("RGBA")
                textura_metal = textura_metal.resize((ancho_img, alto_img), Image.Resampling.LANCZOS)
            else:
                textura_metal = Image.new("RGBA", (ancho_img, alto_img), (140, 145, 150, 255))
            
            # 4. Máscara del texto interior puro (para rellenar con la textura metálica)
            capa_interior_pura = Image.new("RGBA", img.size, (0, 0, 0, 0))
            draw_interior_pura = ImageDraw.Draw(capa_interior_pura)
            draw_interior_pura.text((x, y), texto_hora, font=font_hora, fill=(255, 255, 255, 255))
            
            textura_recortada = Image.composite(textura_metal, Image.new("RGBA", img.size, (0, 0, 0, 0)), capa_interior_pura)
            
            # 5. Combinar capas sobre la imagen original en orden (Resplandor -> Sombra/Borde -> Textura metálica)
            img.alpha_composite(capa_resplandor)
            img.alpha_composite(capa_texto)
            img.alpha_composite(textura_recortada)
            
            # Guardar temporalmente la imagen procesada
            ruta_temporal = f"temp_{nombre_imagen_base}.png"
            img.convert("RGB").save(ruta_temporal, "PNG")
            
            # Envío de la imagen resultante a Discord
            archivo_discord = discord.File(ruta_temporal, filename=f"raid_{nombre_imagen_base}.png")
            await channel.send(file=archivo_discord)
            
            # Limpiar archivo temporal del disco
            if os.path.exists(ruta_temporal):
                os.remove(ruta_temporal)

        logger.info(f"✅ salida_raid procesó y envió {len(datos_procesados)} imágenes correctamente.")

    except Exception as e:
        logger.error(f"❌ Error crítico al ejecutar salida_raid: {e}")
