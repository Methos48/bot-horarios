import logging
import re
import os
import io
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from google import genai
from google.genai import types
import config

try:
    from PIL import Image, ImageEnhance
    PIL_DISPONIBLE = True
except ImportError:
    PIL_DISPONIBLE = False

try:
    import pytesseract
    OCR_LOCAL_DISPONIBLE = True
except ImportError:
    OCR_LOCAL_DISPONIBLE = False

logger = logging.getLogger("EntradaPagina")

ZONA_ARGENTINA = ZoneInfo(getattr(config, "TZ", "America/Argentina/Buenos_Aires"))
client = genai.Client(api_key=getattr(config, "GEMINI_API_KEY", os.getenv("GEMINI_API_KEY")))

async def procesar_mensaje_imagenes(message):
    if not message.attachments:
        return []

    todos_los_registros = []
    imagenes_procesadas_con_exito = False

    for attachment in message.attachments:
        ext = attachment.filename.split('.')[-1].lower()
        if ext in ['png', 'jpg', 'jpeg', 'webp']:
            logger.info(f"🖼️ Imagen detectada para procesamiento: {attachment.filename}")
            try:
                imagen_bytes_original = await attachment.read()
                
                # 🚀 PREPROCESAMIENTO VISUAL (Mejora nitidez para Tesseract)
                imagen_bytes = await asyncio.to_thread(_preprocesar_imagen, imagen_bytes_original)
                
                mime_map = {
                    'png': 'image/png',
                    'jpg': 'image/jpeg',
                    'jpeg': 'image/jpeg',
                    'webp': 'image/webp'
                }
                mime_type = mime_map.get(ext, 'image/png')
                
                registros_imagen = []

                # --- CAPA 1: OCR Local con Tesseract (Opción Principal) ---
                if OCR_LOCAL_DISPONIBLE:
                    logger.info("🔍 Activando Capa 1: OCR Local (Tesseract)...")
                    try:
                        registros_imagen = await asyncio.to_thread(_procesar_con_tesseract_local, imagen_bytes)
                    except Exception as e_ocr:
                        logger.warning(f"⚠️ Capa 1 (Tesseract) falló: {e_ocr}")

                # --- CAPA 2: Respaldo heurístico por Regex sobre Tesseract ---
                if not registros_imagen and OCR_LOCAL_DISPONIBLE:
                    logger.info("🔄 Activando Capa 2: Respaldo Heurístico por Regex...")
                    try:
                        texto_crudo_tesseract = pytesseract.image_to_string(Image.open(io.BytesIO(imagen_bytes)))
                        registros_imagen = _procesar_capa_3_emergencia(texto_crudo_tesseract)
                    except Exception as e_reg:
                        logger.warning(f"⚠️ Capa 2 (Regex) falló: {e_reg}")

                # --- CAPA 3: Gemini (Respaldo Final si el OCR local no detectó nada) ---
                intentos = 0
                max_intentos = 2
                while not registros_imagen and intentos < max_intentos:
                    intentos += 1
                    logger.info(f"🤖 Activando Capa 3 (Respaldo Gemini) - Intento {intentos}...")
                    try:
                        registros_imagen = await asyncio.to_thread(_procesar_con_gemini, imagen_bytes, mime_type)
                    except Exception as e_gemini:
                        logger.warning(f"⚠️ Intento {intentos}: Capa 3 (Gemini) falló: {e_gemini}")
                        await asyncio.sleep(2)

                if registros_imagen:
                    todos_los_registros.extend(registros_imagen)
                    imagenes_procesadas_con_exito = True

            except Exception as e:
                logger.error(f"Error crítico procesando la imagen {attachment.filename}: {e}")

    if imagenes_procesadas_con_exito and todos_los_registros:
        try:
            await message.delete()
            logger.info("🗑️ Mensaje con imágenes eliminado limpiamente del canal.")
        except Exception as e:
            logger.error(f"No se pudo eliminar el mensaje: {e}")

    return _consolidar_y_ordenar_registros(todos_los_registros)


def _preprocesar_imagen(imagen_bytes):
    if not PIL_DISPONIBLE:
        return imagen_bytes
    try:
        imagen = Image.open(io.BytesIO(imagen_bytes)).convert('L')
        enhancer = ImageEnhance.Contrast(imagen)
        imagen = enhancer.enhance(2.2)
        
        output_io = io.BytesIO()
        imagen.save(output_io, format='PNG')
        output_io.seek(0)
        return output_io.getvalue()
    except Exception as e:
        logger.warning(f"⚠️ Error en preprocesamiento visual, usando original: {e}")
        return imagen_bytes


def _procesar_con_tesseract_local(imagen_bytes):
    imagen = Image.open(io.BytesIO(imagen_bytes))
    config_tesseract = r'--oem 3 --psm 6'
    texto_extraido = pytesseract.image_to_string(imagen, config=config_tesseract)
    return _parsear_texto_crudo(texto_extraido)


def _procesar_capa_3_emergencia(texto_crudo):
    registros = []
    zona_actual = ZoneInfo(getattr(config, "TZ", "America/Argentina/Buenos_Aires"))
    lineas = texto_crudo.split('\n')
    for linea in lineas:
        if re.search(r'\d{1,2}:\d{2}', linea):
            partes = re.split(r'[-–|]', linea)
            if len(partes) >= 2:
                nombre = partes[0].strip()
                resto = partes[1].strip()
                if nombre:
                    registros.append({
                        "nombre": nombre,
                        "tiempo_str": resto,
                        "estado": "PROGRAMADO",
                        "es_vivo": False,
                        "datetime": datetime.now(zona_actual)
                    })
    return registros


