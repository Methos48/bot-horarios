import os
import logging
import json
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
import discord
import config

logger = logging.getLogger("SalidaRaidPrueba")

ZONA_ARGENTINA = ZoneInfo(getattr(config, "TZ", "America/Argentina/Buenos_Aires"))

# --- IMPORTACIÓN DE NÚMEROS DESDE CONFIG ---
RECURSOS_NUMEROS = {
    "0": getattr(config, "NUMERO_0", None),
    "1": getattr(config, "NUMERO_1", None),
    "2": getattr(config, "NUMERO_2", None),
    "3": getattr(config, "NUMERO_3", None),
    "4": getattr(config, "NUMERO_4", None),
    "5": getattr(config, "NUMERO_5", None),
    "6": getattr(config, "NUMERO_6", None),
    "7": getattr(config, "NUMERO_7", None),
    "8": getattr(config, "NUMERO_8", None),
    "9": getattr(config, "NUMERO_9", None),
    ":": getattr(config, "NUMERO_DOS_PUNTOS", None)
}

def obtener_catalogo_imagenes_raid():
    directorio_base = getattr(config, "DIR_RAID", "imagen/raid")
    catalogo = {}
    if not os.path.exists(directorio_base):
        return catalogo
    for root, dirs, files in os.walk(directorio_base):
        for archivo in files:
            if archivo.lower().endswith(('.png', '.webp', '.jpg', '.jpeg')):
                ruta_completa = os.path.join(root, archivo)
                clave_relativa = os.path.relpath(ruta_completa, directorio_base).replace("\\", "/")
                catalogo[clave_relativa.lower()] = ruta_completa
                catalogo[archivo.lower()] = ruta_completa
    return catalogo

def obtener_imagen_raid(catalogo, nombre_base_raid):
    nombre_limpio = nombre_base_raid.strip().lower()
    rutas_candidatas = [
        f"raid/antes/{nombre_limpio}.png", 
        f"salio/{nombre_limpio}.png", 
        f"raid/{nombre_limpio}.png",
        f"{nombre_limpio}.png"
    ]

    for ruta in rutas_candidatas:
        for clave_cat in catalogo:
            if clave_cat.endswith(ruta.lower()) or clave_cat == ruta.lower():
                return catalogo[clave_cat]
                
    for clave, ruta_completa in catalogo.items():
        if nombre_limpio in clave:
            return ruta_completa
    return None

def estampar_hora_en_imagen(ruta_imagen_origen, hora_texto, ruta_imagen_destino):
    """
    Redimensiona los números a un tamaño más pequeño y los estampa 
    centrados horizontalmente en la parte inferior de la imagen.
    """
    try:
        from PIL import Image
        base_img = Image.open(ruta_imagen_origen).convert("RGBA")
        ancho_total_img, alto_total_img = base_img.size

        digitos_cargados = []
        ancho_bloque_total = 0
        espaciado = 4  # Espacio en píxeles entre cada número

        # FACTOR DE ESCALA: 0.4 significa que los números se reducirán al 40% de su tamaño original.
        # Si los quieres un poco más grandes o más chicos, puedes ajustar este valor (ej. 0.3 o 0.5).
        factor_escala = 0.2

        for char in hora_texto:
            ruta_digito = RECURSOS_NUMEROS.get(char)
            if ruta_digito and os.path.exists(ruta_digito):
                digito_img = Image.open(ruta_digito).convert("RGBA")
                
                # Redimensionamos proporcionalmente el dígito
                nuevo_ancho = int(digito_img.width * factor_escala)
                nuevo_alto = int(digito_img.height * factor_escala)
                digito_img = digito_img.resize((nuevo_ancho, nuevo_alto), Image.Resampling.LANCZOS)
                
                digitos_cargados.append(digito_img)
                ancho_bloque_total += nuevo_ancho
            else:
                digitos_cargados.append(None)
                ancho_bloque_total += 20

        if len(digitos_cargados) > 1:
            ancho_bloque_total += espaciado * (len(digitos_cargados) - 1)

        # Centrado horizontal automático con el nuevo ancho reducido
        pos_x = (ancho_total_img - ancho_bloque_total) // 2
        
        # Coordenada Y: Ajustada un poco más abajo para que encaje perfectamente en la franja negra
        pos_y = int(alto_total_img * 0.78)

        for digito_img in digitos_cargados:
            if digito_img:
                base_img.paste(digito_img, (pos_x, pos_y), digito_img)
                pos_x += digito_img.width + espaciado
            else:
                pos_x += 20 + espaciado

        base_img.save(ruta_imagen_destino, "PNG")
        return True
    except Exception as e:
        logger.error(f"❌ Error al estampar hora en la imagen: {e}")
        return False

# ==========================================
# SERVICIO DE PRUEBA INMEDIATA
# ==========================================
async def servicio_publicar_raids_salio(bot_instance, ruta_json, json_lock):
    await bot_instance.wait_until_ready()
    logger.info("🧪 [PRUEBA] El bot se ha conectado. Ejecutando envío inmediato de prueba para Antharas...")

    try:
        canal_id = 1551217678386208879
        canal = bot_instance.get_channel(canal_id)
        
        if not canal:
            try:
                canal = await bot_instance.fetch_channel(canal_id)
            except Exception as e:
                logger.error(f"❌ [PRUEBA] No se pudo obtener el canal con ID {canal_id}: {e}")
                return

        if canal:
            nombre_raid = "Antharas"
            sufijo = "4"
            
            nombre_archivo = f"{nombre_raid.lower()}{sufijo}.png"
            ruta_img = f"imagen/raid/raid/antes/{nombre_archivo}"

            if not os.path.exists(ruta_img):
                catalogo = obtener_catalogo_imagenes_raid()
                ruta_img = obtener_imagen_raid(catalogo, f"{nombre_raid}{sufijo}")

            if ruta_img and os.path.exists(ruta_img):
                ahora_arg = datetime.now(ZONA_ARGENTINA)
                hora_actual_24h = ahora_arg.strftime("%H:%M")
                
                ruta_temp_modificada = f"imagen/raid/raid/antes/{nombre_raid.lower()}_prueba_modificada.png"
                
                ruta_final_envio = ruta_img
                if estampar_hora_en_imagen(ruta_img, hora_actual_24h, ruta_temp_modificada):
                    ruta_final_envio = ruta_temp_modificada

                with open(ruta_final_envio, "rb") as binary:
                    await canal.send(
                        content=f"🧪 **[PRUEBA DE TAMAÑO]** Antharas publicado a las `{hora_actual_24h}`",
                        file=discord.File(binary, filename=f"raid_{nombre_raid.lower()}_salio_{sufijo}.png")
                    )
                logger.info(f"✅ [PRUEBA] Imagen de Antharas enviada con éxito al canal {canal_id} con la hora reducida.")
            else:
                logger.error("❌ [PRUEBA] No se encontró la imagen de Antharas.")
        else:
            logger.error(f"❌ [PRUEBA] El canal con ID {canal_id} no existe o el bot no tiene acceso.")

    except Exception as e:
        logger.error(f"❌ [PRUEBA] Error crítico ejecutando la prueba: {e}")

    while not bot_instance.is_closed():
        await asyncio.sleep(60)
