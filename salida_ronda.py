import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont
import discord
import config

logger = logging.getLogger("SalidaRonda")

ZONA_ARGENTINA = ZoneInfo(getattr(config, "TZ", "America/Argentina/Buenos_Aires"))

def _hex_a_rgb(hex_str):
    """Convierte un color hexadecimal (#RRGGBB) a una tupla RGB para PIL."""
    hex_str = hex_str.lstrip('#')
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))

def _es_jefe_especial(nombre):
    """
    Verifica si el jefe requiere la resta de 30 minutos (Valakas, Antharas, Fafurion).
    """
    if not nombre:
        return False
    n_lower = nombre.lower().strip()
    return n_lower in ["valakas", "antharas", "fafurion", "fafureon"]

def _es_epico_o_superior(nombre):
    """
    Define cuáles jefes/eventos son los únicos que pueden pasar a estado VIVO automáticamente 
    cuando llega su hora.
    """
    if not nombre:
        return False
    n_lower = nombre.lower().strip()
    
    excepciones_exactas = ["core", "orfen", "queen ant", "zaken", "asedio", "p v p", "pvp", "x9", "x 9", "foto mes", "electrical", "balrog"]
    return any(exc in n_lower for exc in excepciones_exactas) or any(esp in n_lower for esp in ["valakas", "antharas", "fafurion", "fafureon", "baium", "frintezza", "freya", "zariche"])

def _filtrar_y_clasificar(jefe):
    """
    Filtra la lista estrictamente:
    - Solo nivel 60+ 
    - Excepciones permitidas sin nivel o especiales.
    """
    nombre = jefe.get("nombre", "").strip()
    n_lower = nombre.lower()
    
    if "orfen's handmaiden" in n_lower or "orfens handmaiden" in n_lower:
        return False
    
    excepciones_permitidas = [
        "zaken", "core", "orfen", "queen ant", 
        "asedio", "p v p", "pvp", "x9", "x 9", "foto mes", "electrical", "balrog"
    ]
    
    es_excepcion = any(exc in n_lower for exc in excepciones_permitidas)
    
    nivel_raw = jefe.get("nivel", 0)
    nivel = 0
    try:
        if isinstance(nivel_raw, (int, float)):
            nivel = int(nivel_raw)
        elif isinstance(nivel_raw, str):
            solo_nums = "".join(filter(str.isdigit, nivel_raw))
            nivel = int(solo_nums) if solo_nums else 0
    except Exception:
        nivel = 0
    
    if nivel >= 60 or es_excepcion:
        return True
    return False

def _obtener_color_hora(nombre, es_vivo):
    """
    Define el color específico para la hora o estado de forma exacta.
    """
    n_lower = nombre.lower().strip()

    if es_vivo:
        return _hex_a_rgb("#40A309")

    rojos_exactos = ["valakas", "antharas", "fafurion", "fafureon"]
    if n_lower in rojos_exactos:
        return _hex_a_rgb("#FF0000")

    azules_exactos = ["core", "orfen", "baium", "zaken", "freya", "zariche", "frintezza", "queen ant", "asedio", "p v p", "pvp", "x9", "x 9", "foto mes", "electrical", "balrog"]
    if any(azul in n_lower for azul in azules_exactos):
        return _hex_a_rgb("#4D93D9")

    return _hex_a_rgb("#40A309")

def _obtener_color_fila_entera(nombre, es_vivo):
    """
    Determina si la línea entera debe pintarse de un color específico.
    Si está VIVO y no es de ningún grupo especial, se pinta de naranja claro.
    """
    if not nombre:
        return False, None
    
    n_lower = nombre.lower().strip()

    rojos_exactos = ["valakas", "antharas", "fafurion", "fafureon"]
    if n_lower in rojos_exactos:
        return True, _hex_a_rgb("#FF0000")

    azules_exactos = ["core", "orfen", "baium", "zaken", "freya", "zariche", "frintezza", "queen ant", "asedio", "p v p", "pvp", "x9", "x 9", "foto mes", "electrical", "balrog"]
    if any(azul in n_lower for azul in azules_exactos):
        return True, _hex_a_rgb("#4D93D9")

    verdes_exactos = ["decarbia", "hekaton", "queen shyeed"]
    if n_lower in verdes_exactos:
        return True, _hex_a_rgb("#40A309")

    # NUEVA REGLA: Si está VIVO y no pertenece a los anteriores, fondo naranja claro
    if es_vivo:
        return True, _hex_a_rgb("#FFB366")

    return False, None

