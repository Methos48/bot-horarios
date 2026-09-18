import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo
import google.generativeai as genai
import config

logger = logging.getLogger("EntradaImagen")

# Definir la zona horaria estricta de Argentina
ZONA_ARGENTINA = ZoneInfo(getattr(config, "TZ", "America/Argentina/Buenos_Aires"))

# Configurar la API de Gemini con la credencial de config.py
if config.GEMINI_API_KEY:
    genai.configure(api_key=config.GEMINI_API_KEY)

def procesar_imagen_jefes(imagen_bytes):
    """
    Recibe los bytes de la imagen de Discord, usa Gemini para extraer los datos,
    aplica filtros, prioriza a los vivos ('Alive') al inicio y ordena el resto cronológicamente
    bajo hora argentina.
    """
    if not config.GEMINI_API_KEY:
        logger.error("No se encontró GEMINI_API_KEY en config.py para procesar la imagen.")
        return []

    try:
        logger.info("🤖 Enviando imagen de horarios a Gemini para extracción visual (OCR)...")
        
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = (
            "Analiza esta imagen de un juego MMORPG. Extrae cada jefe o evento junto con su horario o estado correspondiente. "
            "El formato visual muestra el nombre del jefe en una línea y debajo su fecha/hora (ej: 'Valakas' y 'Jueves 17/09 entre 22:30 y 23 hs (ARG)') "
            "o su estado ('Alive'). "
            "Devuelve los resultados en una lista de líneas limpias donde cada línea tenga el formato exacto: "
            "Nombre del Jefe | Fecha, Hora o Estado. "
            "No agregues texto introductorio, saludos ni explicaciones, solo los datos extraídos."
        )
        
        response = model.generate_content([
            prompt,
            {"mime_type": "image/png", "data": imagen_bytes}
        ])
        
        texto_extraido = response.text
        logger.info("✨ Texto extraído de la imagen con éxito. Procesando, filtrando y ordenando (Hora Argentina)...")
        
        return _limpiar_y_ordenar_datos_imagen(texto_extraido)

    except Exception as e:
        logger.error(f"Error procesando la imagen con la API de Gemini: {e}")
        return []

def _limpiar_y_ordenar_datos_imagen(texto_crudo):
    """
    Procesa el texto extraído:
    - Filtra y limpia nombres (Elimina Barakiel, cambia Balrog y Electrica).
    - Detecta si está 'Alive' para darle prioridad máxima (arriba de todo).
    - Procesa rangos horarios tomando estrictamente la primera hora con zona horaria de Argentina.
    - Ordena cronológicamente los que tienen fecha/hora.
    """
    lineas = texto_crudo.strip().split('\n')
    registros = []
    
    # Obtener el año actual referenciado en hora argentina
    año_actual = datetime.now(ZONA_ARGENTINA).year

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

        # --- APLICAR FILTROS DE NOMBRES ---
        # 1. Eliminar a Flame of Splendor Barakiel
        if "flame of splendor barakiel" in nombre_crudo.lower():
            continue
            
        # 2. Renombrar Balrog
        if "balrog devourer pvp" in nombre_crudo.lower() or "balrog" in nombre_crudo.lower():
            nombre_limpio = "Balrog"
        # 3. Renombrar Execution Electrical / Electrica
        elif "execution electrical pvp" in nombre_crudo.lower() or "electrical" in nombre_crudo.lower() or "electric" in nombre_crudo.lower():
            nombre_limpio = "Electrica"
        else:
            nombre_limpio = nombre_crudo

        # --- DETECTAR ESTADO "ALIVE" ---
        es_vivo = "alive" in resto.lower() or "vivo" in resto.lower()

        # --- EXTRAER HORA Y FECHA (Tomando siempre la PRIMERA hora si es un rango) ---
        match_fecha = re.search(r'(\d{1,2})/(\d{1,2})', resto)
        
        # Buscamos la primera aparición de hora (ej: 22:30 o 22 en "entre 22:30 y 23")
        match_hora = re.search(r'(\d{1,2}):(\d{2})', resto)
        if not match_hora:
            # Si no tiene minutos (ej: "entre 22 y 23 hs"), extraemos la primera hora numérica encontrada
            match_hora_simple = re.search(r'(?:entre\s+)?(\d{1,2})', resto, re.IGNORECASE)
            hora_str = f"{match_hora_simple.group(1).zfill(2)}:00" if match_hora_simple else "00:00"
        else:
            hora_str = f"{match_hora.group(1).zfill(2)}:{match_hora.group(2)}"

        if match_fecha:
            dia = int(match_fecha.group(1))
            mes = int(match_fecha.group(2))
            fecha_str = f"{dia:02d}/{mes:02d}/{año_actual}"
            tiempo_str = f"{fecha_str} {hora_str}"
            try:
                # Parsear y asignar de inmediato la zona horaria de Argentina
                dt = datetime.strptime(tiempo_str, "%d/%m/%Y %H:%M").replace(tzinfo=ZONA_ARGENTINA)
            except ValueError:
                dt = datetime.max.replace(tzinfo=ZONA_ARGENTINA)
        else:
            # Si no tiene fecha (ej: formato "Entre 18:30 y 19 hs" sin día específico)
            dt = datetime.max.replace(tzinfo=ZONA_ARGENTINA)
            tiempo_str = resto if resto else "-"

        registros.append({
            "nombre": nombre_limpio,
            "tiempo_str": resto if not es_vivo else "Alive",
            "es_vivo": es_vivo,
            "datetime": dt
        })

    # ORDENAMIENTO:
    # 1. Primero los que están VIVOS (es_vivo = True van arriba)
    # 2. Luego se ordenan cronológicamente por el datetime de la primera hora
    registros_ordenados = sorted(
        registros, 
        key=lambda x: (not x["es_vivo"], x["datetime"])
    )
    
    tabla_limpia = [{"nombre": r["nombre"], "tiempo_str": r["tiempo_str"], "datetime": r["datetime"], "es_vivo": r["es_vivo"]} for r in registros_ordenados]
    logger.info(f"Imagen procesada, priorizada y ordenada con éxito bajo hora argentina: {len(tabla_limpia)} registros.")
    return tabla_limpia
