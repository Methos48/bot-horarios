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
    Blindaje total y mejorado: Inserta espacios automáticamente si detecta campos pegados:
    - Fecha pegada a hora con año (ej: 22/09/2622:00 -> 22/09/26 22:00)
    - Fecha pegada a hora sin año (ej: 22/0922:00 -> 22/09 22:00)
    - Nombre pegado a fecha (ej: Antharas22/09 -> Antharas 22/09)
    """
    # 1. Si la fecha (con o sin año de 2 o 4 dígitos) está pegada directamente a la hora
    linea = re.sub(r'(\d{1,2}/\d{1,2}(?:/\d{2,4})?)(\d{1,2}:\d{2})', r'\1 \2', linea)
    
    # 2. Si el nombre está pegado a la fecha
    match_nombre_fecha = re.search(r'^(.+?)(?=\d{1,2}/\d{1,2})', linea)
    if match_nombre_fecha:
        idx = match_nombre_fecha.end()
        if idx < len(linea) and not linea[idx].isspace():
            linea = linea[:idx] + " " + linea[idx:]
            
    return linea

def procesar_y_ordenar_texto(contenido_texto):
    """
    Procesa bloques de texto ultra flexibles y blindados:
    - Corrige y separa campos totalmente pegados (NombreFechaHora).
    - Une nombres arriba y horarios abajo si están en líneas separadas.
    - Maneja 'VIVO', fechas completas, con días de la semana o sin fecha (asumiendo hoy).
    - Extrae la primera hora de rangos tipo 'entre 22 y 22:30' o '22:00 - 22:30'.
    - Filtra Barakiel, renombra Balrog y Electrical, y ordena por hora argentina.
    """
    lineas_crudas = contenido_texto.strip().split('\n')
    lineas_preliminares = []
    
    # --- PASO 1: APLICAR BLINDAJE DE CAMPOS PEGADOS Y UNIFICAR LÍNEAS ---
    for l in lineas_crudas:
        l_limpia = l.strip()
        if not l_limpia:
            continue
        l_blindada = limpiar_campos_pegados(l_limpia)
        lineas_preliminares.append(l_blindada)

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

    registros = []
    anio_actual = datetime.now(ZONA_ARGENTINA).year
    hoy_dt = datetime.now(ZONA_ARGENTINA)

    patron_vivo = re.compile(r'(.+?)\s+(vivo)', re.IGNORECASE)
    
    # Patrón general robusto para extraer componentes
    patron_completo = re.compile(
        r'(.+?)\s+'  
        r'(?:(?:lunes|martes|miércoles|jueves|viernes|sábado|domingo)\s+)?'  
        r'(\d{1,2}/\d{1,2}(?:/\d{2,4})?)?\s*'  
        r'(?:entre\s+)?(\d{1,2})(?::(\d{2}))?',  
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
            h_parte2 = match_completo.group(4) or "00"
            hora_str = f"{h_parte1}:{h_parte2}"
            es_vivo = False
        else:
            logger.warning(f"Línea {numero_linea} no coincide con el formato esperado: '{linea}'")
            continue

        # --- APLICAR FILTROS DE NOMBRES Y NIVELES ---
        if "flame of splendor barakiel" in nombre_crudo.lower():
            logger.info(f"Filtro: Excluido el jefe '{nombre_crudo}'")
            continue
            
        if "balrog devourer pvp" in nombre_crudo.lower() or "balrog" in nombre_crudo.lower():
            nombre_limpio = "Balrog"
            nivel_asignado = "85"
        elif "execution electrical pvp" in nombre_crudo.lower() or "electrical" in nombre_crudo.lower() or "electric" in nombre_crudo.lower():
            nombre_limpio = "Electrical"
            nivel_asignado = "85"
        else:
            nombre_limpio = nombre_crudo
            nivel_asignado = "-"

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

        registros.append({
            "nombre": nombre_limpio,
            "nivel": nivel_asignado,
            "estado": estado_jefe,
            "tiempo_str": tiempo_str_visual,
            "datetime": dt,
            "es_vivo": es_vivo
        })

    registros_ordenados = sorted(registros, key=lambda x: (not x["es_vivo"], x["datetime"]))
    
    tabla_limpia = []
    for reg in registros_ordenados:
        tabla_limpia.append({
            "nombre": reg["nombre"],
            "nivel": reg["nivel"],
            "estado": reg["estado"],
            "tiempo_str": reg["tiempo_str"]
        })

    logger.info(f"Texto procesado, filtrado y ordenado con éxito bajo hora argentina: {len(tabla_limpia)} elementos listos para main.")
    return tabla_limpia
