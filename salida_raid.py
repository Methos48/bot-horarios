import os
import logging
import json
import io
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter
import discord
import config

logger = logging.getLogger("SalidaRaid")

ZONA_ARGENTINA = ZoneInfo(getattr(config, "TZ", "America/Argentina/Buenos_Aires"))

# ==========================================
# CACHÉ DE HISTORIAL Y CONTROL DINÁMICO
# ==========================================
HISTORIAL_ENVIADOS_CACHE = {}
ULTIMO_RESET_CACHE_DIA = None  # Variable para controlar el reseteo diario por cambio de fecha

# ==========================================
# CONFIGURACIÓN DE TEMA / ESTILO VISUAL
# ==========================================
TEMA_ACTIVO = "rojo"

# ==========================================
# POSICIÓN MANUAL DE LA HORA (Coordenadas X e Y)
# ==========================================
POS_X = 20
POS_Y = 565

# ==========================================
# JEFES ESPECIALES (Rango aleatorio / sin hora fija exacta)
# ==========================================
JEFS_ESPECIALES_RANDOM = {
    "core", "orfen", "baium", "zaken", "freya", 
    "zariche", "frintezza", "queen ant", "electrical", "balrog"
}

# ==========================================
# FILTROS DE PUBLICACIÓN POR RAID ("si" o "no")
# ==========================================
FILTRO_PUBLICAR_RAIDS = {
    "Valakas": "si", "Antharas": "si", "Fafureon": "si", "Balrog": "no",
    "Electrical": "no", "Baium": "si", "Zaken": "si", "Core": "si",
    "Orfen": "si", "Queen Ant": "si", "Frintezza": "si", "Freya": "si",
    "Zariche": "si", "Decarbia": "si", "Hekaton": "si", "Queen shyeed": "si",
    "Golkonda": "si", "Galaxia": "si", "Barakiel": "si",
    "otros_60_mas": "no", "otros_60_menos": "no"
}

FILTRO_PUBLICAR_RAIDS_ANTES = {
    "Valakas": "si", "Antharas": "si", "Fafureon": "si", "Balrog": "si",
    "Electrical": "si", "Baium": "si", "Zaken": "si", "Core": "si",
    "Orfen": "si", "Queen Ant": "si", "Frintezza": "si", "Freya": "si",
    "Zariche": "si", "Decarbia": "si", "Hekaton": "si", "Queen shyeed": "si",
    "Golkonda": "si", "Galaxia": "si", "Barakiel": "si",
    "otros_60_mas": "si", "otros_60_menos": "no"
}

FILTRO_PUBLICAR_RAIDS_SALIO = {
    "Valakas": "si", "Antharas": "si", "Fafureon": "si", "Balrog": "si",
    "Electrical": "si", "Baium": "si", "Zaken": "si", "Core": "si",
    "Orfen": "si", "Queen Ant": "si", "Frintezza": "si", "Freya": "si",
    "Zariche": "si", "Decarbia": "si", "Hekaton": "si", "Queen shyeed": "si",
    "Golkonda": "si", "Galaxia": "si", "Barakiel": "si",
    "otros_60_mas": "si", "otros_60_menos": "no"
}


def debe_publicar_raid(nombre_jefe, nivel_jefe=None, filtro_usado=None):
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


def obtener_imagen_raid(catalogo, nombre_base_raid, tema=TEMA_ACTIVO, tipo_filtro="PUBLICAR_RAIDS"):
    if tipo_filtro in ["PUBLICAR_RAIDS_ANTES", "PUBLICAR_RAIDS_SALIO", "super_epicos", "antes", "salio"]:
        subcarpetas_a_probar = ["raid/antes/", ""]
    else:
        subcarpetas_a_probar = [f"{tema}/raid/", f"{tema}/"]

    for sub in subcarpetas_a_probar:
        for ext in ['.png', '.jpg', '.webp', '.jpeg']:
            claves_intento = [
                f"{sub}{nombre_base_raid}{ext}",
                f"raid/{sub}{nombre_base_raid}{ext}"
            ]
            
            for clave_intento in claves_intento:
                if clave_intento in catalogo:
                    return catalogo[clave_intento]

    return None