def _procesar_con_gemini(imagen_bytes, mime_type):
    prompt = (
        "Analiza esta imagen que contiene información u horarios de Raid Bosses de Lineage II. "
        "Extrae cada fila o bloque identificando el nombre del jefe y su horario o estado correspondiente. "
        "Reglas estrictas:\n"
        "1. Si es una tabla por columnas, extrae el horario de la columna de Argentina/Chile.\n"
        "2. Devuelve estrictamente una línea por cada jefe con el formato: `Nombre del Jefe | Horario o Estado` (Ejemplo: Queen Ant | 16:30 o Balrog | VIVO).\n"
        "3. Si una línea tiene un guion (-) o carece de datos válidos, ignórala.\n"
        "4. No agregues saludos, explicaciones ni bloques markdown. Solo las líneas de datos."
    )
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=[types.Part.from_bytes(data=imagen_bytes, mime_type=mime_type), prompt]
    )
    return _parsear_texto_crudo(response.text)


def _parsear_texto_crudo(texto_crudo):
    if not texto_crudo:
        return []
        
    texto_crudo = re.sub(r'```[a-zA-Z]*\s*', '', texto_crudo)
    texto_crudo = re.sub(r'```\s*', '', texto_crudo)
    
    lineas = texto_crudo.strip().split('\n')
    registros = []
    zona_actual = ZoneInfo(getattr(config, "TZ", "America/Argentina/Buenos_Aires"))
    ahora_local = datetime.now(zona_actual)
    año_actual = ahora_local.year

    for linea in lineas:
        linea = linea.strip()
        if not linea or "|" not in linea:
            continue
            
        partes = linea.split("|", 1)
        nombre_crudo = partes[0].strip()
        resto = partes[1].strip()

        if not nombre_crudo or resto in ["-", "", "None", "---"]:
            continue

        nombre_lower = nombre_crudo.lower()
        if "flame of splendor barakiel" in nombre_lower or "barakiel" in nombre_lower:
            continue
            
        if "balrog" in nombre_lower:
            nombre_limpio = "Balrog"
        elif "execution electrical" in nombre_lower or "electrical" in nombre_lower:
            nombre_limpio = "Electrical"
        else:
            nombre_limpio = nombre_crudo

        es_vivo = "alive" in resto.lower() or "vivo" in resto.lower()

        match_fecha = re.search(r'(\d{1,2})/(\d{1,2})', resto)
        match_hora = re.search(r'(\d{1,2}):(\d{2})', resto)
        
        if not match_hora:
            match_hora_simple = re.search(r'(?:entre\s+)?(\d{1,2})', resto, re.IGNORECASE)
            hora_str = f"{match_hora_simple.group(1).zfill(2)}:00" if match_hora_simple else "00:00"
            tiene_tiempo = bool(match_hora_simple)
        else:
            hora_str = f"{match_hora.group(1).zfill(2)}:{match_hora.group(2)}"
            tiene_tiempo = True

        if match_fecha:
            dia = int(match_fecha.group(1))
            mes = int(match_fecha.group(2))
            fecha_str = f"{dia:02d}/{mes:02d}/{año_actual}"
            tiempo_str_estandar = f"{fecha_str} {hora_str}"
            try:
                dt = datetime.strptime(tiempo_str_estandar, "%d/%m/%Y %H:%M").replace(tzinfo=zona_actual)
            except ValueError:
                dt = datetime.max.replace(tzinfo=zona_actual)
        elif tiene_tiempo and not es_vivo:
            try:
                h, m = map(int, hora_str.split(':'))
                dt = datetime(ahora_local.year, ahora_local.month, ahora_local.day, h, m, tzinfo=zona_actual)
                tiempo_str_estandar = dt.strftime("%d/%m/%Y %H:%M")
            except ValueError:
                dt = datetime.max.replace(tzinfo=zona_actual)
                tiempo_str_estandar = "-"
        else:
            dt = datetime.max.replace(tzinfo=zona_actual)
            tiempo_str_estandar = "-"

        if tiempo_str_estandar == "-" and not es_vivo:
            continue

        tiempo_final_registro = "VIVO" if es_vivo else tiempo_str_estandar

        registros.append({
            "nombre": nombre_limpio,
            "tiempo_str": tiempo_final_registro,
            "estado": "VIVO" if es_vivo else "PROGRAMADO",
            "es_vivo": es_vivo,
            "datetime": dt
        })

    return registros


def _consolidar_y_ordenar_registros(registros):
    unicos = {}
    for r in registros:
        nombre_key = r["nombre"].strip().lower()
        if not nombre_key or r["tiempo_str"] == "-":
            continue
            
        if nombre_key not in unicos:
            unicos[nombre_key] = r
        else:
            actual = unicos[nombre_key]
            if r["es_vivo"] and not actual["es_vivo"]:
                unicos[nombre_key] = r
            elif not actual["es_vivo"] and not r["es_vivo"] and r["datetime"] < actual["datetime"]:
                unicos[nombre_key] = r

    lista_final = list(unicos.values())
    registros_ordenados = sorted(
        lista_final, 
        key=lambda x: (not x["es_vivo"], x["datetime"].date(), x["datetime"].time())
    )
    
    return [
        {
            "nombre": r["nombre"], 
            "tiempo_str": r["tiempo_str"], 
            "datetime": r["datetime"], 
            "es_vivo": r["es_vivo"],
            "estado": r["estado"]
        } 
        for r in registros_ordenados
    ]
