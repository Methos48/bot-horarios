import logging
import re
import os
import io
import json
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

# Importaciones opcionales protegidas
try:
    from PIL import Image, ImageEnhance, ImageOps
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

# Lista oficial de jefes permitidos
NOMBRES_OFICIALES_JEFES = [
    "Valakas",
    "Balrog",
    "Core",
    "Orfen",
    "Antharas",
    "Electrical",
    "Baium",
    "Zaken",
    "Frintezza",
    "Fafureon",
    "Queen Ant",
    "Freya",
    "Zariche",
    "Flame of Splendor Barakiel"
]

def _obtener_zona_horaria():
    tz_str = "America/Argentina/Buenos_Aires"
    if config and hasattr(config, "TZ"):
        tz_str = config.TZ
    try:
        return ZoneInfo(tz_str)
    except Exception:
        return ZoneInfo("UTC")

ZONA_ARGENTINA = _obtener_zona_horaria()

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
            
            try:
                imagen_bytes_original = await attachment.read()
            except Exception as e_dl:
                logger.error(f"❌ Error descargando adjunto {filename}: {e_dl}")
                continue

            if not imagen_bytes_original:
                continue

            # 🚀 Preprocesamiento optimizado para texto rojo/verde y fuentes pixeladas
            imagen_bytes = await asyncio.to_thread(_preprocesar_imagen, imagen_bytes_original)
            
            mime_map = {
                'png': 'image/png',
                'jpg': 'image/jpeg',
                'jpeg': 'image/jpeg',
                'webp': 'image/webp'
            }
            mime_type = mime_map.get(ext, 'image/png')
            
            registros_imagen = []

            # --- CAPA 1: OCR Local con Tesseract ---
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

    if imagenes_procesadas_con_exito and todos_los_registros:
        try:
            await message.delete()
            logger.info("🗑️ Mensaje con imágenes eliminado limpiamente del canal.")
        except Exception as e_del:
            logger.warning(f"⚠️ No se pudo eliminar el mensaje original: {e_del}")

    return _consolidar_y_ordenar_registros(todos_los_registros)


def _preprocesar_imagen(imagen_bytes):
    """
    Optimización visual para imágenes oscuras con texto rojo/verde pixelado.
    Reescala 3x y binariza para resaltar el texto ante Tesseract.
    """
    if not PIL_DISPONIBLE:
        return imagen_bytes
    try:
        img = Image.open(io.BytesIO(imagen_bytes)).convert('RGB')
        
        # 1. Reescalar 3x con NEAREST para agrandar la fuente pixelada sin desenfocar
        w, h = img.size
        img = img.resize((w * 3, h * 3), Image.NEAREST)
        
        # 2. Convertir a escala de grises
        gray = img.convert('L')
        
        # 3. Umbral (Thresholding): El fondo oscuro pasa a blanco y el texto brillante a negro
        # Texto rojo/verde/amarillo tiene valores > 35 en 'L', el fondo oscuro es < 25
        threshold = 35
        fn = lambda x: 0 if x > threshold else 255
        binarizada = gray.point(fn, mode='1')

        output_io = io.BytesIO()
        binarizada.save(output_io, format='PNG')
        output_io.seek(0)
        return output_io.getvalue()
    except Exception as e:
        logger.warning(f"⚠️ Error en preprocesamiento visual, usando bytes originales: {e}")
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
    return _parsear_texto_crudo(texto_crudo)