async def procesar_ciclo_raids(bot_instance, ruta_json, tipo_filtro, intervalo_segundos=30):
    ahora_actual = datetime.now(ZONA_ARGENTINA)

    if tipo_filtro == "PUBLICAR_RAIDS_ANTES":
        filtro_activo = FILTRO_PUBLICAR_RAIDS_ANTES
        nombre_filtro_log = "PUBLICAR_RAIDS_ANTES"
        canal_id = getattr(config, "ENVIAR_MENSAJE_CHANNEL_ID", None)
    elif tipo_filtro == "PUBLICAR_RAIDS_SALIO":
        filtro_activo = FILTRO_PUBLICAR_RAIDS_SALIO
        nombre_filtro_log = "PUBLICAR_RAIDS_SALIO"
        canal_id = getattr(config, "ENVIAR_MENSAJE_CHANNEL_ID", None)
    elif tipo_filtro == "super_epicos":
        filtro_activo = FILTRO_PUBLICAR_RAIDS
        nombre_filtro_log = "super_epicos"
        canal_envio_id = getattr(config, "ENVIAR_MENSAJE_CHANNEL_ID", None)
        canal_clan_id = getattr(config, "MENSAJE_CLAN_CHANNEL_ID", None)
    else:  # PUBLICAR_RAIDS (Servicio principal)
        filtro_activo = FILTRO_PUBLICAR_RAIDS
        nombre_filtro_log = "PUBLICAR_RAIDS"
        canal_id = getattr(config, "MENSAJE_CLAN_CHANNEL_ID", None)
    
    if tipo_filtro != "super_epicos" and not canal_id:
        return

    if not os.path.exists(ruta_json):
        return

    try:
        with open(ruta_json, "r", encoding="utf-8") as f:
            contenido_json = json.load(f)
            
        vivo_o_muerto = contenido_json.get("vivo_o_muerto", [])
        raid_60_plus = contenido_json.get("raid_60_plus", [])
        datos_horario = vivo_o_muerto + raid_60_plus
        
    except Exception as e:
        logger.error(f"❌ Error al leer o parsear el JSON en salida_raid: {e}")
        return

    try:
        catalogo_raids = obtener_catalogo_imagenes_raid()
        if not catalogo_raids:
            return

        raids_super_epicos_nombres = {"valakas", "antharas", "fafureon"}
        datos_procesados = []

        for jefe in datos_horario:
            nombre_jefe = jefe.get("nombre", jefe.get("nombre_imagen", ""))
            nivel_jefe = jefe.get("nivel", None)
            
            nombre_crudo = nombre_jefe.strip()
            nombre_base_limpio = "".join(c for c in nombre_crudo if c.isalnum()).lower()
            
            if not nombre_base_limpio:
                continue

            # ==========================================
            # SERVICIO: SUPER_EPICOS
            # ==========================================
            if tipo_filtro == "super_epicos":
                if nombre_base_limpio not in raids_super_epicos_nombres:
                    continue

                estado = jefe.get("estado", "").upper()
                tiempo_str = jefe.get("tiempo_str", "-")
                es_vivo = (estado == "VIVO" or estado == "ALIVE" or jefe.get("es_vivo", False))
                
                dt_obj = None
                if tiempo_str and tiempo_str != "-":
                    try:
                        dt_obj = datetime.strptime(tiempo_str, "%d/%m/%Y %H:%M").replace(tzinfo=ZONA_ARGENTINA)
                    except ValueError:
                        pass

                if not dt_obj and not es_vivo:
                    continue

                if dt_obj and dt_obj.date() != ahora_actual.date():
                    continue

                tiempo_key = dt_obj.strftime('%Y%m%d_%H%M') if dt_obj else f"vivo_{ahora_actual.strftime('%Y%m%d')}"
                ventana_maxima = max(intervalo_segundos * 2, 90)

                # Regla 1: 1 hora antes
                if dt_obj:
                    t_obj_1 = dt_obj - timedelta(hours=1)
                    diff_1 = (ahora_actual - t_obj_1).total_seconds()
                    cid_1 = f"{nombre_base_limpio}_se_1_{tiempo_key}"
                    if 0 <= diff_1 < ventana_maxima and cid_1 not in HISTORIAL_ENVIADOS_CACHE:
                        HISTORIAL_ENVIADOS_CACHE[cid_1] = ahora_actual
                        datos_procesados.append({**jefe, "nombre_imagen_base": f"{nombre_base_limpio}1", "canal_destino_id": canal_envio_id})

                    # Regla 2: 30 minutos antes
                    t_obj_2 = dt_obj - timedelta(minutes=30)
                    diff_2 = (ahora_actual - t_obj_2).total_seconds()
                    cid_2 = f"{nombre_base_limpio}_se_2_{tiempo_key}"
                    if 0 <= diff_2 < ventana_maxima and cid_2 not in HISTORIAL_ENVIADOS_CACHE:
                        HISTORIAL_ENVIADOS_CACHE[cid_2] = ahora_actual
                        datos_procesados.append({**jefe, "nombre_imagen_base": f"{nombre_base_limpio}2", "canal_destino_id": canal_envio_id})

                    # Regla 3: Hora exacta
                    diff_3 = (ahora_actual - dt_obj).total_seconds()
                    cid_3 = f"{nombre_base_limpio}_se_3_{tiempo_key}"
                    if 0 <= diff_3 < ventana_maxima and cid_3 not in HISTORIAL_ENVIADOS_CACHE:
                        HISTORIAL_ENVIADOS_CACHE[cid_3] = ahora_actual
                        datos_procesados.append({**jefe, "nombre_imagen_base": f"{nombre_base_limpio}3", "canal_destino_id": canal_clan_id})

                # Regla 4: Cambio a VIVO
                if es_vivo:
                    cid_4 = f"{nombre_base_limpio}_se_4_vivo_{tiempo_key}"
                    if cid_4 not in HISTORIAL_ENVIADOS_CACHE:
                        HISTORIAL_ENVIADOS_CACHE[cid_4] = ahora_actual
                        datos_procesados.append({**jefe, "nombre_imagen_base": f"{nombre_base_limpio}4", "canal_destino_id": canal_clan_id})

                continue

            # ==========================================
            # FILTROS DE LOS 3 SERVICIOS PRINCIPALES
            # ==========================================
            if not debe_publicar_raid(nombre_jefe, nivel_jefe, filtro_usado=filtro_activo):
                continue
                
            estado = jefe.get("estado", "").upper()
            tiempo_str = jefe.get("tiempo_str", "-")
            es_vivo = (estado == "VIVO" or estado == "ALIVE" or jefe.get("es_vivo", False))
            
            dt_obj = None
            if tiempo_str and tiempo_str != "-":
                try:
                    dt_obj = datetime.strptime(tiempo_str, "%d/%m/%Y %H:%M").replace(tzinfo=ZONA_ARGENTINA)
                except ValueError:
                    pass

            if not dt_obj and not es_vivo:
                continue

            tiempo_key = dt_obj.strftime('%Y%m%d_%H%M') if dt_obj else f"vivo_{ahora_actual.strftime('%Y%m%d')}"
            ventana_maxima = max(intervalo_segundos * 2, 90)

            # --- SERVICIO: PUBLICAR_RAIDS_ANTES ---
            if tipo_filtro == "PUBLICAR_RAIDS_ANTES":
                if es_vivo or not dt_obj or dt_obj.date() != ahora_actual.date():
                    continue
                tiempo_objetivo = dt_obj if nombre_base_limpio in JEFS_ESPECIALES_RANDOM else dt_obj - timedelta(minutes=10)
                diferencia_segundos = (ahora_actual - tiempo_objetivo).total_seconds()
                
                clave_id = f"{nombre_base_limpio}_antes_{tiempo_key}"
                if 0 <= diferencia_segundos < ventana_maxima and clave_id not in HISTORIAL_ENVIADOS_CACHE:
                    HISTORIAL_ENVIADOS_CACHE[clave_id] = ahora_actual
                    reg = jefe.copy()
                    reg["nombre_imagen_base"] = f"{nombre_base_limpio}1"
                    reg["canal_destino_id"] = canal_id
                    datos_procesados.append(reg)
                continue

            # --- SERVICIO: PUBLICAR_RAIDS_SALIO ---
            elif tipo_filtro == "PUBLICAR_RAIDS_SALIO":
                if nombre_base_limpio in raids_super_epicos_nombres:
                    continue
                if nombre_base_limpio in JEFS_ESPECIALES_RANDOM:
                    if es_vivo:
                        clave_id_salio = f"{nombre_base_limpio}_salio_vivo_{tiempo_key}"
                        if clave_id_salio not in HISTORIAL_ENVIADOS_CACHE:
                            HISTORIAL_ENVIADOS_CACHE[clave_id_salio] = ahora_actual
                            reg = jefe.copy()
                            reg["nombre_imagen_base"] = f"{nombre_base_limpio}2"
                            reg["canal_destino_id"] = canal_id
                            datos_procesados.append(reg)
                else:
                    if dt_obj:
                        if dt_obj.date() != ahora_actual.date():
                            continue
                        diferencia_segundos = (ahora_actual - dt_obj).total_seconds()
                        clave_id_salio = f"{nombre_base_limpio}_salio_{tiempo_key}"
                        if 0 <= diferencia_segundos < ventana_maxima and clave_id_salio not in HISTORIAL_ENVIADOS_CACHE:
                            HISTORIAL_ENVIADOS_CACHE[clave_id_salio] = ahora_actual
                            reg = jefe.copy()
                            reg["nombre_imagen_base"] = f"{nombre_base_limpio}2"
                            reg["canal_destino_id"] = canal_id
                            datos_procesados.append(reg)
                continue

            # --- SERVICIO: PUBLICAR_RAIDS (Principal / Hora exacta) ---
            else:
                if dt_obj:
                    if dt_obj.date() != ahora_actual.date():
                        continue
                    diferencia_segundos = (ahora_actual - dt_obj).total_seconds()
                    clave_id_principal = f"{nombre_base_limpio}_principal_{tiempo_key}"
                    
                    if 0 <= diferencia_segundos < ventana_maxima and clave_id_principal not in HISTORIAL_ENVIADOS_CACHE:
                        HISTORIAL_ENVIADOS_CACHE[clave_id_principal] = ahora_actual
                        reg = jefe.copy()
                        reg["nombre_imagen_base"] = f"{nombre_base_limpio}"
                        reg["canal_destino_id"] = canal_id
                        datos_procesados.append(reg)
                continue

        if not datos_procesados:
            return

        for jefe in datos_procesados:
            nombre_imagen_base = jefe.get("nombre_imagen_base")
            destino_canal_id = jefe.get("canal_destino_id")
            
            if not destino_canal_id:
                continue

            channel_destino = bot_instance.get_channel(destino_canal_id)
            if not channel_destino:
                continue

            ruta_imagen = obtener_imagen_raid(catalogo_raids, nombre_imagen_base, tema=TEMA_ACTIVO, tipo_filtro=tipo_filtro)
            if not ruta_imagen:
                continue
                
            img = Image.open(ruta_imagen).convert("RGBA")
            
            with io.BytesIO() as image_binary:
                img.convert("RGB").save(image_binary, "PNG")
                image_binary.seek(0)
                await channel_destino.send(file=discord.File(image_binary, filename=f"raid_{nombre_imagen_base}.png"))

    except Exception as e:
        logger.error(f"❌ Error crítico en salida_raid [{nombre_filtro_log}]: {e}")


