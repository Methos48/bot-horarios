import os

# Credenciales principales y URLs
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PAGUINA_JUEGO = os.getenv("PAGUINA_JUEGO", "https://www.l2sudamerica.com/?page=boss")
SESSION_SECRET = os.getenv("SESSION_SECRET")
TZ = os.getenv("TZ", "America/Caracas")

# IDs de Canales de Discord (convertidos a enteros de manera segura)
def _get_int_env(key):
    val = os.getenv(key)
    try:
        return int(val) if val else None
    except ValueError:
        return None

MA_CHANNEL_ID = _get_int_env("MA")
RONDA_CHANNEL_ID = _get_int_env("RONDA")
CARGAR_HORARIO_CHANNEL_ID = _get_int_env("CARGAR_HORARIO")
HORARIO_CHANNEL_ID = _get_int_env("HORARIO")

# --- RUTAS DE RECURSOS (Imágenes, Fuentes y Plantillas) ---
DIR_IMAGENES = "imagen"
DIR_FUENTES = os.path.join(DIR_IMAGENES, "fuentes")
DIR_RAID = os.path.join(DIR_IMAGENES, "raid")
DIR_TABLAS = os.path.join(DIR_IMAGENES, "tablas")

# Archivos de Fuentes
FUENTE_APTOS = os.path.join(DIR_FUENTES, "Aptos Narrow.ttf")
FUENTE_BIOME = os.path.join(DIR_FUENTES, "Biome.ttf")

# Plantillas y Tablas principales (.png)
PLANTILLA_RONDA = os.path.join(DIR_TABLAS, "ronda.png")
PLANTILLA_HORARIO = os.path.join(DIR_TABLAS, "horario.png")
PLANTILLA_HORARIO2 = os.path.join(DIR_TABLAS, "horario2.png")
PLANTILLA_MA = os.path.join(DIR_TABLAS, "ma.png")

# Elementos gráficos adicionales de tablas (.webp)
TABLA_BLOODED = os.path.join(DIR_TABLAS, "Blooded.webp")
TABLA_FLOATING = os.path.join(DIR_TABLAS, "Floating.webp")
TABLA_PORTAL = os.path.join(DIR_TABLAS, "Portal.webp")
TABLA_SCROLL = os.path.join(DIR_TABLAS, "Scroll.webp")
