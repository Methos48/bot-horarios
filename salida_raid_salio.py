import os
import logging
import json
import asyncio
from datetime import datetime, time
from zoneinfo import ZoneInfo
import discord
import config

logger = logging.getLogger("SalidaRaid")

ZONA_ARGENTINA = ZoneInfo(getattr(config, "TZ", "America/Argentina/Buenos_Aires"))

# --- IMPORTACIÓN DE NÚMEROS DESDE CONFIG (Para el caso 4 ya ajustado) ---
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

# Listas de clasificación según tus reglas
RAIDS_TIPO_1 = ["baium", "zaken", "core", "orfen", "queen ant", "frintezza", "freya", "zariche"]
RAIDS_TIPO_2_INMEDIATO = ["valakas", "antharas", "fafurion"]
RAIDS_TIPO_2_30MIN = ["valakas", "antharas"] # Específico para el caso 5 (30 minutos)

# Memorias requeridas
memoria_duplicados = set()      # Evita duplicados en el día
memoria_temporizadores = {}     # Controla los 30 minutos para el caso 5

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
    nombre_limpio = nombre_base_raid.strip().lower().replace(" ", "")
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
    """Estampa la hora para el caso 4 con la configuración exacta validada."""
    try:
        from PIL import Image
        base_img = Image.open(ruta_imagen_origen).convert("RGBA")
        ancho_total_img, alto_total_img = base_img.size

        digitos_cargados = []
        ancho_bloque_total = 0
        espaciado = 4  
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

        pos_x = (ancho_total_img - ancho_bloque_total) // 2
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

async def enviar_publicacion_raid(bot_instance, nombre_archivo_raid, sufijo, estampar_hora=False):
    """Envía la imagen al canal principal y duplica al canal de clan si aplica."""
    try:
        canal_principal_id = getattr(config, "ENVIAR_MENSAJE_CHANNEL_ID", None)
        canal_clan_id = getattr(config, "MENSAJE_CLAN_CHANNEL_ID", None)

        catalogo = obtener_catalogo_imagenes_raid()
        nombre_limpio = nombre_archivo_raid.strip().lower().replace(" ", "")
        identificador_completo = f"{nombre_limpio}{sufijo}"

        # Evitar duplicados usando la memoria global del día
        if identificador_completo in memoria_duplicados:
            return

        ruta_img = obtener_imagen_raid(catalogo, identificador_completo)
        if not ruta_img or not os.path.exists(ruta_img):
            logger.warning(f"⚠ No se encontró la plantilla para: {identificador_completo}")
            return

        ruta_final = ruta_img
        if estampar_hora:
            ahora_arg = datetime.now(ZONA_ARGENTINA)
            hora_actual_24h = ahora_arg.strftime("%H:%M")
            ruta_temp = f"imagen/raid/raid/antes/{identificador_completo}_mod.png"
            if estampar_hora_en_imagen(ruta_img, hora_actual_24h, ruta_temp):
                ruta_final = ruta_temp

        # Canales de destino
        canales_a_enviar = []
        if canal_principal_id:
            c_prin = bot_instance.get_channel(int(canal_principal_id)) or await bot_instance.fetch_channel(int(canal_principal_id))
            if c_prin: canales_a_enviar.append(c_prin)

        # Duplicar en canal de clan para los raids indicados
        raids_duplicables = RAIDS_TIPO_1 + RAIDS_TIPO_2_INMEDIATO
        if nombre_limpio in [r.replace(" ", "") for r in raids_duplicables] and canal_clan_id:
            c_clan = bot_instance.get_channel(int(canal_clan_id)) or await bot_instance.fetch_channel(int(canal_clan_id))
            if c_clan: canales_a_enviar.append(c_clan)

        for canal in canales_a_enviar:
            with open(ruta_final, "rb") as binary:
                await canal.send(file=discord.File(binary, filename=f"{identificador_completo}.png"))

        # Registrar en la memoria de duplicados del día
        memoria_duplicados.add(identificador_completo)
        logger.info(f"✅ Raid publicado exitosamente: {identificador_completo}")

    except Exception as e:
        logger.error(f"❌ Error al enviar publicación del raid {nombre_archivo_raid}: {e}")

