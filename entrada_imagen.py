import logging
import re
import os
import io
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

# Importaciones opcionales protegidas
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

# Intentar importar Gemini de forma segura
GEMINI_DISPONIBLE = False
try:
    from google import genai
    from google.genai import types
    GEMINI_DISPONIBLE = True
except ImportError:
    pass

try:
    import config
except ImportError:
    config = None

logger = logging.getLogger("EntradaPagina")

# Configuración de zona horaria segura con fallback
def _obtener_zona_horaria():
    tz_str = "America/Argentina/Buenos_Aires"
    if config and hasattr(config, "TZ"):
        tz_str = config.TZ
    try:
        return ZoneInfo(tz_str)
    except Exception:
        return ZoneInfo("UTC")

ZONA_ARGENTINA = _obtener_zona_horaria()

# Inicializar cliente de Gemini de forma segura
client = None
if GEMINI_DISPONIBLE:
    try:
        api_key = None
        if config and hasattr(config, "GEMINI_API_KEY"):
            api_key = config.GEMINI_API_KEY
        if not api_key:
            api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            client = genai.Client(api_key=api_key)
    except Exception as e:
        logger.warning(f"⚠️ No se pudo inicializar el cliente de Gemini: {e}")


async def procesar_mensaje_imagenes(message):
    """
    Procesa las imágenes adjuntas con un sistema blindado de 3 capas.
    Garantiza que NUNCA se produzca una excepción no controlada que rompa el bot.
    """
    if not message or not getattr(message, "attachments", None):
        return []

    todos_los_registros = []
    imagenes_procesadas_con_exito = False

    for attachment in message.attachments:
        try:
            filename = getattr(attachment, "filename", "desconocido").lower()
            ext = filename.split('.')[-1] if '.' in filename else ''
            
            if ext not in ['png', 'jpg', 'jpeg', 'webp']:
                continue

            logger.info(f"🖼️ [Blindado] Procesando imagen: {filename}")
            
            # Descarga protegida de bytes
            try:
                imagen_bytes_original = await attachment.read()
            except Exception as e_dl:
                logger.error(f"❌ Error descargando adjunto {filename}: {e_dl}")
                continue

            if not imagen_bytes_original:
                continue

            # 🚀 Preprocesamiento visual seguro
            imagen_bytes = await asyncio.to_thread(_preprocesar_imagen, imagen_bytes_original)
            
            mime_map = {
                'png': 'image/png',
                'jpg': 'image/jpeg',
                'jpeg': 'image/jpeg',
                'webp': 'image/webp'
            }
            mime_type = mime_map.get(ext, 'image/png')
            
            registros_imagen = []

            # --- CAPA 1: OCR Local con Tesseract (Opción Principal y Rápida) ---
            if OCR_LOCAL_DISPONIBLE:
                try:
                    logger.info("🔍 [Capa 1] Ejecutando OCR Local (Tesseract)...")
                    registros_imagen = await asyncio.to_thread(_procesar_con_tesseract_local, imagen_bytes)
                except Exception as e_ocr:
                    logger.warning(f"⚠️ Capa 1 falló (Tesseract): {e_ocr}")

            # --- CAPA 2: Respaldo heurístico por Regex sobre Tesseract ---
            if not registros_imagen and OCR_LOCAL_DISPONIBLE:
                try:
                    logger.info("🔄 [Capa 2] Activando Respaldo Heurístico por Regex...")
                    img_pil = Image.open(io.BytesIO(imagen_bytes))
                    texto_crudo_tesseract = pytesseract.image_to_string(img_pil)
                    registros_imagen = _procesar_capa_2_emergencia(texto_crudo_tesseract)
                except Exception as e_reg:
                    logger.warning(f"⚠️ Capa 2 falló (Regex): {e_reg}")

            # --- CAPA 3: Gemini (Respaldo Final en la nube) ---
            if not registros_imagen and GEMINI_DISPONIBLE and client:
                intentos = 0
                max_intentos = 2
                while not registros_imagen and intentos < max_intentos:
                    intentos += 1
                    try:
                        logger.info(f"🤖 [Capa 3] Activando Respaldo Gemini - Intento {intentos}...")
                        registros_imagen = await asyncio.to_thread(_procesar_con_gemini, imagen_bytes, mime_type)
                    except Exception as e_gemini:
                        logger.warning(f"⚠️ Intento {intentos}: Capa 3 falló (Gemini): {e_gemini}")
                        await asyncio.sleep(1)

            if registros_imagen:
                todos_los_registros.extend(registros_imagen)
                imagenes_procesadas_con_exito = True

        except Exception as e_img:
            logger.error(f"❌ Error crítico manejando imagen individual: {e_img}", exc_info=True)

    # Borrar mensaje original solo si se procesó con éxito
    if imagenes_procesadas_con_exito and todos_los_registros:
        try:
            await message.delete()
            logger.info("🗑️ Mensaje con imágenes eliminado limpiamente del canal.")
        except Exception as e_del:
            logger.warning(f"⚠️ No se pudo eliminar el mensaje original: {e_del}")

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
        logger.warning(f"⚠️ Error menor en preprocesamiento visual, usando bytes originales: {e}")
        return imagen_bytes


