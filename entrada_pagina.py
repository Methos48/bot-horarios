import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from zoneinfo import ZoneInfo
from google import genai
from google.genai import types
import os
import config
import re

logger = logging.getLogger("EntradaPagina")

# Definir la zona horaria estricta de Argentina
ZONA_ARGENTINA = ZoneInfo(getattr(config, "TZ", "America/Argentina/Buenos_Aires"))

# Inicializar el cliente con el nuevo SDK de google-genai para imágenes
client = genai.Client(api_key=getattr(config, "GEMINI_API_KEY", os.getenv("GEMINI_API_KEY")))

# Diccionario de normalización de nombres de Raid Bosses y Epic Bosses
MAPEO_NOMBRES = {
    "ketra's chief brakki": "Ketra Brakki",
    "ketra's commander tayr": "Ketra Tayr",
    "ketra's hero hekaton": "Hekaton",
    "varka's commander mos": "Varka Mos",
    "varka's hero shadith": "Varka Shadith",
    "cherub galaxia": "Galaxia",
    "longhorn golkonda": "Golkonda",
    "fire of wrath shuriel": "Fire Shuriel",
    "hestia guardian deity of the hot springs": "Hestia",
    "last lesser giant glaki": "Last Glaki",
    "ocean flame ashakiel": "Ashakiel",
    "bloody empress decarbia": "Decarbia",
    "last lesser giant olkuth": "Last Olkuth",
    "palatanos of horrific power": "Palatanos",
    "antharas priest cloe": "Antharas Cloe",
    "water dragon seer sheshark": "Water Dragon",
    "eilhalder von hellmann": "Von Hellman",
    "immortal savior mardil": "Inmortal Mardil",
    "anakim's nemesis zakaron": "Anakim Zakaron",
    "fafurion's herald lokness": "Fafurion Lokness",
    "flame of splendor barakiel": "Barakiel",
    "palibati queen themis": "Palibati",
    "shilen's messenger cabrio": "Cabrio",
    "bloody priest rudelto": "Rudelto",
    "spirit of andras the betrayer": "Betrayer",
    "kernon's faithful servant kelone": "Kernon Kelone",
    "demon's agent falston": "Demon Falston",
    "last titan utenus": "Last Utenus",
    "enmity ghost ramdal": "Ghost Ramdal",
    "fierce tiger king angel": "Tiger King Angel",
    "gargoyle lord tiphon": "Gargoyle Tiphon",
    "shilen's priest hisilrome": "Priest Hisilrome",
    "fairy queen timiniel": "Fairy Queen",
    "ancient weird drake": "Ancient Drake",
    "ghost of the well lidia": "Ghost Lidia",
    "guardian of the statue of giant karum": "Guardian Karum",
    "taik high prefect arak": "Prefect Arak",
    # Epic Bosses
    "antharas": "Antharas",
    "fafureon": "Fafureon",
    "freya": "Freya",
    "frintezza": "Frintezza",
    "valakas": "Valakas",
    "baium": "Baium",
    "zaken": "Zaken",
    "core": "Core",
    "orfen": "Orfen",
    "queen ant": "Queen Ant"
}

def limpiar_nombre_jefe(nombre_original):
    """
    Toma el nombre original del jefe, lo busca en el diccionario (ignorando mayúsculas/minúsculas)
    y devuelve el nuevo nombre configurado. Si no está en la lista, devuelve el original limpio.
    """
    nombre_limpio_lower = nombre_original.strip().lower()
    
    if "balrog" in nombre_limpio_lower:
        return "Balrog"
    if "electrical" in nombre_limpio_lower or "electric" in nombre_limpio_lower:
        return "Electrica"
        
    return MAPEO_NOMBRES.get(nombre_limpio_lower, nombre_original.strip())

def obtener_datos_web():
    """
    Se conecta a la web de L2Sudamérica, extrae los jefes normales (desde Ember hasta Farakelsus),
    los divide en dos tablas, ordena los vivos arriba y los muertos por orden cronológico.
    Retorna una tupla con las dos tablas procesadas (tabla_1, tabla_2).
    """
    url = getattr(config, "PAGUINA_JUEGO", None)
    if not url:
        logger.error("No se encontró PAGUINA_JUEGO en config.py")
        return [], []

    logger.info(f"Conectando a la web para rastrear jefes normales (Hora Argentina): {url}")
    
    try:
        response = requests.get(url, timeout=15)
        if response.status_code != 200:
            logger.error(f"Error al conectar con la página web. Código HTTP: {response.status_code}")
            return [], []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        filas = soup.find_all('tr')
        
        jefes_crudos = []
        capturando = False
        
        for fila in filas:
            columnas = fila.find_all('td')
            if len(columnas) >= 4:
                nombre_bruto = columnas[0].get_text(strip=True)
                nivel = columnas[1].get_text(strip=True)
                estado = columnas[2].get_text(strip=True)
                tiempo_str = columnas[3].get_text(strip=True)
                
                if nombre_bruto.lower() == "ember":
                    capturando = True
                
                if capturando:
                    nombre_formateado = limpiar_nombre_jefe(nombre_bruto)
                    jefes_crudos.append({
                        "nombre": nombre_formateado,
                        "nivel": nivel,
                        "estado": estado.upper(),
                        "tiempo_str": tiempo_str
                    })
                
                if nombre_bruto.lower() == "zombie lord farakelsus":
                    break
        
        if not jefes_crudos:
            logger.warning("No se encontraron jefes normales en el rango especificado dentro del HTML.")
            return [], []

        mitad = len(jefes_crudos) // 2
        grupo_1 = jefes_crudos[:mitad]
        grupo_2 = jefes_crudos[mitad:]

        tabla_1 = _ordenar_tabla(grupo_1)
        tabla_2 = _ordenar_tabla(grupo_2)

        logger.info(f"Datos web normales procesados con éxito. Tabla 1: {len(tabla_1)} jefes | Tabla 2: {len(tabla_2)} jefes")
        return tabla_1, tabla_2

    except Exception as e:
        logger.error(f"Excepción ocurrida durante el scraping web de jefes normales: {e}")
        return [], []

