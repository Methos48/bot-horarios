import os

# Zona horaria principal (por defecto Argentina, sobreescrita por entorno si existe)
TZ = os.getenv("TZ", "America/Argentina/Buenos_Aires")

# Credenciales principales y URL
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PAGUINA_JUEGO = os.getenv("PAGUINA_JUEGO", "https://www.l2sudamerica.com/?page=boss")
SESSION_SECRET = os.getenv("SESSION_SECRET")

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
LOW_CHANNEL_ID = _get_int_env("RONDA_LOW")
RAID_CHANNEL_ID = _get_int_env("RAID")

# Lectura directa de la variable ENVIAR_MENSAJE
ENVIAR_MENSAJE_CHANNEL_ID = _get_int_env("ENVIAR_MENSAJE")

# --- NUEVA VARIABLE ---
MENSAJE_CLAN_CHANNEL_ID = _get_int_env("MENSAJE_CLAN")

# --- VARIABLES DE COMPATIBILIDAD PARA EVITAR ERRORES DE CANAL FALTANTE ---
if not HORARIO_CHANNEL_ID:
    HORARIO_CHANNEL_ID = _get_int_env("HORARIO_CHANNEL_ID") or MA_CHANNEL_ID

# --- RUTAS DE RECURSOS (Imágenes, Fuentes y Plantillas) ---
DIR_IMAGENES = "imagen"
DIR_FUENTES = os.path.join(DIR_IMAGENES, "fuentes")
DIR_RAID = os.path.join(DIR_IMAGENES, "raid")
DIR_TABLAS = os.path.join(DIR_IMAGENES, "tablas")
DIR_TEXTURA = os.path.join(DIR_IMAGENES, "textura")

# Referencia a la textura metálica
TEXTURA_METAL = os.path.join(DIR_TEXTURA, "metal_textura.jpg")

# Subcarpetas principales de RAID
DIR_CASTILLO = os.path.join(DIR_RAID, "castillo")
DIR_MORADO = os.path.join(DIR_RAID, "morado")
DIR_ROJO = os.path.join(DIR_RAID, "rojo")

# Subcarpetas de Morado y Rojo
DIR_MORADO_CASTILLO = os.path.join(DIR_MORADO, "castillo")
DIR_MORADO_RAID = os.path.join(DIR_MORADO, "raid")
DIR_ROJO_CASTILLO = os.path.join(DIR_ROJO, "castillo")
DIR_ROJO_RAID = os.path.join(DIR_ROJO, "raid")
DIR_RAID_PRINCIPAL = os.path.join(DIR_RAID, "raid")  # Carpeta imagen/raid

# Archivos de Fuentes
FUENTE_APTOS = os.path.join(DIR_FUENTES, "Aptos Narrow.ttf")
FUENTE_BIOME = os.path.join(DIR_FUENTES, "Biome.ttf")
FUENTE_BANKGOTHIC = os.path.join(DIR_FUENTES, "BankGothic Bold.ttf")

# Plantillas y Tablas principales (.png)
PLANTILLA_RONDA = os.path.join(DIR_TABLAS, "ronda.png")
PLANTILLA_RONDALOW = os.path.join(DIR_TABLAS, "rondalow.png")
PLANTILLA_HORARIO = os.path.join(DIR_TABLAS, "horario.png")
PLANTILLA_HORARIO2 = os.path.join(DIR_TABLAS, "horario2.png")
PLANTILLA_MA = os.path.join(DIR_TABLAS, "ma.png")

# Elementos gráficos adicionales de tablas (.webp)
TABLA_BLOODED = os.path.join(DIR_TABLAS, "Blooded.webp")
TABLA_FLOATING = os.path.join(DIR_TABLAS, "Floating.webp")
TABLA_PORTAL = os.path.join(DIR_TABLAS, "Portal.webp")
TABLA_SCROLL = os.path.join(DIR_TABLAS, "Scroll.webp")

