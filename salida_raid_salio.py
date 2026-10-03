import os
import logging
import json
import asyncio
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import discord
from PIL import Image
import config

logger = logging.getLogger("SalidaRaidSalio")

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

# Cachés y estados exclusivos para el servicio de Salió
CACHE_SALIO = {}
CACHE_SALIO_35M = {}
ESTADOS_PREVIOS_RAIDS = {}
TIEMPOS_CAMBIO_VIVO = {}
ULTIMO_RESET_CACHE_SALIO_DIA = None

FILTRO_PUBLICAR_RAIDS_SALIO = {
    "Valakas": "si", "Antharas": "si", "Fafureon": "si", "Balrog": "si",
    "Electrical": "si", "Baium": "si", "Zaken": "si", "Core": "si",
    "Orfen": "si", "Queen Ant": "si", "Frintezza": "si", "Freya": "si",
    "Zariche": "si", "Decarbia": "si", "Hekaton": "si", "Queen shyeed": "si",
    "Golkonda": "si", "Galaxia": "si", "Barakiel": "si",
    "otros_60_mas": "si", "otros_60_menos": "no"
}

def limpiar_memoria_cache_salio():
    global ULTIMO_RESET_CACHE_SALIO_DIA, CACHE_SALIO, CACHE_SALIO_35M, ESTADOS_PREVIOS_RAIDS, TIEMPOS_CAMBIO_VIVO
    ahora_arg = datetime.now(ZONA_ARGENTINA)
    hoy_str = ahora_arg.strftime("%Y-%m-%d")
    
    if ahora_arg.hour >= 4 and ULTIMO_RESET_CACHE_SALIO_DIA != hoy_str:
        CACHE_SALIO.clear()
        CACHE_SALIO_35M.clear()
        ESTADOS_PREVIOS_RAIDS.clear()
        TIEMPOS_CAMBIO_VIVO.clear()
        ULTIMO_RESET_CACHE_SALIO_DIA = hoy_str
        logger.info("🧹 Memoria caché del servicio SALIO limpiada exitosamente a las 04:00 AM.")

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
    Toma la plantilla base de la imagen, calcula el ancho combinado de los números 
    de la hora (formato 24h ej. 20:30) para centrarlos perfectamente debajo de 'ABRIO',
    y los estampa usando los recursos configurados en RECURSOS_NUMEROS.
    """
    try:
        base_img = Image.open(ruta_imagen_origen).convert("RGBA")
        ancho_total_img, alto_total_img = base_img.size

        # 1. Cargamos temporalmente los dígitos para medir su ancho total y espaciado
        digitos_cargados = []
        ancho_bloque_total = 0
        espaciado = 4  # Espacio en pixeles entre cada número/símbolo

        for char in hora_texto:
            ruta_digito = RECURSOS_NUMEROS.get(char)
            if ruta_digito and os.path.exists(ruta_digito):
                digito_img = Image.open(ruta_digito).convert("RGBA")
                digitos_cargados.append(digito_img)
                ancho_bloque_total += digito_img.width
            else:
                digitos_cargados.append(None)
                ancho_bloque_total += 30  # Ancho predeterminado de respaldo

        # Añadimos el espacio acumulado entre los caracteres
        if len(digitos_cargados) > 1:
            ancho_bloque_total += espaciado * (len(digitos_cargados) - 1)

        # 2. Calculamos la posición X inicial para que quede perfectamente CENTRADO horizontalmente
        pos_x = (ancho_total_img - ancho_bloque_total) // 2
        
        # 3. Posición Y: Ajustada para colocarse en la franja negra inferior (ejemplo: debajo de ABRIO)
        # Puedes modificar este valor si necesitas subirlo o bajarlo unos cuantos pixeles.
        pos_y = int(alto_total_img * 0.76)

        # 4. Pegamos cada dígito de manera secuencial sobre la imagen base
        for i, digito_img in enumerate(digitos_cargados):
            if digito_img:
                base_img.paste(digito_img, (pos_x, pos_y), digito_img)
                pos_x += digito_img.width + espaciado
            else:
                pos_x += 30 + espaciado

        base_img.save(ruta_imagen_destino, "PNG")
        return True
    except Exception as e:
        logger.error(f"❌ Error al estampar hora en la imagen: {e}")
        return False

async def enviar_a_canales_salio(bot_instance, ruta_imagen, nombre_archivo_discord, nombre_raid=""):
    canal_principal_id = getattr(config, "ENVIAR_MENSAJE_CHANNEL_ID", None)
    
    canales_destino = []
    if canal_principal_id:
        c1 = bot_instance.get_channel(canal_principal_id)
        if c1:
            canales_destino.append(c1)

    for canal in canales_destino:
        try:
            if os.path.exists(ruta_imagen):
                with open(ruta_imagen, "rb") as binary:
                    await canal.send(file=discord.File(binary, filename=nombre_archivo_discord))
        except Exception as e:
            logger.error(f"❌ Error al enviar imagen de SALIO al canal {canal.id}: {e}")

# ==========================================
# SERVICIO: PUBLICAR_RAIDS_SALIO
# ==========================================
async def servicio_publicar_raids_salio(bot_instance, ruta_json, json_lock):
    await bot_instance.wait_until_ready()
    logger.info("🟢 Servicio independiente de 'Raids Salió' iniciado correctamente.")

    while not bot_instance.is_closed():
        try:
            limpiar_memoria_cache_salio()
            if os.path.exists(ruta_json):
                async with json_lock:
                    with open(ruta_json, "r", encoding="utf-8") as f:
                        data = json.load(f)

                raid_60_plus = data.get("raid_60_plus", [])
                raid_60_menos = data.get("raid_60_menos", [])
                vivo_o_muerto = data.get("vivo_o_muerto", [])
                
                todos_los_jefes = list(raid_60_plus) + list(raid_60_menos) + list(vivo_o_muerto)
                ahora_arg = datetime.now(ZONA_ARGENTINA)
                hoy_str = ahora_arg.strftime("%Y-%m-%d")

                if todos_los_jefes:
                    for item in todos_los_jefes:
                        nombre = str(item.get("nombre", "")).strip()
                        if not nombre:
                            continue
                        
                        valor_filtro_individual = FILTRO_PUBLICAR_RAIDS_SALIO.get(nombre)
                        es_60_plus = item in raid_60_plus or nombre in [r.get("nombre") for r in raid_60_plus]
                        
                        if valor_filtro_individual is not None:
                            if valor_filtro_individual != "si":
                                continue
                        else:
                            if es_60_plus:
                                if FILTRO_PUBLICAR_RAIDS_SALIO.get("otros_60_mas", "no") != "si":
                                    continue
                            else:
                                if FILTRO_PUBLICAR_RAIDS_SALIO.get("otros_60_menos", "no") != "si":
                                    continue

                        # 1. Raids comunes (Parseo estricto formato DD-MM-YYYY HH:MM)
                        if nombre not in ["Baium", "Zaken", "Core", "Orfen", "Queen Ant", "Frintezza", "Freya", "Zariche", "Valakas", "Antharas", "Fafureon"]:
                            tiempo_bruto = str(item.get("tiempo_str") or item.get("tiempo") or item.get("hora") or "").strip()
                            if not tiempo_bruto or tiempo_bruto in ["-", "None", "null", ""]:
                                continue

                            match_dt = re.search(r'(\d{2})-(\d{2})-(\d{4})\s+(\d{1,2}:\d{2})', tiempo_bruto)
                            if not match_dt:
                                continue

                            dia, mes, anio, hora_raid_str = match_dt.groups()
                            fecha_raid_str = f"{anio}-{mes}-{dia}"

                            if fecha_raid_str != hoy_str:
                                continue

                            try:
                                dt_raid = datetime.strptime(f"{fecha_raid_str} {hora_raid_str}", "%Y-%m-%d %H:%M").replace(tzinfo=ZONA_ARGENTINA)
                                
                                if dt_raid <= ahora_arg < dt_raid + timedelta(minutes=5):
                                    sufijo = "2"
                                    clave_cache_hora = f"{nombre}_{fecha_raid_str}_{hora_raid_str}_hora_exacta"
                                    if not CACHE_SALIO.get(clave_cache_hora):
                                        nombre_archivo = f"{nombre.lower().replace(' ', '')}{sufijo}.png"
                                        ruta_img = f"imagen/raid/raid/antes/{nombre_archivo}"
                                        
                                        if not os.path.exists(ruta_img):
                                            catalogo = obtener_catalogo_imagenes_raid()
                                            ruta_img = obtener_imagen_raid(catalogo, f"{nombre}{sufijo}")

                                        if ruta_img and os.path.exists(ruta_img):
                                            await enviar_a_canales_salio(bot_instance, ruta_img, f"raid_{nombre.lower()}_salio_{sufijo}.png", nombre_raid=nombre)
                                            CACHE_SALIO[clave_cache_hora] = True
                                            logger.info(f"✅ [SALIO] Raid común '{nombre}' publicado a su hora exacta ({hora_raid_str}).")
                                            await asyncio.sleep(1.0)
                            except ValueError:
                                pass
                            continue

                        # 2. Épicos y Dragones (Monitoreo de estado Vivo/Muerto)
                        estado_actual_json = str(item.get("estado") or item.get("status") or item.get("vivo_o_muerto") or "").strip().lower()
                        if not estado_actual_json:
                            continue

                        estado_anterior = ESTADOS_PREVIOS_RAIDS.get(nombre, "muerto")

                        if estado_anterior == "muerto" and estado_actual_json == "vivo":
                            ESTADOS_PREVIOS_RAIDS[nombre] = "vivo"
                            TIEMPOS_CAMBIO_VIVO[nombre] = ahora_arg
                            logger.info(f"⚡ [SALIO] Cambio detectado: '{nombre}' pasó de MUERTO a VIVO.")

                            sufijo = "2" if nombre in ["Baium", "Zaken", "Core", "Orfen", "Queen Ant", "Frintezza", "Freya", "Zariche"] else "4"
                            clave_cache = f"{nombre}_{hoy_str}_sufijo_{sufijo}"
                            
                            if not CACHE_SALIO.get(clave_cache):
                                nombre_archivo = f"{nombre.lower().replace(' ', '')}{sufijo}.png"
                                ruta_img = f"imagen/raid/raid/antes/{nombre_archivo}"

                                if not os.path.exists(ruta_img):
                                    catalogo = obtener_catalogo_imagenes_raid()
                                    ruta_img = obtener_imagen_raid(catalogo, f"{nombre}{sufijo}")

                                if ruta_img and os.path.exists(ruta_img):
                                    ruta_final_envio = ruta_img
                                    
                                    # Para Valakas y Antharas (sufijo 4), generamos la hora exacta real de publicación y la estampamos centrada
                                    if nombre in ["Valakas", "Antharas"] and sufijo == "4":
                                        hora_actual_24h = ahora_arg.strftime("%H:%M")
                                        ruta_temp_modificada = f"imagen/raid/raid/antes/{nombre.lower()}_modificada.png"
                                        
                                        if estampar_hora_en_imagen(ruta_img, hora_actual_24h, ruta_temp_modificada):
                                            ruta_final_envio = ruta_temp_modificada
                                        
                                        logger.info(f"🕒 [SALIO] '{nombre}' (Sufijo 4) estampado con hora real exacta: {hora_actual_24h}")

                                    await enviar_a_canales_salio(bot_instance, ruta_final_envio, f"raid_{nombre.lower()}_salio_{sufijo}.png", nombre_raid=nombre)
                                    CACHE_SALIO[clave_cache] = True
                                    logger.info(f"✅ [SALIO] Publicado '{nombre}' inmediato (Sufijo {sufijo}).")
                                    await asyncio.sleep(1.0)

                        if estado_actual_json == "muerto":
                            ESTADOS_PREVIOS_RAIDS[nombre] = "muerto"

                        # Valakas y Antharas: 35 minutos después -> Sufijo 5
                        if nombre in ["Valakas", "Antharas"] and ESTADOS_PREVIOS_RAIDS.get(nombre) == "vivo":
                            tiempo_cambio = TIEMPOS_CAMBIO_VIVO.get(nombre)
                            if tiempo_cambio:
                                tiempo_objetivo_35m = tiempo_cambio + timedelta(minutes=35)
                                
                                if tiempo_objetivo_35m <= ahora_arg < tiempo_objetivo_35m + timedelta(minutes=5):
                                    sufijo = "5"
                                    clave_cache_35m = f"{nombre}_{hoy_str}_sufijo_{sufijo}_35m"
                                    
                                    if not CACHE_SALIO_35M.get(clave_cache_35m):
                                        nombre_archivo = f"{nombre.lower().replace(' ', '')}{sufijo}.png"
                                        ruta_img = f"imagen/raid/raid/antes/{nombre_archivo}"

                                        if not os.path.exists(ruta_img):
                                            catalogo = obtener_catalogo_imagenes_raid()
                                            ruta_img = obtener_imagen_raid(catalogo, f"{nombre}{sufijo}")

                                        if ruta_img and os.path.exists(ruta_img):
                                            await enviar_a_canales_salio(bot_instance, ruta_img, f"raid_{nombre.lower()}_salio_{sufijo}.png", nombre_raid=nombre)
                                            CACHE_SALIO_35M[clave_cache_35m] = True
                                            logger.info(f"✅ [SALIO] Publicado '{nombre}' a los 35 minutos (Sufijo {sufijo}).")
                                            await asyncio.sleep(1.0)

        except Exception as e:
            logger.error(f"❌ Error en servicio_publicar_raids_salio: {e}")

        await asyncio.sleep(30)
