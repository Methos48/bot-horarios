import asyncio
import io
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import discord
from PIL import Image

logger = logging.getLogger("SalidaBot")

CANAL_SALIDA_BOT = 1568910710057074799
ZONA_ARGENTINA = ZoneInfo("America/Argentina/Buenos_Aires")
RAIDS = {"valakas", "antharas", "fafureon"}
DIR_PLANTILLAS = Path("imagen") / "bot"
DIR_NUMEROS = Path("imagen") / "numeros"
INTERVALO_LECTURA = 1.0
TIEMPO_CIERRE = timedelta(minutes=33)

# =====================================================================
# 🎛️ PANEL DE CONTROL INDEPENDIENTE
# =====================================================================

# 1. CONFIGURACIÓN PARA PLANTILLAS DE FECHA Y HORA (Ej: Valakas, Antharas)
ALTO_NUMEROS_FECHA_HORA = 85
POSICION_Y_FECHA_HORA = 270
POSICION_X_FECHA_HORA = 57
ESPACIO_ENTRE_NUMEROS_FH = 1
ESPACIO_ENTRE_FECHA_Y_HORA = 15

# 2. CONFIGURACIÓN PARA PLANTILLA DE SOLO HORA (Ej: Abrio / Cronómetro)
ALTO_NUMEROS_SOLO_HORA = 115
POSICION_Y_SOLO_HORAS = 250
POSICION_X_SOLO_HORAS = 70
ESPACIO_ENTRE_NUMEROS_SH = 4

# =====================================================================


def _fecha(item):
    valor = item.get("datetime_iso") or item.get("datetime")
    if isinstance(valor, datetime):
        fecha = valor
    elif valor:
        try:
            fecha = datetime.fromisoformat(str(valor))
        except ValueError:
            fecha = None
    else:
        fecha = None
    if fecha is None:
        for campo in ("tiempo_str", "tiempo", "hora"):
            texto = str(item.get(campo) or "").strip()
            for formato in ("%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M"):
                try:
                    fecha = datetime.strptime(texto, formato)
                    break
                except ValueError:
                    continue
            if fecha is not None:
                break
    if fecha is None or fecha.year in (1, 9999):
        return None
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=ZONA_ARGENTINA)
    return fecha.astimezone(ZONA_ARGENTINA)


def _estado(item):
    for campo in ("estado", "status", "vivo_muerto", "vivo_o_muerto", "tiempo_str"):
        valor = str(item.get(campo) or "").strip().upper()
        if valor in ("VIVO", "ALIVE"):
            return "vivo"
        if valor in ("MUERTO", "DEAD"):
            return "muerto"
    if item.get("es_vivo") is True:
        return "vivo"
    return None


def _leer_datos(data):
    if not isinstance(data, dict):
        raise ValueError("El JSON de jefes debe contener un objeto.")
    fechas = {}
    estados = {}
    for lista in ("tabla_60_plus", "tabla_raids", "horarios_manuales", "raid_60_menos", "raid_60_plus"):
        items = data.get(lista, [])
        if not isinstance(items, list):
            raise ValueError(f"La lista {lista} no tiene un formato válido.")
        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"La lista {lista} contiene un registro inválido.")
            nombre = str(item.get("nombre") or "").strip().lower()
            if nombre in RAIDS:
                fecha = _fecha(item)
                if fecha:
                    fechas[nombre] = fecha
                estado = _estado(item)
                if estado:
                    estados[nombre] = estado
    for lista in ("tabla_epic", "vivo_o_muerto"):
        items = data.get(lista, [])
        if not isinstance(items, list):
            raise ValueError(f"La lista {lista} no tiene un formato válido.")
        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"La lista {lista} contiene un registro inválido.")
            nombre = str(item.get("nombre") or "").strip().lower()
            if nombre in RAIDS:
                estado = _estado(item)
                if estado:
                    estados[nombre] = estado
                fecha = _fecha(item)
                if fecha and nombre not in fechas:
                    fechas[nombre] = fecha
    fechas_rojos = {fecha.date() for nombre, fecha in fechas.items() if nombre in {"valakas", "antharas"}}
    if "fafureon" in fechas and fechas["fafureon"].date() in fechas_rojos:
        del fechas["fafureon"]
    return fechas, estados


def _clave(nombre, fecha):
    return f"{nombre}|{fecha.isoformat()}"