# ==========================================
# BUCLE PERMANENTE EN SEGUNDO PLANO
# ==========================================
async def iniciar_monitoreo_permanente(bot_instance, ruta_json="horarios.json", intervalo_segundos=30):
    global HISTORIAL_ENVIADOS_CACHE, ULTIMO_RESET_CACHE_DIA
    logger.info(f"🔄 Bucle permanente de monitoreo de Raids iniciado. Intervalo: {intervalo_segundos}s")
    
    await bot_instance.wait_until_ready()

    while not bot_instance.is_closed():
        try:
            ahora_actual = datetime.now(ZONA_ARGENTINA)

            # MECANISMO DE LIMPIEZA DIARIA ROBUSTO POR CAMBIO DE DÍA
            fecha_hoy = ahora_actual.date()
            if ULTIMO_RESET_CACHE_DIA is None or fecha_hoy > ULTIMO_RESET_CACHE_DIA:
                HISTORIAL_ENVIADOS_CACHE.clear()
                ULTIMO_RESET_CACHE_DIA = fecha_hoy
                logger.info("🧹 Caché de raids limpiada automáticamente por cambio de día.")

            # Ciclo que ejecuta los 3 servicios principales + super_epicos
            for tipo in ["PUBLICAR_RAIDS", "PUBLICAR_RAIDS_ANTES", "PUBLICAR_RAIDS_SALIO", "super_epicos"]:
                await procesar_ciclo_raids(bot_instance, ruta_json, tipo, intervalo_segundos)
                
        except Exception as e:
            logger.error(f"❌ Error en el ciclo de monitoreo permanente: {e}")
        
        await asyncio.sleep(intervalo_segundos)
