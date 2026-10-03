import os
import logging
import json
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
import discord
import config

logger = logging.getLogger("SalidaRaid")

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
    Estampa la hora con el tamaño y posición exactos probados y calibrados.
    """
    try:
        from PIL import Image
        base_img = Image.open(ruta_imagen_origen).convert("RGBA")
        ancho_total_img, alto_total_img = base_img.size

        digitos_cargados = []
        ancho_bloque_total = 0
        espaciado = 4  # Espacio en píxeles entre cada número

        # Configuración exacta validada
        factor_escala = 0.15

        for char in hora_texto:
            ruta_digito = RECURSOS_NUMEROS.get(char)
            if ruta_digito and os.path.exists(ruta_digito):
                digito_img = Image.open(ruta_digito).convert("RGBA")
                
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

        # Centrado horizontal automático
        pos_x = (ancho_total_img - ancho_bloque_total) // 2
        
        # Posición vertical exacta validada
        pos_y = int(alto_total_img * 0.83)

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
# SERVICIO PRINCIPAL DE PUBLICACIÓN DE RAIDS
# ==========================================
async def servicio_publicar_raids_salio(bot_instance, ruta_json, json_lock):
    await bot_instance.wait_until_ready()
    logger.info("🚀 Servicio de publicación de raids iniciado correctamente.")

    while not bot_instance.is_closed():
        try:
            # Aquí va la lógica normal de lectura de tu archivo JSON de raids
            if os.path.exists(ruta_json):
                async with json_lock:
                    with open(ruta_json, "r", encoding="utf-8") as f:
                        data = json.load(f)
                
                # --- EJEMPLO DE USO INTEGRADO PARA ANTHARAS/VALAKAS CON SUFIJO 4 ---
                # Cada vez que detectes que un raid como Antharas o Valakas con sufijo 4 sale:
                # (Asegúrate de adaptar esta parte a la estructura de tu bucle de raids actual)
                
                # Ejemplo de validación para el envío:
                # nombre_raid = raid.get("nombre")  # ej: "Antharas" o "Valakas"
                # sufijo = raid.get("sufijo", "")    # ej: "4"
                # canal_id = raid.get("canal_id")
                
                # Si el nombre es Antharas o Valakas y su sufijo/identificador termina en 4:
                # if nombre_raid.lower() in ["antharas", "valakas"] and str(sufijo) == "4":
                #     ruta_img = obtener_imagen_raid(obtener_catalogo_imagenes_raid(), f"{nombre_raid}{sufijo}")
                #     if ruta_img and os.path.exists(ruta_img):
                #         ahora_arg = datetime.now(ZONA_ARGENTINA)
                #         hora_actual_24h = ahora_arg.strftime("%H:%M")
                #         ruta_temp = f"imagen/raid/raid/antes/{nombre_raid.lower()}_modificada.png"
                #         
                #         if estampar_hora_en_imagen(ruta_img, hora_actual_24h, ruta_temp):
                #             # Enviar al canal correspondiente con tu lógica de Discord
                #             pass

            await asyncio.sleep(30) # Comprobación periódica del JSON
        except Exception as e:
            logger.error(f"❌ Error en el ciclo principal de raids: {e}")
            await asyncio.sleep(30)