def _estampar(plantilla, texto):
    with Image.open(plantilla) as original:
        imagen = original.convert("RGBA")
        
    if texto:
        archivos = {str(i): DIR_NUMEROS / f"{i}.jpg" for i in range(10)}
        archivos.update({":": DIR_NUMEROS / "2puntos.jpg", "/": DIR_NUMEROS / "signo.png"})
        
        # Detectar si estamos procesando la plantilla de solo hora (abrio.png o formato de segundos)
        es_solo_hora = ":" in texto and "/" not in texto
        
        # Seleccionar parámetros según el tipo de plantilla
        if es_solo_hora:
            alto_base = ALTO_NUMEROS_SOLO_HORA
            pos_x_inicial = POSICION_X_SOLO_HORAS
            y = POSICION_Y_SOLO_HORAS
            espacio_nums = ESPACIO_ENTRE_NUMEROS_SH
        else:
            alto_base = ALTO_NUMEROS_FECHA_HORA
            pos_x_inicial = POSICION_X_FECHA_HORA
            y = POSICION_Y_FECHA_HORA
            espacio_nums = ESPACIO_ENTRE_NUMEROS_FH

        piezas = []
        i = 0
        while i < len(texto):
            caracter = texto[i]
            if caracter == " ":
                conteo_espacios = 0
                while i < len(texto) and texto[i] == " ":
                    conteo_espacios += 1
                    i += 1
                piezas.append((None, ESPACIO_ENTRE_FECHA_Y_HORA * conteo_espacios))
                continue
            
            path_pieza = archivos.get(caracter)
            if path_pieza and path_pieza.exists():
                with Image.open(path_pieza) as original_pieza:
                    pieza = original_pieza.convert("RGBA")
                
                # Regla: Los dos puntos (":") miden el 60% del alto de los números
                if caracter == ":":
                    alto_caracter = int(alto_base * 0.60)
                else:
                    alto_caracter = alto_base

                ancho = max(1, round(pieza.width * alto_caracter / pieza.height))
                pieza_resized = pieza.resize((ancho, alto_caracter), Image.Resampling.LANCZOS)
                piezas.append((pieza_resized, ancho))
            else:
                piezas.append((None, 0))
            i += 1
                
        ancho_total = 0
        for item, ancho in piezas:
            if item:
                ancho_total += ancho + espacio_nums
            else:
                ancho_total += ancho
        if piezas and piezas[-1][0] is not None:
            ancho_total -= espacio_nums

        if pos_x_inicial is not None:
            x = pos_x_inicial
        else:
            x = (imagen.width - ancho_total) // 2
        
        for item, ancho in piezas:
            if item:
                # Ajustar alineación vertical si es un carácter de menor altura (como los dos puntos al 60%)
                offset_y = 0
                if item.height < alto_base:
                    offset_y = (alto_base - item.height) // 2
                
                imagen.paste(item, (x, y + offset_y), item)
                x += ancho + espacio_nums
            else:
                x += ancho

    resultado = io.BytesIO()
    imagen.save(resultado, format="PNG", quality=95)
    resultado.seek(0)
    return resultado


def _cargar_estado(ruta):
    if not ruta.exists():
        return {"actual": None, "completados": [], "mensaje_id": None}
    with ruta.open("r", encoding="utf-8") as archivo:
        estado = json.load(archivo)
    if not isinstance(estado, dict) or not isinstance(estado.get("completados"), list):
        raise ValueError(f"Estado inválido en {ruta}")
    return estado


def _guardar_estado(ruta, estado):
    temporal = ruta.with_name(ruta.name + ".tmp")
    with temporal.open("w", encoding="utf-8") as archivo:
        json.dump(estado, archivo, ensure_ascii=False, indent=2)
    os.replace(temporal, ruta)