def obtener_datos_epic_web():
    """
    Extrae la tercera lista correspondiente a los Epic Bosses de la página web.
    Busca elementos estructurados (como tarjetas o bloques de Epic Bosses) y extrae su estatus (VIVO / MUERTO).
    """
    url = getattr(config, "PAGUINA_JUEGO", None)
    if not url:
        logger.error("No se encontró PAGUINA_JUEGO en config.py para Epic Bosses")
        return []

    logger.info(f"Conectando a la web para rastrear Epic Bosses: {url}")
    
    try:
        response = requests.get(url, timeout=15)
        if response.status_code != 200:
            logger.error(f"Error HTTP al conectar para Epic Bosses: {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        epic_bosses = []

        contenedores_epic = soup.find_all(lambda tag: tag.name in ['div', 'li', 'article'] and any('epic' in c.lower() for c in tag.get('class', [])))
        
        if not contenedores_epic:
            for el in soup.find_all(text=True):
                texto = el.strip()
                if texto.lower() in ["antharas", "fafureon", "freya", "frintezza", "valakas", "baium", "zaken", "core", "orfen", "queen ant"]:
                    padre = el.find_parent(['div', 'tr', 'li', 'section'])
                    if padre:
                        estado_texto = padre.get_text(separator=' ', strip=True).upper()
                        estado = "VIVO" if "VIVO" in estado_texto or "ALIVE" in estado_texto else "MUERTO"
                        nivel_match = re.search(r'LV\s*(\d+)', estado_texto, re.IGNORECASE)
                        nivel = nivel_match.group(1) if nivel_match else "-"
                        
                        nombre_limpio = limpiar_nombre_jefe(texto)
                        if not any(b["nombre"] == nombre_limpio for b in epic_bosses):
                            epic_bosses.append({
                                "nombre": nombre_limpio,
                                "nivel": nivel,
                                "estado": estado,
                                "tiempo_str": "-"
                            })
        else:
            for contenedor in contenedores_epic:
                texto_bloque = contenedor.get_text(separator=' ', strip=True)
                for clave, nombre_formateado in MAPEO_NOMBRES.items():
                    if clave in texto_bloque.lower():
                        estado = "VIVO" if "VIVO" in texto_bloque.upper() or "ALIVE" in texto_bloque.upper() else "MUERTO"
                        nivel_match = re.search(r'LV\s*(\d+)', texto_bloque, re.IGNORECASE)
                        nivel = nivel_match.group(1) if nivel_match else "-"
                        
                        if not any(b["nombre"] == nombre_formateado for b in epic_bosses):
                            epic_bosses.append({
                                "nombre": nombre_formateado,
                                "nivel": nivel,
                                "estado": estado,
                                "tiempo_str": "-"
                            })

        epic_bosses_ordenados = sorted(epic_bosses, key=lambda x: (x["estado"] != "VIVO", x["nombre"]))
        logger.info(f"Epic Bosses procesados con éxito. Total: {len(epic_bosses_ordenados)} jefes")
        return epic_bosses_ordenados

    except Exception as e:
        logger.error(f"Excepción ocurrida al extraer Epic Bosses: {e}")
        return []

def _ordenar_tabla(lista_jefes):
    """
    Ordena una lista de jefes asegurando el huso horario argentino en los datetimes:
    1. Primero los VIVOS arriba.
    2. Luego los MUERTOS ordenados de forma ascendente por fecha y hora.
    """
    vivos = [j for j in lista_jefes if j["estado"] == "VIVO"]
    muertos = [j for j in lista_jefes if j["estado"] != "VIVO"]
    
    def parsear_fecha(jefe):
        t_str = jefe["tiempo_str"]
        if not t_str or t_str == "-":
            return datetime.max.replace(tzinfo=ZONA_ARGENTINA)
        try:
            return datetime.strptime(t_str, "%d/%m/%Y %H:%M").replace(tzinfo=ZONA_ARGENTINA)
        except ValueError:
            return datetime.max.replace(tzinfo=ZONA_ARGENTINA)

    muertos_ordenados = sorted(muertos, key=parsear_fecha)
    return vivos + muertos_ordenados


# ==========================================
# FUNCIONES DE PROCESAMIENTO DE IMÁGENES
# ==========================================

async def procesar_mensaje_imagen(message):
    if not message.attachments:
        return []

    horarios_procesados = []
    imagen_procesada_con_exito = False

    for attachment in message.attachments:
        if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp']):
            logger.info(f"🖼️ Imagen detectada en el canal: {attachment.filename}")
            try:
                imagen_bytes = await attachment.read()
                horarios_procesados = _procesar_imagen_jefes_bytes(imagen_bytes)
                if horarios_procesados:
                    imagen_procesada_con_exito = True
            except Exception as e:
                logger.error(f"Error leyendo o procesando los bytes de la imagen: {e}")
            break

    if imagen_procesada_con_exito:
        try:
            await message.delete()
            logger.info("🗑️ Mensaje de imagen original eliminado limpiamente del canal.")
        except Exception as e:
            logger.error(f"No se pudo eliminar el mensaje de la imagen: {e}")

    return horarios_procesados

def _procesar_imagen_jefes_bytes(imagen_bytes):
    if not config.GEMINI_API_KEY:
        logger.error("No se encontró GEMINI_API_KEY en config.py para procesar la imagen.")
        return []

    try:
        logger.info("🤖 Enviando imagen de horarios a Gemini para extracción visual (OCR)...")
        
        prompt = (
            "Analiza esta imagen de un juego MMORPG. Extrae cada jefe o evento junto con su horario o estado correspondiente. "
            "El formato visual muestra el nombre del jefe en una línea y debajo su fecha/hora o su estado ('Alive' o 'Muerto'). "
            "Devuelve los resultados en una lista de líneas limpias donde cada línea tenga el formato exacto: "
            "Nombre del Jefe | Fecha, Hora o Estado. "
            "No agregues texto introductorio, saludos ni explicaciones, solo los datos extraídos."
        )
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                types.Part.from_bytes(
                    data=imagen_bytes,
                    mime_type="image/png",
                ),
                prompt
            ]
        )
        
        texto_extraido = response.text
        logger.info("✨ Texto extraído de la imagen con éxito. Procesando y ordenando (Hora Argentina)...")
        
        return _limpiar_y_ordenar_datos_imagen(texto_extraido)

    except Exception as e:
        logger.error(f"Error procesando la imagen con la API de Gemini: {e}")
        return []

