import unittest
import os
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import salida_ronda


AHORA = datetime(2026, 11, 9, 0, 15, tzinfo=salida_ronda.ZONA_ARGENTINA)


class FechaFija(datetime):
    @classmethod
    def now(cls, tz=None):
        return AHORA.astimezone(tz)


def fecha_fija(fecha):
    return FechaFija.fromtimestamp(fecha.timestamp(), fecha.tzinfo)


class SalidaRondaTest(unittest.IsolatedAsyncioTestCase):
    async def renderizar(self, registros):
        canal = MagicMock()

        async def historial_vacio():
            if False:
                yield None

        canal.history.side_effect = lambda **kwargs: historial_vacio()
        canal.send = AsyncMock()
        dibujo = MagicMock()
        imagen = MagicMock()
        imagen.convert.return_value = imagen
        bot = MagicMock()

        with (
            patch.object(salida_ronda, "datetime", FechaFija),
            patch.object(salida_ronda, "SERVIDORES_RONDA", [1]),
            patch.object(salida_ronda, "_obtener_canal", AsyncMock(side_effect=lambda bot, cid: canal if cid == 1 else None)),
            patch.object(salida_ronda.Image, "open", return_value=imagen),
            patch.object(salida_ronda.ImageDraw, "Draw", return_value=dibujo),
            patch.object(salida_ronda.discord, "File"),
        ):
            await salida_ronda.ejecutar(bot, registros)

        canal.send.assert_awaited_once()
        textos = [
            (llamada.args[0], llamada.args[1])
            for llamada in dibujo.text.call_args_list
        ]
        nombres = [texto for (x, _), texto in textos if x in (16, 340)]
        horas = [texto for (x, _), texto in textos if x in (265, 590)]
        return nombres, horas, dibujo

    async def test_limites_prioridad_y_otras_categorias(self):
        registros = [
            {"nombre": "Asedio", "datetime": fecha_fija(AHORA)},
            {"nombre": "P V P", "datetime": fecha_fija(AHORA - timedelta(hours=2, minutes=29, seconds=59))},
            {"nombre": "pvp", "datetime": fecha_fija(AHORA - timedelta(hours=2, minutes=30))},
            {"nombre": "x9", "datetime": fecha_fija(AHORA - timedelta(hours=3))},
            {"nombre": "x 9", "datetime": fecha_fija(AHORA + timedelta(minutes=1))},
            {"nombre": "foto mes", "datetime": fecha_fija(AHORA - timedelta(minutes=1))},
            {"nombre": "Core", "datetime": fecha_fija(AHORA - timedelta(hours=3))},
            {"nombre": "Zaken", "datetime": fecha_fija(AHORA + timedelta(hours=1))},
            {"nombre": "Valakas", "nivel": 60, "estado": "VIVO"},
            {"nombre": "jefe", "nivel": 60, "estado": "VIVO"},
            {"nombre": "asedio especial", "datetime": fecha_fija(AHORA - timedelta(hours=3))},
        ]
        nombres, horas, _ = await self.renderizar(registros)

        self.assertEqual(nombres, [
            "Valakas", "Asedio", "foto mes", "P V P", "jefe",
            "Core", "asedio especial", "x 9", "Zaken",
        ])
        self.assertEqual(horas, [
            "VIVO", "EN CURSO", "EN CURSO", "EN CURSO", "VIVO",
            "21:15", "21:15", "00:16", "01:15",
        ])
        self.assertNotIn("tiempo_str_final", registros[0])

    async def test_fechas_invalidas_parseadas_y_otra_zona(self):
        registros = [
            {"nombre": "asedio", "tiempo_str": "-"},
            {"nombre": "pvp", "tiempo_str": "09/11/2026 00:14"},
            {"nombre": "x9", "datetime": fecha_fija(AHORA.astimezone(timezone.utc) - timedelta(minutes=1))},
            {"nombre": "foto mes", "estado": "VIVO", "datetime": fecha_fija(AHORA - timedelta(hours=4))},
            {"nombre": "x 9", "datetime": FechaFija.max.replace(tzinfo=salida_ronda.ZONA_ARGENTINA)},
        ]
        nombres, horas, _ = await self.renderizar(registros)
        self.assertEqual(nombres, ["foto mes", "pvp", "x9", "asedio", "x 9"])
        self.assertEqual(horas, ["VIVO", "EN CURSO", "EN CURSO", "-", "-"])

    async def test_texto_en_curso_cabe_en_ambas_columnas(self):
        registros = [
            {"nombre": "asedio", "datetime": fecha_fija(AHORA)},
            *({"nombre": "Valakas", "nivel": 60, "estado": "VIVO"} for _ in range(21)),
            {"nombre": "x9", "datetime": fecha_fija(AHORA)},
        ]
        _, _, dibujo = await self.renderizar(registros)
        llamadas = [llamada for llamada in dibujo.text.call_args_list if llamada.args[1] == "EN CURSO"]
        self.assertEqual({llamada.args[0][0] for llamada in llamadas}, {265, 266, 590, 591})
        for llamada in llamadas:
            fuente = llamada.kwargs["font"]
            self.assertLessEqual(fuente.getbbox("EN CURSO")[2], 49)

    async def test_ambas_variantes_limites_y_envio(self):
        canales = {cid: MagicMock() for cid in (1, 2, salida_ronda.CANAL_RONDA_CORTA)}
        bot = MagicMock()
        mensajes = {}
        for cid, canal in canales.items():
            mensaje = MagicMock()
            mensaje.author = bot.user
            mensaje.delete = AsyncMock()
            mensajes[cid] = mensaje

            async def historial(mensaje=mensaje, **kwargs):
                yield mensaje

            canal.history.side_effect = historial
            canal.send = AsyncMock()

        imagenes = [MagicMock(), MagicMock()]
        dibujos = [MagicMock(), MagicMock()]
        for imagen in imagenes:
            imagen.convert.return_value = imagen
        registros = [
            {"nombre": "asedio", "datetime": fecha_fija(AHORA)},
            {"nombre": "pvp", "datetime": fecha_fija(AHORA - timedelta(hours=2, minutes=30))},
            *({"nombre": f"jefe {i:02}", "nivel": 60, "estado": "VIVO"} for i in range(45)),
        ]
        with (
            patch.object(salida_ronda, "datetime", FechaFija),
            patch.object(salida_ronda, "SERVIDORES_RONDA", [1, 2]),
            patch.object(salida_ronda, "_obtener_canal", AsyncMock(side_effect=lambda bot, cid: canales[cid])),
            patch.object(salida_ronda.Image, "open", side_effect=imagenes) as abrir,
            patch.object(salida_ronda.ImageDraw, "Draw", side_effect=dibujos),
            patch.object(salida_ronda.discord, "File", side_effect=lambda archivo, filename: archivo),
        ):
            await salida_ronda.ejecutar(bot, registros)

        self.assertEqual([llamada.args[0] for llamada in abrir.call_args_list],
                         [salida_ronda.config.PLANTILLA_RONDA, salida_ronda.PLANTILLA_RONDA_CORTA])
        imagenes[0].save.assert_called_once_with("ronda_horario_final.png")
        imagenes[1].save.assert_called_once_with("ronda_horario_corto.png")
        for cid, canal in canales.items():
            mensajes[cid].delete.assert_awaited_once()
            archivo = "ronda_horario_corto.png" if cid == salida_ronda.CANAL_RONDA_CORTA else "ronda_horario_final.png"
            canal.send.assert_awaited_once_with(file=archivo)

        for dibujo, filas in zip(dibujos, (22, 14)):
            nombres = [(llamada.args[0], llamada.args[1])
                       for llamada in dibujo.text.call_args_list
                       if llamada.args[0][0] in (16, 340)]
            self.assertEqual(len(nombres), 2 * filas)
            self.assertEqual(nombres[0], ((16, 122), "asedio"))
            self.assertEqual(nombres[filas - 1][0], (16, 122 + (filas - 1) * 24))
            self.assertEqual(nombres[filas][0], (340, 122))
            self.assertEqual(nombres[-1][0], (340, 122 + (filas - 1) * 24))
            self.assertTrue(any(llamada.args[1] == "EN CURSO" for llamada in dibujo.text.call_args_list))
            self.assertFalse(any(llamada.args[1] == "pvp" for llamada in dibujo.text.call_args_list))

    async def test_fallo_plantilla_corta_no_impide_envio_normal(self):
        canal_normal = MagicMock()
        canal_corto = MagicMock()
        bot = MagicMock()
        for canal in (canal_normal, canal_corto):
            async def historial_vacio(**kwargs):
                if False:
                    yield None
            canal.history.side_effect = historial_vacio
            canal.send = AsyncMock()

        def generar(datos, plantilla, archivo, filas, aptos, biome):
            if filas == 14:
                raise OSError("plantilla corta inaccesible")

        with (
            patch.object(salida_ronda, "SERVIDORES_RONDA", [1]),
            patch.object(salida_ronda, "_obtener_canal", AsyncMock(side_effect=lambda bot, cid: canal_normal if cid == 1 else canal_corto)),
            patch.object(salida_ronda, "_generar_imagen", side_effect=generar),
            patch.object(salida_ronda.discord, "File"),
            self.assertLogs("SalidaRonda", level="ERROR") as logs,
        ):
            await salida_ronda.ejecutar(bot, [])
        canal_normal.send.assert_awaited_once()
        canal_corto.send.assert_not_awaited()
        canal_corto.history.assert_not_called()
        self.assertTrue(any("plantilla corta inaccesible" in mensaje for mensaje in logs.output))

    def test_generar_imagenes_reales(self):
        datos = [
            {"nombre": "asedio", "nivel": 60, "tiempo_str_final": "EN CURSO", "es_vivo": False},
            *({"nombre": f"jefe {i:02}", "nivel": 60, "tiempo_str_final": "VIVO", "es_vivo": True}
              for i in range(43)),
        ]
        with tempfile.TemporaryDirectory() as directorio:
            for plantilla, filas, dimensiones in (
                (salida_ronda.config.PLANTILLA_RONDA, 22, (653, 715)),
                (salida_ronda.PLANTILLA_RONDA_CORTA, 14, (651, 455)),
            ):
                archivo = os.path.join(directorio, f"ronda_{filas}.png")
                salida_ronda._generar_imagen(
                    datos, plantilla, archivo, filas,
                    salida_ronda.config.FUENTE_APTOS, salida_ronda.config.FUENTE_BIOME,
                )
                with salida_ronda.Image.open(archivo) as imagen:
                    self.assertEqual(imagen.size, dimensiones)
                    self.assertEqual(imagen.format, "PNG")


if __name__ == "__main__":
    unittest.main()
