import asyncio
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from PIL import Image

import salida_bot


ZONA = salida_bot.ZONA_ARGENTINA
INICIO = datetime(2026, 11, 9, 15, 0, tzinfo=ZONA)


class CanalFalso:
    def __init__(self, usuario):
        self.usuario = usuario
        self.mensajes = []
        self.archivos = []

    async def history(self, limit=None):
        for mensaje in list(self.mensajes):
            yield mensaje

    async def send(self, file):
        mensaje = SimpleNamespace(id=len(self.archivos) + 1, author=self.usuario)

        async def borrar():
            self.mensajes.remove(mensaje)

        mensaje.delete = AsyncMock(side_effect=borrar)
        self.archivos.append(file.filename)
        self.mensajes.append(mensaje)
        return mensaje


class SalidaBotTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.ruta = Path(self.temporal.name) / "jefes_activos.json"
        self.usuario = SimpleNamespace(id=42)
        self.canal = CanalFalso(self.usuario)
        self.bot = MagicMock(user=self.usuario)
        self.bot.get_channel.return_value = self.canal
        self.monitor = salida_bot.MonitorSalidaBot(self.bot, self.ruta, asyncio.Lock())

    def guardar(self, fechas, estados):
        datos = {
            "raid_60_plus": [
                {"nombre": nombre, "datetime_iso": fecha.isoformat(), "estado": "MUERTO"}
                for nombre, fecha in fechas.items()
            ],
            "vivo_o_muerto": [
                {"nombre": nombre, "estado": estado}
                for nombre, estado in estados.items()
            ],
        }
        self.ruta.write_text(json.dumps(datos), encoding="utf-8")

    async def test_ciclo_completo_prioridad_estado_y_reinicio(self):
        fechas = {"valakas": INICIO, "antharas": INICIO + timedelta(days=1)}
        self.guardar(fechas, {"valakas": "MUERTO", "antharas": "MUERTO"})
        await self.monitor.procesar(INICIO - timedelta(days=1))
        self.assertEqual(self.canal.archivos, ["valakas.png"])
        await self.monitor.procesar(INICIO - timedelta(minutes=30, seconds=1))
        self.assertEqual(len(self.canal.archivos), 1)
        await self.monitor.procesar(INICIO - timedelta(minutes=30))
        self.assertEqual(self.canal.archivos[-1], "valakasa.png")
        await self.monitor.procesar(INICIO)
        self.assertEqual(self.canal.archivos[-1], "valakasr.png")
        self.guardar(fechas, {"valakas": "VIVO", "antharas": "MUERTO"})
        apertura = INICIO + timedelta(seconds=12)
        await self.monitor.procesar(apertura)
        self.assertEqual(self.canal.archivos[-1], "abrio.png")
        self.assertEqual(self.monitor.estado["actual"]["apertura"], apertura.isoformat())
        self.assertEqual(len(self.canal.mensajes), 1)

        reiniciado = salida_bot.MonitorSalidaBot(self.bot, self.ruta, asyncio.Lock())
        await reiniciado.procesar(apertura + timedelta(minutes=32, seconds=59))
        self.assertEqual(self.canal.archivos[-1], "abrio.png")
        await reiniciado.procesar(apertura + timedelta(minutes=33))
        self.assertEqual(self.canal.archivos[-1], "valakasc.png")
        self.guardar(fechas, {"valakas": "MUERTO", "antharas": "MUERTO"})
        await reiniciado.procesar(apertura + timedelta(minutes=34))
        self.assertEqual(self.canal.archivos[-1], "antharas.png")
        self.assertEqual(len(self.canal.mensajes), 1)
        await reiniciado.procesar(apertura + timedelta(minutes=35))
        self.assertEqual(self.canal.archivos.count("antharas.png"), 1)

    async def test_fafureon_y_exclusion_por_fecha_argentina(self):
        fechas = {
            "fafureon": INICIO,
            "valakas": INICIO.astimezone(timezone.utc) + timedelta(hours=1),
            "antharas": INICIO + timedelta(days=1),
        }
        self.guardar(fechas, {nombre: "MUERTO" for nombre in fechas})
        await self.monitor.procesar(INICIO - timedelta(days=1))
        self.assertEqual(self.canal.archivos[-1], "valakas.png")
        self.guardar({"fafureon": INICIO}, {"fafureon": "MUERTO"})
        self.monitor.estado["actual"] = None
        await self.monitor.procesar(INICIO - timedelta(minutes=1))
        self.assertEqual(self.canal.archivos[-1], "fafureona.png")
        self.guardar({"fafureon": INICIO}, {"fafureon": "VIVO"})
        await self.monitor.procesar(INICIO)
        self.assertEqual(self.canal.archivos[-1], "fafureons.png")
        await self.monitor.procesar(INICIO + timedelta(minutes=40))
        self.assertEqual(self.canal.archivos[-1], "fafureons.png")

    async def test_ya_vivo_al_arrancar_sin_inventar_apertura(self):
        self.guardar({"antharas": INICIO}, {"antharas": "VIVO"})
        await self.monitor.procesar(INICIO + timedelta(minutes=10))
        self.assertEqual(self.canal.archivos[-1], "antharas.png")
        self.assertIsNone(self.monitor.estado["actual"]["apertura"])
        await self.monitor.procesar(INICIO + timedelta(hours=1))
        self.assertEqual(self.canal.archivos, ["antharas.png"])
        self.guardar({"antharas": INICIO}, {"antharas": "MUERTO"})
        await self.monitor.procesar(INICIO + timedelta(hours=1, seconds=1))
        self.assertEqual(len(self.canal.mensajes), 0)
        self.assertIsNone(self.monitor.estado["actual"])

    async def test_error_de_dibujado_no_elimina_mensaje_anterior(self):
        self.guardar({"valakas": INICIO}, {"valakas": "MUERTO"})
        await self.monitor.procesar(INICIO - timedelta(hours=1))
        with patch.object(salida_bot, "_estampar", side_effect=OSError("falta archivo")):
            with self.assertRaises(OSError):
                await self.monitor.procesar(INICIO)
        self.assertEqual(len(self.canal.mensajes), 1)
        self.assertEqual(self.canal.archivos[-1], "valakas.png")
        await self.monitor.procesar(INICIO)
        self.assertEqual(self.canal.archivos[-1], "valakasr.png")

    async def test_cambia_al_siguiente_si_muere_antes_de_33_minutos(self):
        fechas = {"valakas": INICIO, "antharas": INICIO + timedelta(days=1)}
        self.guardar(fechas, {"valakas": "MUERTO", "antharas": "MUERTO"})
        await self.monitor.procesar(INICIO - timedelta(days=1))
        self.guardar(fechas, {"valakas": "VIVO", "antharas": "MUERTO"})
        await self.monitor.procesar(INICIO)
        self.assertEqual(self.canal.archivos[-1], "abrio.png")
        self.guardar(fechas, {"valakas": "MUERTO", "antharas": "MUERTO"})
        await self.monitor.procesar(INICIO + timedelta(minutes=1))
        self.assertEqual(self.canal.archivos[-1], "antharas.png")
        await self.monitor.procesar(INICIO + timedelta(minutes=33))
        self.assertNotIn("valakasc.png", self.canal.archivos)

    async def test_inicio_durante_ventana_publica_base_y_fase_actual(self):
        self.guardar({"valakas": INICIO}, {"valakas": "MUERTO"})
        await self.monitor.procesar(INICIO - timedelta(minutes=15))
        self.assertEqual(self.canal.archivos, ["valakas.png", "valakasa.png"])
        self.assertEqual(len(self.canal.mensajes), 1)

    async def test_nuevo_horario_mas_proximo_reemplaza_cartelera(self):
        self.guardar({"valakas": INICIO + timedelta(days=1)}, {"valakas": "MUERTO"})
        await self.monitor.procesar(INICIO - timedelta(days=1))
        self.guardar(
            {"valakas": INICIO + timedelta(days=1), "antharas": INICIO},
            {"valakas": "MUERTO", "antharas": "MUERTO"},
        )
        await self.monitor.procesar(INICIO - timedelta(hours=1))
        self.assertEqual(self.canal.archivos[-1], "antharas.png")
        self.assertEqual(len(self.canal.mensajes), 1)

    async def test_lectura_espera_el_lock_compartido(self):
        self.guardar({"valakas": INICIO}, {"valakas": "MUERTO"})
        async with self.monitor.json_lock:
            tarea = asyncio.create_task(self.monitor._datos())
            await asyncio.sleep(0)
            self.assertFalse(tarea.done())
        fechas, estados = await tarea
        self.assertEqual(fechas["valakas"], INICIO)
        self.assertEqual(estados["valakas"], "muerto")

    async def test_fecha_y_hora_estampadas_con_resta_y_apertura(self):
        self.guardar({"antharas": INICIO.replace(hour=0, minute=15)}, {"antharas": "MUERTO"})
        estampados = []

        def estampar(ruta, texto):
            estampados.append((ruta.name, texto))
            return io.BytesIO(b"png")

        with patch.object(salida_bot, "_estampar", side_effect=estampar):
            await self.monitor.procesar(INICIO - timedelta(days=1))
            self.guardar({"antharas": INICIO.replace(hour=0, minute=15)}, {"antharas": "VIVO"})
            await self.monitor.procesar(INICIO + timedelta(seconds=47))
        self.assertEqual(estampados, [
            ("antharas.png", "08/11   23:45"),
            ("abrio.png", "15:00:47"),
        ])

    def test_recursos_graficos_reales(self):
        for plantilla, texto, dimensiones in (
            ("valakas.png", "08/11   23:45", (685, 404)),
            ("valakasa.png", "08/11   23:45", (685, 404)),
            ("valakasr.png", "08/11   23:45", (683, 403)),
            ("abrio.png", "15:00:47", (685, 404)),
            ("fafureons.png", None, (684, 404)),
        ):
            with salida_bot._estampar(salida_bot.DIR_PLANTILLAS / plantilla, texto) as archivo:
                with Image.open(archivo) as imagen:
                    self.assertEqual(imagen.size, dimensiones)
                    self.assertEqual(imagen.format, "PNG")

    def test_datos_invalidos_no_se_convierten_en_lista_vacia(self):
        with self.assertRaises(ValueError):
            salida_bot._leer_datos({"raid_60_plus": "inválido"})


if __name__ == "__main__":
    unittest.main()