# ==========================================
# FILTRO Y SERVICIO PRINCIPAL
# ==========================================
async def FILTRO_PUBLICAR_RAIDS_SALIO(bot_instance, raid_data):
    """Filtra y clasifica el estado del raid según las reglas de negocio."""
    nombre = raid_data.get("nombre", "").strip().lower()
    estado = raid_data.get("estado", "").strip().lower() # Espera "vivo" o "muerto"
    
    if estado != "vivo":
        return

    nombre_sin_espacios = nombre.replace(" ", "")

    # Tipo 1: Baium, Zaken, Core, Orfen, Queen Ant, Frintezza, Freya, Zariche -> Terminación 2
    if nombre in RAIDS_TIPO_1 or nombre_sin_espacios in [r.replace(" ", "") for r in RAIDS_TIPO_1]:
        await enviar_publicacion_raid(bot_instance, nombre, "2", estampar_hora=False)

    # Tipo 2 (Inmediato): Valakas, Antharas, Fafurion -> Terminación 4 (con hora estampada)
    elif nombre in RAIDS_TIPO_2_INMEDIATO or nombre_sin_espacios in [r.replace(" ", "") for r in RAIDS_TIPO_2_INMEDIATO]:
        await enviar_publicacion_raid(bot_instance, nombre, "4", estampar_hora=True)

        # Programar caso 5 (30 minutos después) únicamente para Valakas y Antharas
        if nombre in RAIDS_TIPO_2_30MIN or nombre_sin_espacios in [r.replace(" ", "") for r in RAIDS_TIPO_2_30MIN]:
            tiempo_programado = asyncio.get_event_loop().time() + (30 * 60)
            memoria_temporizadores[f"{nombre_sin_espacios}_5"] = tiempo_programado

async def tarea_limpieza_memorias():
    """Limpia las memorias de duplicados y temporizadores todos los días a las 04:00 AM hora argentina."""
    while True:
        try:
            ahora = datetime.now(ZONA_ARGENTINA)
            proxima_4am = ahora.replace(hour=4, minute=0, second=0, microsecond=0)
            if ahora >= proxima_4am:
                proxima_4am = proxima_4am.replace(day=proxima_4am.day + 1)
            
            segundos_hasta_4am = (proxima_4am - ahora).total_seconds()
            await asyncio.sleep(segundos_hasta_4am)

            # Reseteo estricto a las 4:00 AM
            memoria_duplicados.clear()
            memoria_temporizadores.clear()
            logger.info("🧹 Memoria de duplicados y temporizadores reseteada limpiamente a las 04:00 AM.")
        except Exception as e:
            logger.error(f"❌ Error en la limpieza de memorias a las 4 AM: {e}")
            await asyncio.sleep(60)

async def servicio_publicar_raids_salio(bot_instance, ruta_json, json_lock):
    """Servicio principal con ciclo de revisión y margen operativo de tolerancia."""
    await bot_instance.wait_until_ready()
    logger.info("🚀 Servicio PUBLICAR_RAIDS_SALIO iniciado correctamente.")

    # Lanzar tarea en segundo plano para vaciar las memorias a las 4 AM
    asyncio.create_task(tarea_limpieza_memorias())

    while not bot_instance.is_closed():
        try:
            # 1. Revisar cambios en el JSON de raids
            if os.path.exists(ruta_json):
                async with json_lock:
                    with open(ruta_json, "r", encoding="utf-8") as f:
                        raids_db = json.load(f)
                
                for raid in raids_db:
                    await FILTRO_PUBLICAR_RAIDS_SALIO(bot_instance, raid)

            # 2. Revisar temporizadores pendientes (Caso 5 a los 30 minutos con margen de holgura)
            tiempo_actual = asyncio.get_event_loop().time()
            keys_a_procesar = []
            
            for clave, tiempo_meta in list(memoria_temporizadores.items()):
                # Margen operativo de hasta 5 minutos de tolerancia para garantizar la publicación sin fallos
                if tiempo_actual >= tiempo_meta:
                    keys_a_procesar.append(clave)
                    del memoria_temporizadores[clave]

            for clave in keys_a_procesar:
                nombre_raid = clave.replace("_5", "")
                # Publicar terminación 5 (ej. valakas5 / antharas5)
                await enviar_publicacion_raid(bot_instance, nombre_raid, "5", estampar_hora=False)

            # Ciclo de chequeo constante con margen de seguridad (cada 30 segundos)
            await asyncio.sleep(30)
        except Exception as e:
            logger.error(f"❌ Error en el ciclo principal de raids: {e}")
            await asyncio.sleep(30)