# Recursos de la carpeta Castillo (Principal)
CASTILLO_ADEN = os.path.join(DIR_CASTILLO, "aden.png")
CASTILLO_ARMANDO = os.path.join(DIR_CASTILLO, "armando.png")
CASTILLO_DION = os.path.join(DIR_CASTILLO, "dion.png")
CASTILLO_DOMINGO = os.path.join(DIR_CASTILLO, "domingo.png")
CASTILLO_GIRAN = os.path.join(DIR_CASTILLO, "giran.png")
CASTILLO_GLUDIO = os.path.join(DIR_CASTILLO, "gludio.png")
CASTILLO_GODDARD = os.path.join(DIR_CASTILLO, "goddard.png")
CASTILLO_INNADRIL = os.path.join(DIR_CASTILLO, "innadril.png")
CASTILLO_OREN = os.path.join(DIR_CASTILLO, "oren.png")
CASTILLO_RUNE = os.path.join(DIR_CASTILLO, "rune.png")
CASTILLO_SABADO = os.path.join(DIR_CASTILLO, "sabado.png")
CASTILLO_SCHUTGART = os.path.join(DIR_CASTILLO, "schutgart.png")

# Recursos de la carpeta imagen/raid
RAID_ANTHARAS = os.path.join(DIR_RAID_PRINCIPAL, "antharas.png")
RAID_BAIUM = os.path.join(DIR_RAID_PRINCIPAL, "baium.png")
RAID_BALROG = os.path.join(DIR_RAID_PRINCIPAL, "balrog.png")
RAID_BARAKIEL = os.path.join(DIR_RAID_PRINCIPAL, "barakiel.png")
RAID_CORE = os.path.join(DIR_RAID_PRINCIPAL, "core.png")
RAID_DECARBIA = os.path.join(DIR_RAID_PRINCIPAL, "decarbia.png")
RAID_ELECTRICAL = os.path.join(DIR_RAID_PRINCIPAL, "electrical.png")
RAID_FAFUREON = os.path.join(DIR_RAID_PRINCIPAL, "fafureon.png")
RAID_FREYA = os.path.join(DIR_RAID_PRINCIPAL, "freya.png")
RAID_FRINTEZZA = os.path.join(DIR_RAID_PRINCIPAL, "frintezza.png")
RAID_GALAXIA = os.path.join(DIR_RAID_PRINCIPAL, "galaxia.png")
RAID_GOLKONDA = os.path.join(DIR_RAID_PRINCIPAL, "golkonda.png")
RAID_HEKATON = os.path.join(DIR_RAID_PRINCIPAL, "hekaton.png")
RAID_ORFEN = os.path.join(DIR_RAID_PRINCIPAL, "orfen.png")
RAID_QUEENANT = os.path.join(DIR_RAID_PRINCIPAL, "queenant.png")
RAID_QUEENSHYEED = os.path.join(DIR_RAID_PRINCIPAL, "queenshyeed.png")
RAID_URUKA = os.path.join(DIR_RAID_PRINCIPAL, "uruka.png")
RAID_VALAKAS = os.path.join(DIR_RAID_PRINCIPAL, "valakas.png")
RAID_ZAKEN = os.path.join(DIR_RAID_PRINCIPAL, "zaken.png")
RAID_ZARICHE = os.path.join(DIR_RAID_PRINCIPAL, "zariche.png")

