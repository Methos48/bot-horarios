import os
from salida_bot import _estampar, DIR_PLANTILLAS

if __name__ == "__main__":
    print("Generando pruebas usando EXACTAMENTE la misma función de salida_bot.py...")

    # Textos de ejemplo simulando los formatos reales
    texto_antharas = "23/01   20:30"
    texto_abrio = "22:34:02"

    # Buscar plantillas
    plantilla_antharas = DIR_PLANTILLAS / "antharas.png"
    if not plantilla_antharas.exists():
        plantilla_antharas = DIR_PLANTILLAS / "antharas.jpg"

    plantilla_abrio = DIR_PLANTILLAS / "abrio.png"
    if not plantilla_abrio.exists():
        plantilla_abrio = DIR_PLANTILLAS / "abrio.jpg"

    # Ejecutar estampado de prueba para Antharas
    if plantilla_antharas.exists():
        io_antharas = _estampar(plantilla_antharas, texto_antharas)
        with open("prueba_antharas.png", "wb") as f:
            f.write(io_antharas.getbuffer())
        print("✅ Imagen de prueba actualizada: prueba_antharas.png")
    else:
        print("⚠️ No se encontró la plantilla de Antharas en imagen/bot/")

    # Ejecutar estampado de prueba para Abrio
    if plantilla_abrio.exists():
        io_abrio = _estampar(plantilla_abrio, texto_abrio)
        with open("prueba_abrio.png", "wb") as f:
            f.write(io_abrio.getbuffer())
        print("✅ Imagen de prueba actualizada: prueba_abrio.png")
    else:
        print("⚠️ No se encontró la plantilla de Abrio en imagen/bot/")