class MonitorSalidaBot:
    def __init__(self, bot, ruta_json, json_lock):
        self.bot = bot
        self.ruta_json = Path(ruta_json)
        self.json_lock = json_lock
        self.ruta_estado = self.ruta_json.with_name("salida_bot_estado.json")
        self.estado = _cargar_estado(self.ruta_estado)
        self.canal = None
        self.publicado = None

    async def _datos(self):
        async with self.json_lock:
            with self.ruta_json.open("r", encoding="utf-8") as archivo:
                datos = json.load(archivo)
        return _leer_datos(datos)

    async def _canal(self):
        if self.canal is None:
            self.canal = self.bot.get_channel(CANAL_SALIDA_BOT)
            if self.canal is None:
                self.canal = await self.bot.fetch_channel(CANAL_SALIDA_BOT)
        return self.canal

    async def _limpiar(self):
        canal = await self._canal()
        async for mensaje in canal.history(limit=None):
            if mensaje.author.id == self.bot.user.id:
                try:
                    await mensaje.delete()
                except discord.NotFound:
                    continue
        self.estado["mensaje_id"] = None
        _guardar_estado(self.ruta_estado, self.estado)

    async def _publicar(self, nombre, variante, texto):
        firma = (nombre, variante, texto)
        if self.publicado == firma:
            return
        ruta = DIR_PLANTILLAS / (f"{nombre}{variante}.png" if nombre else "abrio.png")
        imagen = await asyncio.to_thread(_estampar, ruta, texto)
        try:
            canal = await self._canal()
            await self._limpiar()
            adjunto = discord.File(imagen, filename=ruta.name)
            try:
                mensaje = await canal.send(file=adjunto)
            finally:
                adjunto.close()
            self.estado["mensaje_id"] = mensaje.id
            _guardar_estado(self.ruta_estado, self.estado)
            self.publicado = firma
            logger.info("Publicada %s en el canal %s.", ruta.name, CANAL_SALIDA_BOT)
        finally:
            imagen.close()

    async def procesar(self, ahora):
        fechas, estados = await self._datos()
        actual = self.estado.get("actual")
        inicio_ciclo = False
        if actual:
            nombre = actual["nombre"]
            fecha = datetime.fromisoformat(actual["fecha"])
            estado_actual = estados.get(nombre)
            anterior = actual.get("estado_anterior")
            if anterior == "vivo" and estado_actual == "muerto":
                clave = _clave(nombre, fecha)
                if clave not in self.estado["completados"]:
                    self.estado["completados"].append(clave)
                self.estado["actual"] = None
                _guardar_estado(self.ruta_estado, self.estado)
                self.publicado = None
                actual = None
                logger.info("%s pasó a MUERTO; buscando el siguiente raid.", nombre)
            elif nombre == "fafureon" and nombre not in fechas and any(
                fecha.date() == otra.date() for otro, otra in fechas.items() if otro in {"valakas", "antharas"}
            ):
                self.estado["actual"] = None
                _guardar_estado(self.ruta_estado, self.estado)
                self.publicado = None
                actual = None
            else:
                fecha_nueva = fechas.get(nombre)
                cambio = False
                if fecha_nueva and fecha_nueva != fecha and not actual.get("apertura") and estado_actual != "vivo":
                    actual["fecha"] = fecha_nueva.isoformat()
                    cambio = True
                if anterior == "muerto" and estado_actual == "vivo":
                    actual["apertura"] = ahora.isoformat()
                    cambio = True
                    logger.info("%s detectado VIVO a las %s; la fuente no informa la hora real.", nombre, ahora.isoformat())
                if estado_actual and estado_actual != anterior:
                    actual["estado_anterior"] = estado_actual
                    cambio = True
                if cambio:
                    _guardar_estado(self.ruta_estado, self.estado)

        if actual and not actual.get("apertura") and actual.get("estado_anterior") != "vivo":
            pendientes = sorted(
                (fecha, nombre) for nombre, fecha in fechas.items()
                if _clave(nombre, fecha) not in self.estado["completados"]
            )
            fecha_actual = datetime.fromisoformat(actual["fecha"])
            if pendientes and pendientes[0] < (fecha_actual, actual["nombre"]):
                self.estado["actual"] = None
                _guardar_estado(self.ruta_estado, self.estado)
                self.publicado = None
                actual = None

        if actual is None:
            candidatos = sorted(
                ((fecha, nombre) for nombre, fecha in fechas.items()
                 if _clave(nombre, fecha) not in self.estado["completados"]),
            )
            if not candidatos:
                if self.estado.get("mensaje_id") is not None or self.publicado is not None:
                    await self._limpiar()
                    self.publicado = None
                return
            fecha, nombre = candidatos[0]
            actual = {
                "nombre": nombre,
                "fecha": fecha.isoformat(),
                "estado_anterior": estados.get(nombre),
                "apertura": None,
            }
            self.estado["actual"] = actual
            _guardar_estado(self.ruta_estado, self.estado)
            inicio_ciclo = True

        nombre = actual["nombre"]
        fecha = datetime.fromisoformat(actual["fecha"])
        apertura = datetime.fromisoformat(actual["apertura"]) if actual.get("apertura") else None
        if apertura:
            if nombre == "fafureon":
                await self._publicar(nombre, "s", None)
            elif ahora >= apertura + TIEMPO_CIERRE:
                await self._publicar(nombre, "c", None)
            else:
                await self._publicar(None, "", apertura.strftime("%H:%M:%S"))
        else:
            hora_cartel = fecha - timedelta(minutes=30)
            texto = hora_cartel.strftime("%d/%m   %H:%M")
            if inicio_ciclo:
                await self._publicar(nombre, "", texto)
            if actual.get("estado_anterior") == "vivo":
                variante = ""
            elif ahora >= fecha:
                variante = "r"
            elif ahora >= hora_cartel:
                variante = "a"
            else:
                variante = ""
            await self._publicar(nombre, variante, texto)


async def iniciar_monitoreo_salida_bot(bot, ruta_json, json_lock):
    """Publica el ciclo y conserva su estado junto al JSON de entrada."""
    await bot.wait_until_ready()
    error_estado = False
    while not bot.is_closed():
        try:
            monitor = MonitorSalidaBot(bot, ruta_json, json_lock)
            break
        except (OSError, ValueError, json.JSONDecodeError):
            if not error_estado:
                logger.exception("No se pudo cargar el estado de salida_bot; se reintentará.")
                error_estado = True
            await asyncio.sleep(INTERVALO_LECTURA)
    else:
        return
    logger.info("Monitoreo de salida_bot iniciado para el canal %s.", CANAL_SALIDA_BOT)
    error_ciclo = False
    while not bot.is_closed():
        try:
            await monitor.procesar(datetime.now(ZONA_ARGENTINA))
            if error_ciclo:
                logger.info("Monitoreo de salida_bot recuperado.")
                error_ciclo = False
        except Exception:
            if not error_ciclo:
                logger.exception("Error en el ciclo de salida_bot; se reintentará.")
                error_ciclo = True
        await asyncio.sleep(INTERVALO_LECTURA)