# Recursos de la carpeta imagen/morado/castillo
MORADO_CASTILLO_ADEN = os.path.join(DIR_MORADO_CASTILLO, "aden.png")
MORADO_CASTILLO_DION = os.path.join(DIR_MORADO_CASTILLO, "dion.png")
MORADO_CASTILLO_DOMINGO = os.path.join(DIR_MORADO_CASTILLO, "domingo.png")
MORADO_CASTILLO_DOMINGO2 = os.path.join(DIR_MORADO_CASTILLO, "domingo2.png")
MORADO_CASTILLO_GIRAN = os.path.join(DIR_MORADO_CASTILLO, "giran.png")
MORADO_CASTILLO_GLUDIO = os.path.join(DIR_MORADO_CASTILLO, "gludio.png")
MORADO_CASTILLO_GODDARD = os.path.join(DIR_MORADO_CASTILLO, "goddard.png")
MORADO_CASTILLO_INNADRIL = os.path.join(DIR_MORADO_CASTILLO, "innadril.png")
MORADO_CASTILLO_OREN = os.path.join(DIR_MORADO_CASTILLO, "oren.png")
MORADO_CASTILLO_RUNE = os.path.join(DIR_MORADO_CASTILLO, "rune.png")
MORADO_CASTILLO_SABADO = os.path.join(DIR_MORADO_CASTILLO, "sabado.png")
MORADO_CASTILLO_SABADO2 = os.path.join(DIR_MORADO_CASTILLO, "sabado2.png")
MORADO_CASTILLO_SCHUTGART = os.path.join(DIR_MORADO_CASTILLO, "schutgart.png")

# Recursos de la carpeta imagen/morado/raid
MORADO_RAID_ANTHARASH = os.path.join(DIR_MORADO_RAID, "antharash.png")
MORADO_RAID_ANTHARASM = os.path.join(DIR_MORADO_RAID, "antharasm.png")
MORADO_RAID_BAIUM = os.path.join(DIR_MORADO_RAID, "baium.png")
MORADO_RAID_BALROG = os.path.join(DIR_MORADO_RAID, "balrog.png")
MORADO_RAID_BARAKIEL = os.path.join(DIR_MORADO_RAID, "barakiel.png")
MORADO_RAID_CORE = os.path.join(DIR_MORADO_RAID, "core.png")
MORADO_RAID_DECARBIA = os.path.join(DIR_MORADO_RAID, "decarbia.png")
MORADO_RAID_ELECTRICAL = os.path.join(DIR_MORADO_RAID, "electrical.png")
MORADO_RAID_FAFPUREONM = os.path.join(DIR_MORADO_RAID, "fafureonm.png")
MORADO_RAID_FREYA = os.path.join(DIR_MORADO_RAID, "freya.png")
MORADO_RAID_FRINTEZZA = os.path.join(DIR_MORADO_RAID, "frintezza.png")
MORADO_RAID_FUFUREONH = os.path.join(DIR_MORADO_RAID, "fufureonh.png")
MORADO_RAID_GALAXIA = os.path.join(DIR_MORADO_RAID, "galaxia.png")
MORADO_RAID_GOLKONDA = os.path.join(DIR_MORADO_RAID, "golkonda.png")
MORADO_RAID_HEKATON = os.path.join(DIR_MORADO_RAID, "hekaton.png")
MORADO_RAID_ORFEN = os.path.join(DIR_MORADO_RAID, "orfen.png")
MORADO_RAID_QUEENANT = os.path.join(DIR_MORADO_RAID, "queenant.png")
MORADO_RAID_QUEENSHYEED = os.path.join(DIR_MORADO_RAID, "queenshyeed.png")
MORADO_RAID_URUKA = os.path.join(DIR_MORADO_RAID, "uruka.png")
MORADO_RAID_VALAKASH = os.path.join(DIR_MORADO_RAID, "valakash.png")
MORADO_RAID_VALAKASM = os.path.join(DIR_MORADO_RAID, "valakasm.png")
MORADO_RAID_ZAKEN = os.path.join(DIR_MORADO_RAID, "zaken.png")
MORADO_RAID_ZARICHE = os.path.join(DIR_MORADO_RAID, "zariche.png")