def _limpiar_y_ordenar_datos_imagen(texto_crudo):
    lineas = texto_crudo.strip().split('\n')
    registros = []
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

        nombre_limpio = limpiar_nombre_jefe(nombre_crudo)
        es_vivo = "alive" in resto.lower() or "vivo" in resto.lower()

        match_fecha = re.search(r'(\d{1,2})/(\d{1,2})', resto)
        match_hora = re.search(r'(\d{1,2}):(\d{2})', resto)
        if not match_hora:
            match_hora_simple = re.search(r'(?:entre\s+)?(\d{1,2})', resto, re.IGNORECASE)
            hora_str = f"{match_hora_simple.group(1).zfill(2)}:00" if match_hora_simple else "00:00"
        else:
            hora_str = f"{match_hora.group(1).zfill(2)}:{match_hora.group(2)}"

        if match_fecha:
            dia = int(match_fecha.group(1))
            mes = int(match_fecha.group(2))
            fecha_str = f"{dia:02d}/{mes:02d}/{año_actual}"
            tiempo_str_estandar = f"{fecha_str} {hora_str}"
            try:
                dt = datetime.strptime(tiempo_str_estandar, "%d/%m/%Y %H:%M").replace(tzinfo=ZONA_ARGENTINA)
            except ValueError:
                dt = datetime.max.replace(tzinfo=ZONA_ARGENTINA)
        else:
            dt = datetime.max.replace(tzinfo=ZONA_ARGENTINA)
            tiempo_str_estandar = "-"

        estado_final = "VIVO" if es_vivo else "MUERTO"
        tiempo_final_str = "-" if es_vivo else tiempo_str_estandar

        registros.append({
            "nombre": nombre_limpio,
            "nivel": "-",
            "estado": estado_final,
            "tiempo_str": tiempo_final_str,
            "es_vivo": es_vivo,
            "datetime": dt
        })

    registros_ordenados = sorted(registros, key=lambda x: (not x["es_vivo"], x["datetime"]))
    
    tabla_limpia = [
        {
            "nombre": r["nombre"], 
            "nivel": r["nivel"], 
            "estado": r["estado"], 
            "tiempo_str": r["tiempo_str"]
        } 
        for r in registros_ordenados
    ]
    
    return tabla_limpia
