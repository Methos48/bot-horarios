import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo
import config

logger = logging.getLogger("EntradaTexto")

# Definir la zona horaria estricta de Argentina
ZONA_ARGENTINA = ZoneInfo(getattr(config, "TZ", "America/Argentina/Buenos_Aires"))

def procesar_y_ordenar_texto(contenido_texto):
    """
    Procesa el bloque de texto del canal de carga:
    - Filtra rangos de hora tomando la primera.
    - Excluye a Flame of Splendor Barakiel.
    - Renombra Balrog Devourer PVP y Execution Electrical PVP.
    - Ordena cronológicamente bajo hora argentina.
    """
    lineas = contenido_texto.strip().split('\n')
    registros = []
    
    # Expresión regular para detectar fechas y horas (permite capturar rangos como HH:MM - HH:MM)
    patron_linea = re.compile(r'(.+?)\s+(\d{2}/\d{2}/\d{2,4})\s+(\d{2}:\d{2})(?:\s*-\s*\d{2}:\d{2})?')

    for numero_linea, linea in enumerate(lineas, start=1):
        linea = linea.strip()
        if not linea:
            continue
            
        match = patron_linea.search(linea)
        if match:
            nombre_crudo = match.group(1).strip()
            fecha_str = match.group(2)
            hora_str = match.group(3) # Toma la primera hora en caso de haber un rango
            
            # --- APLICAR FILTROS DE NOMBRES ---
            # 1. Excluir a Flame of Splendor Barakiel
            if "flame of splendor barakiel" in nombre_crudo.lower():
                logger.info(f"Filtro: Excluido el jefe '{nombre_crudo}'")
                continue
                
            # 2. Renombrar Balrog Devourer PVP
            if "balrog devourer pvp" in nombre_crudo.lower() or "balrog" in nombre_crudo.lower():
                nombre_limpio = "Balrog"
            # 3. Renombrar Execution Electrical PVP
            elif "execution electrical pvp" in nombre_crudo.lower() or "electrical" in nombre_crudo.lower() or "electric" in nombre_crudo.lower():
                nombre_limpio = "Electrica"
            else:
                nombre_limpio = nombre_crudo

            tiempo_str = f"{fecha_str} {hora_str}"
            
            # Convertir a datetime con zona horaria argentina para orden exacto
            try:
                partes_fecha = fecha_str.split('/')
                if len(partes_fecha[2]) == 2:
                    dt = datetime.strptime(tiempo_str, "%d/%m/%y %H:%M").replace(tzinfo=ZONA_ARGENTINA)
                else:
                    dt = datetime.strptime(tiempo_str, "%d/%m/%Y %H:%M").replace(tzinfo=ZONA_ARGENTINA)
            except ValueError:
                dt = datetime.max.replace(tzinfo=ZONA_ARGENTINA)  # Si hay error, se manda al final
            
            registros.append({
                "nombre": nombre_limpio,
                "tiempo_str": tiempo_str,
                "datetime": dt
            })
        else:
            logger.warning(f"Línea {numero_linea} no coincide con el formato esperado: '{linea}'")

    # Ordenar cronológicamente bajo hora argentina (lo que sucede más pronto va arriba)
    registros_ordenados = sorted(registros, key=lambda x: x["datetime"])
    
    # Entregar la tabla limpia conservando los campos necesarios para main.py
    tabla_limpia = []
    for reg in registros_ordenados:
        tabla_limpia.append({
            "nombre": reg["nombre"],
            "tiempo_str": reg["tiempo_str"],
            "datetime": reg["datetime"],
            "es_vivo": False  # El texto manual procesa fechas y horas directas
        })

    logger.info(f"Texto procesado, filtrado y ordenado con éxito bajo hora argentina: {len(tabla_limpia)} elementos listos para main.")
    return tabla_limpia