async def ejecutar(bot_instance, datos_horario):
    """
    Función principal llamada desde main.py
    """
    logger.info("⚙️ Ejecutando salida_ronda: Procesando filtros y lógica de ordenamiento por estados...")
    
    canal_id = getattr(config, "RONDA_CHANNEL_ID", None)
    ruta_plantilla = getattr(config, "PLANTILLA_RONDA", None)
    fuente_aptos_path = getattr(config, "FUENTE_APTOS", None)
    fuente_biome_path = getattr(config, "FUENTE_BIOME", None)
    
    if not canal_id or not ruta_plantilla:
        logger.error("❌ Faltan configuraciones en config.py (RONDA_CHANNEL_ID o PLANTILLA_RONDA).")
        return

    channel = bot_instance.get_channel(canal_id)
    if not channel:
        logger.warning(f"⚠️ No se pudo encontrar el canal de Discord con ID: {canal_id}")
        return

    try:
        # 1. BORRAR EL MENSAJE ANTERIOR DEL BOT
        try:
            async for mensaje in channel.history(limit=20):
                if mensaje.author == bot_instance.user:
                    await mensaje.delete()
                    logger.info("🗑️ Mensaje anterior de salida_ronda eliminado con éxito.")
                    break
        except Exception as err_del:
            logger.warning(f"⚠️ No se pudo eliminar el mensaje anterior en salida_ronda: {err_del}")

        # 2. FILTRAR Y PROCESAR DATOS UNIFICADOS
        datos_filtrados = [j for j in datos_horario if _filtrar_y_clasificar(j)]
        datos_procesados = []

        ahora_actual = datetime.now(ZONA_ARGENTINA)

        for jefe in datos_filtrados:
            registro = jefe.copy()
            nombre = registro.get("nombre", "")
            estado = registro.get("estado", "").upper()
            tiempo_str = registro.get("tiempo_str", "-")
            
            es_vivo_fuente = (estado in ["VIVO", "ALIVE"] or registro.get("es_vivo", False))
            
            dt_obj = datetime.max.replace(tzinfo=ZONA_ARGENTINA)
            if tiempo_str and tiempo_str != "-":
                try:
                    dt_obj = datetime.strptime(tiempo_str, "%d/%m/%Y %H:%M").replace(tzinfo=ZONA_ARGENTINA)
                    if _es_jefe_especial(nombre):
                        dt_obj = dt_obj - timedelta(minutes=30)
                except ValueError:
                    pass

            es_epico = _es_epico_o_superior(nombre)
            
            if es_vivo_fuente or (es_epico and dt_obj != datetime.max.replace(tzinfo=ZONA_ARGENTINA) and dt_obj <= ahora_actual):
                registro["es_vivo"] = True
                registro["tiempo_str_final"] = "VIVO"
                registro["datetime"] = datetime.min.replace(tzinfo=ZONA_ARGENTINA)
            else:
                registro["es_vivo"] = False
                registro["datetime"] = dt_obj
                if dt_obj != datetime.max.replace(tzinfo=ZONA_ARGENTINA):
                    registro["tiempo_str_final"] = dt_obj.strftime("%H:%M")
                else:
                    registro["tiempo_str_final"] = tiempo_str[-5:] if len(tiempo_str) >= 5 else tiempo_str

            datos_procesados.append(registro)

        # ==========================================
        # 3. ORDENAR ESTRICTO PARA VIVOS (Rojos -> Azules -> Verdes -> Comunes) Y LUEGO CRONOLÓGICOS
        # ==========================================
        rojos_set = {"valakas", "antharas", "fafurion", "fafureon"}
        azules_set = {"core", "orfen", "baium", "zaken", "freya", "zariche", "frintezza", "queen ant", "asedio", "p v p", "pvp", "x9", "x 9", "foto mes", "electrical", "balrog"}
        verdes_set = {"decarbia", "hekaton", "queen shyeed"}

        def clave_orden(item):
            nombre = item.get("nombre", "").lower().strip()
            es_vivo = item.get("es_vivo", False)
            dt = item.get("datetime", datetime.max.replace(tzinfo=ZONA_ARGENTINA))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZONA_ARGENTINA)

            if es_vivo:
                if nombre in rojos_set:
                    prioridad_vivo = 1
                elif any(b in nombre for b in azules_set):
                    prioridad_vivo = 2
                elif nombre in verdes_set:
                    prioridad_vivo = 3
                else:
                    prioridad_vivo = 4 # Vivos comunes
                return (0, prioridad_vivo, nombre)
            else:
                return (1, 0, dt)

        datos_ordenados = sorted(datos_procesados, key=clave_orden)

        # 4. CARGAR PLANTILLA Y FUENTES
        canvas = Image.open(ruta_plantilla).convert("RGBA")
        draw = ImageDraw.Draw(canvas)

        try:
            fuente_texto = ImageFont.truetype(fuente_aptos_path, 15) if fuente_aptos_path else ImageFont.load_default()
        except Exception:
            fuente_texto = ImageFont.load_default()

        try:
            fuente_texto_grande = ImageFont.truetype(fuente_aptos_path, 17) if fuente_aptos_path else ImageFont.load_default()
        except Exception:
            fuente_texto_grande = ImageFont.load_default()

        try:
            fuente_hora = ImageFont.truetype(fuente_biome_path, 15) if fuente_biome_path else ImageFont.load_default()
        except Exception:
            fuente_hora = ImageFont.load_default()

        try:
            fuente_hora_grande = ImageFont.truetype(fuente_biome_path, 17) if fuente_biome_path else ImageFont.load_default()
        except Exception:
            fuente_hora_grande = ImageFont.load_default()

        color_negro = _hex_a_rgb("#000000")

        # 5. CONFIGURACIÓN DE COORDENADAS (DOS COLUMNAS)
        x_nombre_izq, x_lvl_izq, x_hora_izq = 16, 220, 265
        x_nombre_der, x_lvl_der, x_hora_der = 340, 540, 590
        y_inicial = 110
        espaciado_renglon = 24

        # 6. DIBUJAR DATOS EN LA IMAGEN (MÁX 22 POR LADO)
        for index, jefe in enumerate(datos_ordenados):
            nombre = jefe.get("nombre", "Desconocido")
            nivel = str(jefe.get("nivel", ""))
            tiempo_mostrar = jefe.get("tiempo_str_final", "-")
            es_vivo = jefe.get("es_vivo", False)

            if index < 22:
                columna = "izq"
                y_cursor = y_inicial + (index * espaciado_renglon)
            elif index < 44:
                columna = "der"
                y_cursor = y_inicial + ((index - 22) * espaciado_renglon)
            else:
                break

            if columna == "izq":
                x_n, x_l, x_h = x_nombre_izq, x_lvl_izq, x_hora_izq
            else:
                x_n, x_l, x_h = x_nombre_der, x_lvl_der, x_hora_der

            y_centro = y_cursor + (espaciado_renglon // 2)

            debe_pintar_fondo, color_fondo_especial = _obtener_color_fila_entera(nombre, es_vivo)

            if debe_pintar_fondo:
                rect_box = [x_n - 4, y_centro - 10, x_h + 50, y_centro + 10]
                draw.rectangle(rect_box, fill=color_fondo_especial)
                
                # Si el fondo es naranja claro (#FFB366), usamos texto negro para mantener la legibilidad, de lo contrario blanco
                if color_fondo_especial == _hex_a_rgb("#FFB366"):
                    color_texto_fila = _hex_a_rgb("#000000")
                    color_hora = _hex_a_rgb("#000000")
                else:
                    color_texto_fila = _hex_a_rgb("#FFFFFF")
                    color_hora = _hex_a_rgb("#FFFFFF")

                font_t = fuente_texto_grande
                font_h = fuente_hora_grande
                
                draw.text((x_n, y_centro), nombre, fill=color_texto_fila, font=font_t, anchor="lm")
                draw.text((x_n + 1, y_centro), nombre, fill=color_texto_fila, font=font_t, anchor="lm")

                draw.text((x_l, y_centro), nivel, fill=color_texto_fila, font=font_t, anchor="lm")
                draw.text((x_l + 1, y_centro), nivel, fill=color_texto_fila, font=font_t, anchor="lm")

                draw.text((x_h, y_centro), tiempo_mostrar, fill=color_hora, font=font_h, anchor="lm")
                draw.text((x_h + 1, y_centro), tiempo_mostrar, fill=color_hora, font=font_h, anchor="lm")
            else:
                color_texto_fila = color_negro
                color_hora = _obtener_color_hora(nombre, es_vivo)
                font_t = fuente_texto
                font_h = fuente_hora

                draw.text((x_n, y_centro), nombre, fill=color_texto_fila, font=font_t, anchor="lm")
                draw.text((x_l, y_centro), nivel, fill=color_texto_fila, font=font_t, anchor="lm")
                draw.text((x_h, y_centro), tiempo_mostrar, fill=color_hora, font=font_h, anchor="lm")

        # 7. GUARDAR Y ENVIAR A DISCORD
        nombre_archivo_salida = "ronda_horario_final.png"
        canvas.save(nombre_archivo_salida)

        archivo_discord = discord.File(nombre_archivo_salida, filename="horario_ronda.png")
        await channel.send(file=archivo_discord)
        
        logger.info("✅ Imagen de salida_ronda generada correctamente con nuevo orden y recuadro naranja para vivos comunes.")

    except Exception as e:
        logger.error(f"❌ Error crítico al ejecutar salida_ronda: {e}")
