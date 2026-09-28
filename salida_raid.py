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


def obtener_imagen_raid(catalogo, nombre_base_raid, tema=TEMA_ACTIVO, tipo_filtro="principal"):
    if tipo_filtro == "antes":
        subcarpetas_a_probar = ["raid/antes/"]
    elif tipo_filtro == "salio":
        subcarpetas_a_probar = ["raid/salio/"]
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


async def procesar_ciclo_raids(bot_instance, ruta_json, tipo_filtro):
    ahora_actual = datetime.now(ZONA_ARGENTINA)

    global HISTORIAL_ENVIADOS_CACHE
    limite_tiempo = ahora_actual - timedelta(hours=24)
    HISTORIAL_ENVIADOS_CACHE = {
        k: v for k, v in HISTORIAL_ENVIADOS_CACHE.items() if v > limite_tiempo
    }

    if tipo_filtro == "antes":
        filtro_activo = FILTRO_PUBLICAR_RAIDS_ANTES
        nombre_filtro_log = "antes"
        canal_id = getattr(config, "ENVIAR_MENSAJE_CHANNEL_ID", None)
    elif tipo_filtro == "salio":
        filtro_activo = FILTRO_PUBLICAR_RAIDS_SALIO
        nombre_filtro_log = "salio"
        canal_id = getattr(config, "ENVIAR_MENSAJE_CHANNEL_ID", None)
    else:
        filtro_activo = FILTRO_PUBLICAR_RAIDS
        nombre_filtro_log = "principal"
        canal_id = getattr(config, "MENSAJE_CLAN_CHANNEL_ID", None)
    
    fuente_bankgothic = getattr(config, "FUENTE_BANKGOTHIC", None)
    
    if not canal_id:
        return

    channel = bot_instance.get_channel(canal_id)
    if not channel:
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

        raids_especiales_dragones = {"valakas", "antharas", "fafureon"}
        datos_procesados = []

        for jefe in datos_horario:
            nombre_jefe = jefe.get("nombre", jefe.get("nombre_imagen", ""))
            nivel_jefe = jefe.get("nivel", None)
            
            if not debe_publicar_raid(nombre_jefe, nivel_jefe, filtro_usado=filtro_activo):
                continue
                
            nombre_crudo = nombre_jefe.strip()
            nombre_base_limpio = "".join(c for c in nombre_crudo if c.isalnum()).lower()
            
            if not nombre_base_limpio:
                continue
                
            registro = jefe.copy()
            estado = registro.get("estado", "").upper()
            tiempo_str = registro.get("tiempo_str", "-")
            es_vivo = (estado == "VIVO" or estado == "ALIVE" or registro.get("es_vivo", False))
            
            dt_obj = None
            if tiempo_str and tiempo_str != "-":
                try:
                    dt_obj = datetime.strptime(tiempo_str, "%d/%m/%Y %H:%M").replace(tzinfo=ZONA_ARGENTINA)
                except ValueError:
                    pass

            if not dt_obj and not es_vivo:
                continue

            # ==========================================
            # SERVICIO 1: ANTES (Reglas actualizadas)
            # ==========================================
            if tipo_filtro == "antes":
                if es_vivo or not dt_obj:
                    continue
                
                # Validación estricta: Solo procesar si el raid ocurre estrictamente el día de HOY
                if dt_obj.date() != ahora_actual.date():
                    continue

                # Si es jefe especial random, se publica a la hora exacta. Si es del resto de 60+, 10 minutos antes.
                if nombre_base_limpio in JEFS_ESPECIALES_RANDOM:
                    tiempo_objetivo = dt_obj
                else:
                    tiempo_objetivo = dt_obj - timedelta(minutes=10)

                diferencia_segundos = (ahora_actual - tiempo_objetivo).total_seconds()
                clave_id = f"{nombre_base_limpio}_antes_{dt_obj.strftime('%Y%m%d_%H%M')}"
                
                # Ventana de control de 5 minutos (300 segundos) y anti-duplicados
                if 0 <= diferencia_segundos < 300 and clave_id not in HISTORIAL_ENVIADOS_CACHE:
                    registro["nombre_imagen_base"] = f"{nombre_base_limpio}1"
                    datos_procesados.append(registro)
                    HISTORIAL_ENVIADOS_CACHE[clave_id] = ahora_actual
                continue

            # SERVICIO 2: SALIÓ
            elif tipo_filtro == "salio":
                if nombre_base_limpio in JEFS_ESPECIALES_RANDOM:
                    if es_vivo:
                        clave_id_salio = f"{nombre_base_limpio}_salio_{ahora_actual.strftime('%Y%m%d_%H')}"
                        if clave_id_salio not in HISTORIAL_ENVIADOS_CACHE:
                            registro["nombre_imagen_base"] = nombre_base_limpio
                            datos_procesados.append(registro)
                            HISTORIAL_ENVIADOS_CACHE[clave_id_salio] = ahora_actual
                else:
                    if dt_obj:
                        diferencia_segundos = (ahora_actual - dt_obj).total_seconds()
                        clave_id_salio = f"{nombre_base_limpio}_salio_{dt_obj.strftime('%Y%m%d_%H%M')}"
                        
                        if 0 <= diferencia_segundos < 300 and clave_id_salio not in HISTORIAL_ENVIADOS_CACHE:
                            registro["nombre_imagen_base"] = nombre_base_limpio
                            datos_procesados.append(registro)
                            HISTORIAL_ENVIADOS_CACHE[clave_id_salio] = ahora_actual
                continue

            # SERVICIO 3: PRINCIPAL
            else:
                if nombre_base_limpio in raids_especiales_dragones:
                    if not dt_obj:
                        continue
                    
                    fecha_raid_dia = dt_obj.date()
                    fecha_dia_antes = fecha_raid_dia - timedelta(days=1)
                    
                    # 1) Día antes a las 10:00 AM (resta 30 min)
                    dt_10am_dia_raid = datetime.combine(fecha_raid_dia, datetime.min.time(), tzinfo=ZONA_ARGENTINA).replace(hour=10, minute=0)
                    diferencia_seg_h = (ahora_actual - dt_10am_dia_raid).total_seconds()
                    clave_id_h = f"{nombre_base_limpio}_h_{dt_obj.strftime('%Y%m%d_%H%M')}"
                    if 0 <= diferencia_seg_h < 300 and clave_id_h not in HISTORIAL_ENVIADOS_CACHE:
                        reg_h = registro.copy()
                        reg_h["tiempo_str_final"] = (dt_obj - timedelta(minutes=30)).strftime("%H:%M")
                        reg_h["nombre_imagen_base"] = f"{nombre_base_limpio}h"
                        datos_procesados.append(reg_h)
                        HISTORIAL_ENVIADOS_CACHE[clave_id_h] = ahora_actual

                    # 2) Día antes a las 10:00 AM (resta 30 min)
                    dt_10am_dia_antes = datetime.combine(fecha_dia_antes, datetime.min.time(), tzinfo=ZONA_ARGENTINA).replace(hour=10, minute=0)
                    diferencia_seg_m = (ahora_actual - dt_10am_dia_antes).total_seconds()
                    clave_id_m = f"{nombre_base_limpio}_m_{dt_obj.strftime('%Y%m%d_%H%M')}"
                    if 0 <= diferencia_seg_m < 300 and clave_id_m not in HISTORIAL_ENVIADOS_CACHE:
                        reg_m = registro.copy()
                        reg_m["tiempo_str_final"] = (dt_obj - timedelta(minutes=30)).strftime("%H:%M")
                        reg_m["nombre_imagen_base"] = f"{nombre_base_limpio}m"
                        datos_procesados.append(reg_m)
                        HISTORIAL_ENVIADOS_CACHE[clave_id_m] = ahora_actual

                    # 3) Mismo día a las 18:00 PM (Modificado: ahora también resta 30 min)
                    dt_18pm_dia_raid = datetime.combine(fecha_raid_dia, datetime.min.time(), tzinfo=ZONA_ARGENTINA).replace(hour=18, minute=0)
                    diferencia_seg_18 = (ahora_actual - dt_18pm_dia_raid).total_seconds()
                    clave_id_18 = f"{nombre_base_limpio}_18pm_{dt_obj.strftime('%Y%m%d_%H%M')}"
                    if 0 <= diferencia_seg_18 < 300 and clave_id_18 not in HISTORIAL_ENVIADOS_CACHE:
                        reg_18 = registro.copy()
                        reg_18["tiempo_str_final"] = (dt_obj - timedelta(minutes=30)).strftime("%H:%M")
                        reg_18["nombre_imagen_base"] = nombre_base_limpio
                        datos_procesados.append(reg_18)
                        HISTORIAL_ENVIADOS_CACHE[clave_id_18] = ahora_actual
                else:
                    if dt_obj and not es_vivo:
                        if dt_obj.date() == ahora_actual.date():
                            if 18 <= dt_obj.hour <= 23:
                                fecha_raid_dia = dt_obj.date()
                                t_actual = ahora_actual.time()
                                if datetime.strptime("13:50", "%H:%M").time() <= t_actual <= datetime.strptime("14:50", "%H:%M").time():
                                    clave_id_pub = f"{nombre_base_limpio}_tarde_{fecha_raid_dia.strftime('%Y%m%d')}"
                                    if clave_id_pub not in HISTORIAL_ENVIADOS_CACHE:
                                        reg_tarde = registro.copy()
                                        reg_tarde["tiempo_str_final"] = dt_obj.strftime("%H:%M")
                                        reg_tarde["nombre_imagen_base"] = nombre_base_limpio
                                        datos_procesados.append(reg_tarde)
                                        HISTORIAL_ENVIADOS_CACHE[clave_id_pub] = ahora_actual
                    continue

        if not datos_procesados:
            return

        try:
            font_hora = ImageFont.truetype(fuente_bankgothic, 150) if fuente_bankgothic else ImageFont.load_default()
        except Exception:
            font_hora = ImageFont.load_default()

        for jefe in datos_procesados:
            nombre_imagen_base = jefe.get("nombre_imagen_base")
            ruta_imagen = obtener_imagen_raid(catalogo_raids, nombre_imagen_base, tema=TEMA_ACTIVO, tipo_filtro=tipo_filtro)
            
            if not ruta_imagen:
                continue
                
            img = Image.open(ruta_imagen).convert("RGBA")
            ancho_img, alto_img = img.size

            if tipo_filtro in ["antes", "salio"]:
                with io.BytesIO() as image_binary:
                    img.convert("RGB").save(image_binary, "PNG")
                    image_binary.seek(0)
                    await channel.send(file=discord.File(image_binary, filename=f"raid_{nombre_imagen_base}.png"))
                continue

            texto_hora = jefe.get("tiempo_str_final", "")
            if texto_hora != "VIVO" and texto_hora != "-":
                draw_temp = ImageDraw.Draw(img)
                bbox = draw_temp.textbbox((0, 0), texto_hora, font=font_hora)
                ancho_texto = bbox[2] - bbox[0]
                
                x = POS_X if POS_X is not None else (ancho_img - ancho_texto) / 2
                y = POS_Y if POS_Y is not None else (alto_img - 145)
                
                capa_resplandor = Image.new("RGBA", img.size, (0, 0, 0, 0))
                draw_resplandor = ImageDraw.Draw(capa_resplandor)
                draw_resplandor.text((x, y), texto_hora, font=font_hora, fill=(0, 0, 0, 0), stroke_width=6, stroke_fill=(255, 30, 30, 220))
                capa_resplandor = capa_resplandor.filter(ImageFilter.GaussianBlur(radius=3))

                capa_texto = Image.new("RGBA", img.size, (0, 0, 0, 0))
                draw_capa = ImageDraw.Draw(capa_texto)
                draw_capa.text((x + 4, y + 4), texto_hora, font=font_hora, fill=(0, 0, 0, 200))
                draw_capa.text((x, y), texto_hora, font=font_hora, fill=(255, 255, 255, 255), stroke_width=4, stroke_fill=(230, 0, 38, 255))
                
                ruta_textura_metal = getattr(config, "TEXTURA_METAL", None)
                if ruta_textura_metal and os.path.exists(ruta_textura_metal):
                    textura_metal = Image.open(ruta_textura_metal).convert("RGBA").resize((ancho_img, alto_img), Image.Resampling.LANCZOS)
                else:
                    textura_metal = Image.new("RGBA", (ancho_img, alto_img), (140, 145, 150, 255))
                
                capa_interior_pura = Image.new("RGBA", img.size, (0, 0, 0, 0))
                ImageDraw.Draw(capa_interior_pura).text((x, y), texto_hora, font=font_hora, fill=(255, 255, 255, 255))
                textura_recortada = Image.composite(textura_metal, Image.new("RGBA", img.size, (0, 0, 0, 0)), capa_interior_pura)
                
                img.alpha_composite(capa_resplandor)
                img.alpha_composite(capa_texto)
                img.alpha_composite(textura_recortada)
            
            with io.BytesIO() as image_binary:
                img.convert("RGB").save(image_binary, "PNG")
                image_binary.seek(0)
                await channel.send(file=discord.File(image_binary, filename=f"raid_{nombre_imagen_base}.png"))

    except Exception as e:
        logger.error(f"❌ Error crítico en salida_raid [{nombre_filtro_log}]: {e}")


# ==========================================
# BUCLE PERMANENTE EN SEGUNDO PLANO
# ==========================================
async def iniciar_monitoreo_permanente(bot_instance, ruta_json="horarios.json", intervalo_segundos=30):
    logger.info(f"🔄 Bucle permanente de monitoreo de Raids iniciado. Intervalo: {intervalo_segundos}s")
    
    await bot_instance.wait_until_ready()

    while not bot_instance.is_closed():
        try:
            for tipo in ["principal", "antes", "salio"]:
                await procesar_ciclo_raids(bot_instance, ruta_json, tipo)
        except Exception as e:
            logger.error(f"❌ Error en el ciclo de monitoreo permanente: {e}")
        
        await asyncio.sleep(intervalo_segundos)