def _procesar_con_tesseract_local(imagen_bytes):
    try:
        imagen = Image.open(io.BytesIO(imagen_bytes))
        config_tesseract = r'--oem 3 --psm 6'
        texto_extraido = pytesseract.image_to_string(imagen, config=config_tesseract)
        return _parsear_texto_crudo(texto_extraido)
    except Exception as e:
        logger.warning(f"⚠️ Excepción en motor Tesseract: {e}")
        return []


def _procesar_capa_2_emergencia(texto_crudo):
    registros = []
    if not texto_crudo:
        return registros
    try:
        zona_actual = _obtener_zona_horaria()
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
    except Exception as e:
        logger.warning(f"⚠️ Error en respaldo Regex: {e}")
    return registros


def _procesar_con_gemini(imagen_bytes, mime_type):
    if not client:
        return []
    prompt = (
        "Analiza esta imagen que contiene información u horarios de Raid Bosses de Lineage II. "
        "Extrae cada fila o bloque identificando el nombre del jefe y su horario o estado correspondiente. "
        "Reglas estrictas:\n"
        "1. Si es una tabla por columnas, extrae el horario de la columna de Argentina/Chile.\n"
        "2. Devuelve estrictamente una línea por cada jefe con el formato: `Nombre del Jefe | Horario o Estado` (Ejemplo: Queen Ant | 16:30 o Balrog | VIVO).\n"
        "3. Si una línea tiene un guion (-) o carece de datos válidos, ignórala.\n"
        "4. No agregues saludos, explicaciones ni bloques markdown. Solo las líneas de datos."
    )
    try:
        response = client.models.generate_content(
            model='gemini-3.8-flash',
            contents=[types.Part.from_bytes(data=imagen_bytes, mime_type=mime_type), prompt]
        )
        if response and hasattr(response, "text"):
            return _parsear_texto_crudo(response.text)
    except Exception as e:
        logger.warning(f"⚠️ Error en API Gemini: {e}")
    return []


def _parsear_texto_crudo(texto_crudo):
    if not texto_crudo or not isinstance(texto_crudo, str):
        return []
        
    try:
        texto_crudo = re.sub(r'```[a-zA-Z]*\s*', '', texto_crudo)
        texto_crudo = re.sub(r'```\s*', '', texto_crudo)
        
        lineas = texto_crudo.strip().split('\n')
        registros = []
        zona_actual = _obtener_zona_horaria()
        ahora_local = datetime.now(zona_actual)
        año_actual = ahora_local.year

        for linea in lineas:
            try:
                linea = linea.strip()
                if not linea or "|" not in linea:
                    continue
                    
                partes = linea.split("|", 1)
                if len(partes) < 2:
                    continue
                    
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
            except Exception as e_linea:
                logger.debug(f"Línea descartada por formato inválido: {e_linea}")
                continue

        return registros
    except Exception as e_parse:
        logger.warning(f"⚠️ Error general parseando texto crudo: {e_parse}")
        return []


def _consolidar_y_ordenar_registros(registros):
    if not registros or not isinstance(registros, list):
        return []
    try:
        unicos = {}
        for r in registros:
            try:
                nombre_key = str(r.get("nombre", "")).strip().lower()
                if not nombre_key or r.get("tiempo_str") == "-":
                    continue
                    
                if nombre_key not in unicos:
                    unicos[nombre_key] = r
                else:
                    actual = unicos[nombre_key]
                    if r.get("es_vivo") and not actual.get("es_vivo"):
                        unicos[nombre_key] = r
                    elif not actual.get("es_vivo") and not r.get("es_vivo") and r.get("datetime", datetime.max) < actual.get("datetime", datetime.max):
                        unicos[nombre_key] = r
            except Exception:
                continue

        lista_final = list(unicos.values())
        
        # Ordenamiento seguro ante nulos o tipos extraños
        registros_ordenados = sorted(
            lista_final, 
            key=lambda x: (
                not x.get("es_vivo", False), 
                getattr(x.get("datetime"), "date", lambda: datetime.min.date())(), 
                getattr(x.get("datetime"), "time", lambda: datetime.min.time())()
            )
        )
        
        return [
            {
                "nombre": str(r.get("nombre", "Desconocido")), 
                "tiempo_str": str(r.get("tiempo_str", "-")), 
                "datetime": r.get("datetime"), 
                "es_vivo": bool(r.get("es_vivo", False)),
                "estado": str(r.get("estado", "PROGRAMADO"))
            } 
            for r in registros_ordenados
        ]
    except Exception as e_cons:
        logger.error(f"❌ Error consolidando registros: {e_cons}")
        return []
