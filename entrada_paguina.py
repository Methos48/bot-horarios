import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from zoneinfo import ZoneInfo
import config

logger = logging.getLogger("EntradaPagina")

# Definir la zona horaria estricta de Argentina
ZONA_ARGENTINA = ZoneInfo(getattr(config, "TZ", "America/Argentina/Buenos_Aires"))

def obtener_datos_web():
    """
    Se conecta a la web de L2Sudamérica, extrae los jefes desde Ember hasta Zombie Lord Farakelsus,
    los divide en dos tablas, ordena los vivos arriba y los muertos por orden cronológico 
    de respawn bajo hora argentina.
    Retorna una tupla con las dos tablas procesadas (tabla_1, tabla_2).
    """
    url = config.PAGUINA_JUEGO
    logger.info(f"Conectando a la web para rastrear jefes (Hora Argentina): {url}")
    
    try:
        response = requests.get(url, timeout=15)
        if response.status_code != 200:
            logger.error(f"Error al conectar con la página web. Código HTTP: {response.status_code}")
            return [], []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extraer filas de la tabla de la página del juego
        filas = soup.find_all('tr')
        
        jefes_crudos = []
        capturando = False
        
        for fila in filas:
            columnas = fila.find_all('td')
            if len(columnas) >= 4:
                nombre = columnas[0].get_text(strip=True)
                nivel = columnas[1].get_text(strip=True)
                estado = columnas[2].get_text(strip=True) # "VIVO" o "MUERTO"
                tiempo_str = columnas[3].get_text(strip=True) # Ej: "18/09/2026 21:44" o "-"
                
                # Activar captura al encontrar el inicio (Ember)
                if nombre.lower() == "ember":
                    capturando = True
                
                if capturando:
                    jefes_crudos.append({
                        "nombre": nombre,
                        "nivel": nivel,
                        "estado": estado.upper(),
                        "tiempo_str": tiempo_str
                    })
                
                # Detener captura al llegar al límite (Zombie Lord Farakelsus)
                if nombre.lower() == "zombie lord farakelsus":
                    break
                
        if not jefes_crudos:
            logger.warning("No se encontraron jefes en el rango especificado dentro del HTML.")
            return [], []

        # Dividir en dos grupos/tablas según el criterio solicitado
        mitad = len(jefes_crudos) // 2
        grupo_1 = jefes_crudos[:mitad]  # Primer grupo (60+)
        grupo_2 = jefes_crudos[mitad:]  # Segundo grupo (60-)

        tabla_1 = _ordenar_tabla(grupo_1)
        tabla_2 = _ordenar_tabla(grupo_2)

        logger.info(f"Datos web procesados con éxito bajo hora argentina. Tabla 1: {len(tabla_1)} jefes | Tabla 2: {len(tabla_2)} jefes")
        return tabla_1, tabla_2

    except Exception as e:
        logger.error(f"Excepción ocurrida durante el scraping web: {e}")
        return [], []

def _ordenar_tabla(lista_jefes):
    """
    Ordena una lista de jefes asegurando el huso horario argentino en los datetimes:
    1. Primero los VIVOS arriba.
    2. Luego los MUERTOS ordenados de forma ascendente por fecha y hora (el que nace más pronto primero).
    """
    vivos = [j for j in lista_jefes if j["estado"] == "VIVO"]
    muertos = [j for j in lista_jefes if j["estado"] != "VIVO"]
    
    # Ordenar los muertos por fecha y hora de reaparición (más próximo / rápido primero) bajo zona horaria argentina
    def parsear_fecha(jefe):
        t_str = jefe["tiempo_str"]
        if not t_str or t_str == "-":
            return datetime.max.replace(tzinfo=ZONA_ARGENTINA)
        try:
            # Parsear la fecha del sitio web y asignarle la zona horaria de Argentina
            return datetime.strptime(t_str, "%d/%m/%Y %H:%M").replace(tzinfo=ZONA_ARGENTINA)
        except ValueError:
            return datetime.max.replace(tzinfo=ZONA_ARGENTINA)

    muertos_ordenados = sorted(muertos, key=parsear_fecha)
    
    # Combinar: Vivos primero, seguidos por los muertos ordenados por tiempo de respawn
    return vivos + muertos_ordenados
