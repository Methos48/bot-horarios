import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from google import genai
from google.genai import types
import os
import config
import asyncio

# Intento de importación opcional para la Capa 2 (OCR Local)
try:
    import pytesseract
    from PIL import Image
    import io
    OCR_LOCAL_DISPONIBLE = True
except ImportError:
    OCR_LOCAL_DISPONIBLE = False

logger = logging.getLogger("EntradaPagina")

ZONA_ARGENTINA = ZoneInfo(getattr(config, "TZ", "America/Argentina/Buenos_Aires"))
client = genai.Client(api_key=getattr(config, "GEMINI_API_KEY", os.getenv("GEMINI_API_KEY")))

async def procesar_mensaje_imagenes(message):
    """
    Verifica si el mensaje contiene imágenes, aplica el sistema en cascada 
    de forma asíncrona y consolida los resultados.
    """
    if not message.attachments:
        return []

    todos_los_registros = []
    imagenes_procesadas_con_exito = False

    for attachment in message.attachments:
        ext = attachment.filename.split('.')[-1].lower()
        if ext in ['png', 'jpg', 'jpeg', 'webp']:
            logger.info(f"🖼️ Imagen detectada para procesamiento en cascada: {attachment.filename}")
            try:
                imagen_bytes = await attachment.read()
                
                # Detectar mime_type correcto según la extensión
                mime_map = {
                    'png': 'image/png',
                    'jpg': 'image/jpeg',
                    'jpeg': 'image/jpeg',
                    'webp': 'image/webp'
                }
                mime_type = mime_map.get(ext, 'image/png')
                
                registros_imagen = []
                
                # --- SISTEMA EN CASCADA DE EXTRACCIÓN (Asíncrono para no bloquear Discord) ---
                
                # Opción 1: Intentar con Gemini AI (Envuelto en thread para evitar bloqueo)
                try:
                    registros_imagen = await asyncio.to_thread(_procesar_con_gemini, imagen_bytes, mime_type)
                except Exception as e_gemini:
                    logger.warning(f"⚠️ Capa 1 (Gemini) falló: {e_gemini}. Intentando capa alternativa...")

                # Opción 2: Si Gemini falla, usar OCR local (Tesseract en thread separado)
                if not registros_imagen and OCR_LOCAL_DISPONIBLE:
                    logger.info("🔄 Activando Capa 2: OCR Local (Tesseract)...")
                    try:
                        registros_imagen = await asyncio.to_thread(_procesar_con_tesseract_local, imagen_bytes)
                    except Exception as e_ocr:
                        logger.warning(f"⚠️ Capa 2 (Tesseract) falló: {e_ocr}.")

                if registros_imagen:
                    todos_los_registros.extend(registros_imagen)
                    imagenes_procesadas_con_exito = True

            except Exception as e:
                logger.error(f"Error crítico procesando la imagen {attachment.filename} en la cascada: {e}")

    if imagenes_procesadas_con_exito and todos_los_registros:
        try:
            await message.delete()
            logger.info("🗑️ Mensaje con múltiples imágenes eliminado limpiamente del canal.")
        except Exception as e:
            logger.error(f"No se pudo eliminar el mensaje de las imágenes: {e}")

    return _consolidar_y_ordenar_registros(todos_los_registros)

def _procesar_con_gemini(imagen_bytes, mime_type):
    """Capa 1: Extracción mediante la API de Gemini."""
    prompt = (
        "Analiza esta imagen de un juego MMORPG. Extrae cada jefe o evento junto con su horario o estado correspondiente. "
        "Devuelve los resultados en una lista de líneas limpias donde cada línea tenga el formato exacto: "
        "Nombre del Jefe | Fecha, Hora o Estado (ej: Valakas | Jueves 17/09 22:30 o Antharas | Alive). "
        "No agregues texto introductorio ni bloques de código markdown, solo los datos extraídos."
    )
    response = client.models.generate_content(
        model='gemini-3.6-flash', # Actualizado a un modelo estándar estable
        contents=[types.Part.from_bytes(data=imagen_bytes, mime_type=mime_type), prompt]
    )
    return _parsear_texto_crudo(response.text)

def _procesar_con_tesseract_local(imagen_bytes):
    """Capa 2: Respaldo local usando Tesseract OCR."""
    imagen = Image.open(io.BytesIO(imagen_bytes))
    texto_extraido = pytesseract.image_to_string(imagen)
    return _parsear_texto_crudo(texto_extraido)

def _parsear_texto_crudo(texto_crudo):
    """Procesa, limpia y normaliza el texto obtenido de cualquier capa."""
    if not texto_crudo:
        return []
        
    # Limpiar posibles bloques de código markdown que devuelva la IA
    texto_crudo = re.sub(r'```[a-zA-Z]*\s*', '', texto_crudo)
    texto_crudo = re.sub(r'```\s*', '', texto_crudo)
    
    lineas = texto_crudo.strip().split('\n')
    registros = []
    zona_actual = ZoneInfo(getattr(config, "TZ", "America/Argentina/Buenos_Aires"))
    ahora_local = datetime.now(zona_actual)
    año_actual = ahora_local.year

    for linea in lineas:
        linea = linea.strip()
        if not linea:
            continue
            
        if "|" in linea:
            partes = linea.split("|")
            nombre_crudo = partes[0].strip()
            resto = partes[1].strip()
        else:
            nombre_crudo = linea
            resto = ""

        nombre_lower = nombre_crudo.lower()

        if "flame of splendor barakiel" in nombre_lower or "barakiel" in nombre_lower:
            continue
            
        if "balrog" in nombre_lower:
            nombre_limpio = "Balrog"
        elif "execution electrical" in nombre_lower or "electrical" in nombre_lower or "electric" in nombre_lower:
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
            # Si hay hora pero no fecha explícita, asumimos el día de hoy
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
    """Consolida, elimina duplicados y ordena los registros finales asegurando unicidad."""
    unicos = {}
    for r in registros:
        nombre_key = r["nombre"].strip().lower()
        # Ignorar entradas vacías o inválidas
        if not nombre_key or r["tiempo_str"] in ["-", "", "None"] and not r["es_vivo"]:
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
