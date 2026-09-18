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

# Rutas de archivos locales
EXCEL_LOCAL = "RAID.xlsm"
EXCEL_PROCESO = "RAID_PROCESO.xlsm"
