import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo
import config

logger = logging.getLogger("EntradaTexto")

# Definir la zona horaria estricta de Argentina
ZONA_ARGENTINA = ZoneInfo(getattr(config, "TZ", "America/Argentina/Buenos_Aires"))

async def procesar_mensaje_texto(message):
    """
    Verifica si el mensaje contiene contenido de texto válido (y no tiene archivos adjuntos/imágenes).
    Si es así, procesa el texto, extrae los datos y, al terminar de conseguirlos con éxito,
    borra el mensaje original para mantener el canal limpio.
    """
    if message.attachments or not message.content:
        return []

    contenido_texto = message.content
    logger.info("📥 Bloque de texto detectado en el canal de carga.")
    
    horarios_procesados = procesar_y_ordenar_texto(contenido_texto)

    if horarios_procesados:
        try:
            await message.delete()
            logger.info("🗑️ Mensaje de texto original eliminado limpiamente del canal.")
        except Exception as e:
            logger.error(f"No se pudo eliminar el mensaje de texto: {e}")

    return horarios_procesados

def limpiar_campos_pegados(linea):
    """
    Inserta espacios automáticamente si detecta campos pegados en la entrada:
    - Fecha pegada a hora con año (ej: 22/09/2622:00 -> 22/09/26 22:00)
    - Fecha pegada a hora sin año (ej: 22/0922:00 -> 22/09 22:00)
    - Nombre pegado a fecha (ej: Antharas22/09 -> Antharas 22/09)
    """
    linea = re.sub(r'(\d{1,2}/\d{1,2}(?:/\d{2,4})?)(\d{1,2}:\d{2})', r'\1 \2', linea)
    
    match_nombre_fecha = re.search(r'^(.+?)(?=\d{1,2}/\d{1,2})', linea)
    if match_nombre_fecha:
        idx = match_nombre_fecha.end()
        if idx < len(linea) and not linea[idx].isspace():
            linea = linea[:idx] + " " + linea[idx:]
            
    return linea

def limpiar_nombre_crudo(nombre_crudo):
    """
    Remueve restos de fechas (ej: 29/09/26) o espacios múltiples de la cadena de entrada.
    """
    nombre_limpio = re.sub(r'\d{1,2}/\d{1,2}(?:/\d{2,4})?', '', nombre_crudo)
    return re.sub(r'\s+', ' ', nombre_limpio).strip()

def normalizar_nombre_y_nivel(nombre_crudo):
    """
    Compara el nombre crudo con la lista oficial para forzar la salida exacta requerida.
    Excluye por completo a Barakiel.
    """
    n_low = limpiador_claves(nombre_crudo)

    if "barakiel" in n_low:
        return None, None # Descartado

    if "balrog" in n_low:
        return "Balrog", "85"
    elif "electrical" in n_low or "electric" in n_low:
        return "Electrical", "85"
    elif "orfen" in n_low:
        return "Orfen", "-"
    elif "queen ant" in n_low or "queenant" in n_low:
        return "Queen Ant", "-"
    elif "core" in n_low:
        return "Core", "-"
    elif "zaken" in n_low:
        return "Zaken", "-"
    elif "baium" in n_low:
        return "Baium", "-"
    elif "frintezza" in n_low:
        return "Frintezza", "-"
    elif "freya" in n_low:
        return "Freya", "-"
    elif "zariche" in n_low:
        return "Zariche", "-"
    elif "valakas" in n_low:
        return "Valakas", "-"
    elif "antharas" in n_low:
        return "Antharas", "-"
    elif "fafur" in n_low or "fafureon" in n_low:
        return "Fafureon", "-"
    elif "asedio" in n_low:
        return "Asedio", "-"
    elif "p v p" in n_low or "pvp" in n_low:
        return "P V P", "-"
    elif "x 9" in n_low or "x9" in n_low:
        return "X 9", "-"
    elif "foto mes" in n_low or "fotomes" in n_low:
        return "Foto Mes", "-"
    else:
        return nombre_crudo.title(), "-"

def limpiador_claves(texto):
    """Normaliza texto eliminando espacios y acentos para comparación segura."""
    return re.sub(r'[\s\-]+', '', texto.lower())