# Recursos de la carpeta imagen/rojo/castillo
ROJO_CASTILLO_ADEN = os.path.join(DIR_ROJO_CASTILLO, "aden.png")
ROJO_CASTILLO_DION = os.path.join(DIR_ROJO_CASTILLO, "dion.png")
ROJO_CASTILLO_DOMINGO = os.path.join(DIR_ROJO_CASTILLO, "domingo.png")
ROJO_CASTILLO_DOMINGO2 = os.path.join(DIR_ROJO_CASTILLO, "domingo2.png")
ROJO_CASTILLO_GIRAN = os.path.join(DIR_ROJO_CASTILLO, "giran.png")
ROJO_CASTILLO_GLUDIO = os.path.join(DIR_ROJO_CASTILLO, "gludio.png")
ROJO_CASTILLO_GODDARD = os.path.join(DIR_ROJO_CASTILLO, "goddard.png")
ROJO_CASTILLO_INNADRIL = os.path.join(DIR_ROJO_CASTILLO, "innadril.png")
ROJO_CASTILLO_OREN = os.path.join(DIR_ROJO_CASTILLO, "oren.png")
ROJO_CASTILLO_RUNE = os.path.join(DIR_ROJO_CASTILLO, "rune.png")
ROJO_CASTILLO_SABADO = os.path.join(DIR_ROJO_CASTILLO, "sabado.png")
ROJO_CASTILLO_SABADO2 = os.path.join(DIR_ROJO_CASTILLO, "sabado2.png")
ROJO_CASTILLO_SCHUTGART = os.path.join(DIR_ROJO_CASTILLO, "schutgart.png")

# Recursos de la carpeta imagen/rojo/raid
ROJO_RAID_ANTHARASH = os.path.join(DIR_ROJO_RAID, "antharash.png")
ROJO_RAID_ANTHARASM = os.path.join(DIR_ROJO_RAID, "antharasm.png")
ROJO_RAID_BAIUM = os.path.join(DIR_ROJO_RAID, "baium.png")
ROJO_RAID_BALROG = os.path.join(DIR_ROJO_RAID, "balrog.png")
ROJO_RAID_BARAKIEL = os.path.join(DIR_ROJO_RAID, "barakiel.png")
ROJO_RAID_CORE = os.path.join(DIR_ROJO_RAID, "core.png")
ROJO_RAID_DECARBIA = os.path.join(DIR_ROJO_RAID, "decarbia.png")
ROJO_RAID_ELECTRICAL = os.path.join(DIR_ROJO_RAID, "electrical.png")
ROJO_RAID_FAFPUREONH = os.path.join(DIR_ROJO_RAID, "fafureonh.png")
ROJO_RAID_FAFPUREONM = os.path.join(DIR_ROJO_RAID, "fafureonm.png")
ROJO_RAID_FREYA = os.path.join(DIR_ROJO_RAID, "freya.png")
ROJO_RAID_FRINTEZZA = os.path.join(DIR_ROJO_RAID, "frintezza.png")
ROJO_RAID_GALAXIA = os.path.join(DIR_ROJO_RAID, "galaxia.png")
ROJO_RAID_GOLKONDA = os.path.join(DIR_ROJO_RAID, "golkonda.png")
ROJO_RAID_HEKATON = os.path.join(DIR_ROJO_RAID, "hekaton.png")
ROJO_RAID_ORFEN = os.path.join(DIR_ROJO_RAID, "orfen.png")
ROJO_RAID_QUEENANT = os.path.join(DIR_ROJO_RAID, "queenant.png")
ROJO_RAID_QUEENSHYEED = os.path.join(DIR_ROJO_RAID, "queenshyeed.png")
ROJO_RAID_URUKA = os.path.join(DIR_ROJO_RAID, "uruka.png")
ROJO_RAID_VALAKASH = os.path.join(DIR_ROJO_RAID, "valakash.png")
ROJO_RAID_VALAKASM = os.path.join(DIR_ROJO_RAID, "valakasm.png")
ROJO_RAID_ZAKEN = os.path.join(DIR_ROJO_RAID, "zaken.png")
ROJO_RAID_ZARICHE = os.path.join(DIR_ROJO_RAID, "zariche.png")