def _procesar_con_gemini(imagen_bytes, mime_type):
    if not client:
        return []
    
    prompt = (
        "Analiza esta imagen de Raid Bosses de Lineage II. "
        "Devuelve un arreglo JSON estricto con los jefes encontrados. Cada objeto debe tener:\n"
        "- \"nombre\": Nombre exacto del jefe (ej: \"Balrog\", \"Orfen\", \"Flame of Splendor Barakiel\", \"Electrical\", etc.)\n"
        "- \"tiempo_str\": La línea completa de horario o estado (ej: \"VIVO\", \"Entre 03:30 y 04 hs (ARG)\", \"Sabado 26/09 entre 11:30 y 12 hs (ARG)\").\n"
        "Si una línea no contiene datos válidos o es un título, ignórala. Responde SOLO con el JSON válido."
    )
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[types.Part.from_bytes(data=imagen_bytes, mime_type=mime_type), prompt]
        )
        if response and hasattr(response, "text"):
            match_json = re.search(r'\[.*\]', response.text, re.DOTALL)
            if match_json:
                datos = json.loads(match_json.group(0))
                registros = []
                zona_actual = _obtener_zona_horaria()
                for item in datos:
                    nombre = item.get("nombre", "")
                    tiempo = item.get("tiempo_str", "")
                    reg = _normalizar_registro(nombre, tiempo, zona_actual)
                    if reg:
                        registros.append(reg)
                return registros
    except Exception as e:
        logger.warning(f"⚠️ Error en API Gemini: {e}")
    return []


def _normalizar_registro(nombre_crudo, resto, zona_actual):
    """
    Valida, normaliza nombres y parsea correctamente fechas y horas sin interferencia.
    """
    if not nombre_crudo or not resto or resto in ["-", "", "None", "---"]:
        return None

    nombre_lower = nombre_crudo.lower()

    # Regla de Exclusión Barakiel
    if "barakiel" in nombre_lower and "flame of splendor" not in nombre_lower:
        return None

    # Mapeo oficial
    nombre_limpio = None
    if "balrog" in nombre_lower:
        nombre_limpio = "Balrog"
    elif "electrical" in nombre_lower or "execution" in nombre_lower:
        nombre_limpio = "Electrical"
    else:
        for oficial in NOMBRES_OFICIALES_JEFES:
            if oficial.lower() in nombre_lower:
                nombre_limpio = oficial
                break

    if not nombre_limpio:
        return None

    es_vivo = "alive" in resto.lower() or "vivo" in resto.lower()
    ahora_local = datetime.now(zona_actual)
    año_actual = ahora_local.year

    match_fecha = re.search(r'(\d{1,2})/(\d{1,2})', resto)

    # 🛠️ FIX CLAVE: Eliminar la fecha del resto antes de extraer las horas
    resto_sin_fecha = re.sub(r'\d{1,2}/\d{1,2}', '', resto)
    todas_las_horas = re.findall(r'(\d{1,2})(?::(\d{2}))?', resto_sin_fecha)

    hora_str = "00:00"
    tiene_tiempo = False

    if todas_las_horas:
        tiene_tiempo = True
        h1_num, m1_str = todas_las_horas[0]
        h1 = int(h1_num)
        m1 = int(m1_str) if m1_str else 0
        hora_str = f"{h1:02d}:{m1:02d}"

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
        return None

    tiempo_final_registro = "VIVO" if es_vivo else tiempo_str_estandar

    return {
        "nombre": nombre_limpio,
        "tiempo_str": tiempo_final_registro,
        "estado": "VIVO" if es_vivo else "PROGRAMADO",
        "es_vivo": es_vivo,
        "datetime": dt
    }


def _parsear_texto_crudo(texto_crudo):
    """
    Parseo por detección de nombres oficializados para evitar desfases por encabezados.
    """
    if not texto_crudo or not isinstance(texto_crudo, str):
        return []

    try:
        lineas = [l.strip() for l in texto_crudo.split('\n') if l.strip()]
        registros = []
        zona_actual = _obtener_zona_horaria()

        idx = 0
        while idx < len(lineas):
            linea = lineas[idx]
            
            # Buscar si la línea actual coincide o contiene un nombre conocido
            nombre_coincidente = None
            for oficial in NOMBRES_OFICIALES_JEFES + ["balrog devourer", "execution electrical"]:
                if oficial.lower() in linea.lower():
                    nombre_coincidente = linea
                    break

            if nombre_coincidente and idx + 1 < len(lineas):
                resto = lineas[idx + 1]
                reg = _normalizar_registro(nombre_coincidente, resto, zona_actual)
                if reg:
                    registros.append(reg)
                idx += 2
            elif "|" in linea:
                partes = linea.split("|", 1)
                reg = _normalizar_registro(partes[0].strip(), partes[1].strip(), zona_actual)
                if reg:
                    registros.append(reg)
                idx += 1
            else:
                idx += 1

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