def procesar_y_ordenar_texto(contenido_texto):
    """
    Procesa la entrada línea por línea, unifica saltos partidos, interpreta 
    correctamente VIVO o formato de fecha/hora, normaliza y ordena la salida.
    """
    lineas_crudas = contenido_texto.strip().split('\n')
    lineas_preliminares = []
    
    for l in lineas_crudas:
        l_limpia = l.strip()
        if not l_limpia:
            continue
        lineas_preliminares.append(limpiar_campos_pegados(l_limpia))

    # Unir líneas partidas en la entrada (ej: Nombre en una línea y hora en la siguiente)
    lineas_limpias = []
    i = 0
    while i < len(lineas_preliminares):
        linea_actual = lineas_preliminares[i]
        
        if i + 1 < len(lineas_preliminares):
            siguiente_linea = lineas_preliminares[i + 1]
            es_horario_o_vivo = bool(re.search(r'(\d{1,2}:\d{2}|vivo|entre)', siguiente_linea, re.IGNORECASE))
            no_tiene_horario_actual = not bool(re.search(r'(\d{1,2}:\d{2}|vivo|\d{1,2}/\d{1,2})', linea_actual, re.IGNORECASE))
            
            if no_tiene_horario_actual and es_horario_o_vivo:
                linea_actual = f"{linea_actual} {siguiente_linea}"
                i += 1
                
        lineas_limpias.append(linea_actual)
        i += 1

    registros_dict = {} 
    anio_actual = datetime.now(ZONA_ARGENTINA).year
    hoy_dt = datetime.now(ZONA_ARGENTINA)

    # Patrones de entrada mejorados para capturar ordenes flexibles de texto
    patron_vivo = re.compile(r'^(.*?)\s+(vivo)\b', re.IGNORECASE)
    patron_completo = re.compile(
        r'^(.*?)\s+'  
        r'(?:(?:lunes|martes|miércoles|jueves|viernes|sábado|domingo)\s+)?'  
        r'(\d{1,2}/\d{1,2}(?:/\d{2,4})?)?\s*'  
        r'(?:entre\s+)?(\d{1,2}):(\d{2})',  
        re.IGNORECASE
    )

    for numero_linea, linea in enumerate(lineas_limpias, start=1):
        linea = linea.strip()
        if not linea:
            continue

        match_vivo = patron_vivo.search(linea)
        match_completo = patron_completo.search(linea) if not match_vivo else None

        if match_vivo:
            nombre_crudo = match_vivo.group(1).strip()
            es_vivo = True
            fecha_str = None
            hora_str = None
        elif match_completo:
            nombre_crudo = match_completo.group(1).strip()
            fecha_str = match_completo.group(2)
            h_parte1 = match_completo.group(3)
            h_parte2 = match_completo.group(4)
            hora_str = f"{h_parte1}:{h_parte2}"
            es_vivo = False
        else:
            logger.warning(f"Línea {numero_linea} no coincide con el formato esperado: '{linea}'")
            continue

        # Limpiar y normalizar salida
        nombre_base = limpiar_nombre_crudo(nombre_crudo)
        nombre_limpio, nivel_asignado = normalizar_nombre_y_nivel(nombre_base)

        if not nombre_limpio: # Descartado (Ej: Barakiel)
            continue

        if es_vivo:
            tiempo_str_visual = "VIVO"
            dt = datetime.min.replace(tzinfo=ZONA_ARGENTINA)
            estado_jefe = "VIVO"
        else:
            if not fecha_str:
                fecha_con_anio = hoy_dt.strftime(f"%d/%m/{anio_actual}")
            else:
                partes_fecha = fecha_str.split('/')
                dia_norm = f"{int(partes_fecha[0]):02d}"
                mes_norm = f"{int(partes_fecha[1]):02d}"

                if len(partes_fecha) == 2:
                    fecha_con_anio = f"{dia_norm}/{mes_norm}/{anio_actual}"
                elif len(partes_fecha[2]) == 2:
                    fecha_con_anio = f"{dia_norm}/{mes_norm}/20{partes_fecha[2]}"
                else:
                    fecha_con_anio = f"{dia_norm}/{mes_norm}/{partes_fecha[2]}"

            partes_hora = hora_str.split(':')
            hora_formateada = f"{int(partes_hora[0]):02d}:{partes_hora[1]}"

            tiempo_str_completo = f"{fecha_con_anio} {hora_formateada}"
            
            try:
                dt = datetime.strptime(tiempo_str_completo, "%d/%m/%Y %H:%M").replace(tzinfo=ZONA_ARGENTINA)
                tiempo_str_visual = dt.strftime("%d/%m/%Y %H:%M")
            except ValueError:
                dt = datetime.max.replace(tzinfo=ZONA_ARGENTINA)
                tiempo_str_visual = tiempo_str_completo

            estado_jefe = "MUERTO"

        # Control estricto de duplicados en la salida usando clave unificada
        clave_key = limpiador_claves(nombre_limpio)
        if clave_key not in registros_dict or es_vivo:
            registros_dict[clave_key] = {
                "nombre": nombre_limpio,
                "nivel": nivel_asignado,
                "estado": estado_jefe,
                "tiempo_str": tiempo_str_visual,
                "datetime": dt,
                "es_vivo": es_vivo
            }

    # Orden final exacto: Primero los VIVOS, luego ordenados cronológicamente
    registros_ordenados = sorted(list(registros_dict.values()), key=lambda x: (not x["es_vivo"], x["datetime"]))
    
    tabla_limpia = []
    for reg in registros_ordenados:
        tabla_limpia.append({
            "nombre": reg["nombre"],
            "nivel": reg["nivel"],
            "estado": reg["estado"],
            "tiempo_str": reg["tiempo_str"]
        })

    logger.info(f"Entrada analizada y salida formateada con éxito: {len(tabla_limpia)} registros.")
    return tabla_limpia
