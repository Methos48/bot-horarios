import os
import logging
import io
import discord
import config

logger = logging.getLogger("ComandosBot")

# Diccionario de mapeo de comandos permitidos (sin la barra inicial) a su archivo de imagen correspondiente
COMANDOS_VALIDOS = {
    "4s": "4s.png",
    "anakim": "anakim.png",
    "antharas": "antharas.png",
    "armando": "armando.png",
    "asedio": "asedio.png",
    "baium": "baium.png",
    "balrog": "balrog.png",
    "core": "core.png",
    "electrical": "electrical.png",
    "fafureon": "fafureon.png",
    "freya": "freya.png",
    "frintezza": "frintezza.png",
    "ketra": "ketra.png",
    "lilith": "lilith.png",
    "monas": "monas.png",
    "orfen": "orfen.png",
    "pagan": "pagan.png",
    "pvp": "pvp.png",
    "pvp2": "pvp2.png",
    "pvp3": "pvp3.png",
    "valakas": "valakas.png",
    "varka": "varka.png",
    "zaken": "zaken.png",
    "zariche": "zariche.png",
    # Variantes para Queen Ant (apuntan a queenant.png o la que corresponda en la carpeta)
    "queenant": "queenant.png",
    "queen": "queenant.png",
    "quen": "queenant.png"
}

def registrar_comandos_bot(bot_instance):
    @bot_instance.event
    async def on_message(message: discord.Message):
        # Evitar que el bot responda a sus propios mensajes
        if message.author.bot:
            return

        # Obtener el canal de clan configurado
        canal_clan_id = getattr(config, "MENSAJE_CLAN_CHANNEL_ID", None)
        if not canal_clan_id or message.channel.id != canal_clan_id:
            return

        contenido = message.content.strip()

        # Verificar que sea un comando (comience con '/')
        if not contenido.startswith('/'):
            return

        # Extraer el comando sin la barra y pasarlo a minúsculas para ignorar mayúsculas/minúsculas
        comando_limpio = contenido[1:].lower()

        if comando_limpio in COMANDOS_VALIDOS:
            nombre_archivo = COMANDOS_VALIDOS[comando_limpio]
            
            # Construir la ruta basada en la estructura proporcionada
            directorio_armando = getattr(config, "DIR_ARMANDO", "imagen/raid/raid/armando")
            ruta_imagen = os.path.join(directorio_armando, nombre_archivo)

            if not os.path.exists(ruta_imagen):
                logger.warning(f"⚠️ La plantilla '{nombre_archivo}' no se encontró en '{directorio_armando}'.")
                return

            # Intentar borrar el mensaje original del usuario
            try:
                await message.delete()
            except discord.Forbidden:
                logger.warning("⚠️ No tengo permisos para eliminar mensajes en este canal.")
            except discord.HTTPException as e:
                logger.error(f"❌ Error al intentar borrar el mensaje: {e}")

            # Enviar la imagen correspondiente al canal
            try:
                img = Image.open(ruta_imagen) if 'Image' in globals() else None
                # Si prefieres abrirla con PIL para validación o enviarla directamente por archivo binario:
                with open(ruta_imagen, "rb") as f:
                    archivo_discord = discord.File(f, filename=nombre_archivo)
                    await message.channel.send(file=archivo_discord)
            except Exception as e:
                logger.error(f"❌ Error al enviar la imagen del comando /{comando_limpio}: {e}")
