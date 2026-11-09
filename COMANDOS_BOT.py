import os
import logging
import discord
from discord import app_commands
import config

logger = logging.getLogger("ComandosBot")

# Diccionario de mapeo de comandos permitidos a su archivo de imagen correspondiente
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
    "queenant": "queenant.png",
    "queen": "queenant.png",
    "quen": "queenant.png"
}

def registrar_comandos_bot(bot_instance):
    """Registra dinámicamente los comandos de barra (slash commands) en el bot de Discord."""
    
    # Función auxiliar para procesar y enviar la imagen correspondiente
    async def enviar_imagen_comando(interaction: discord.Interaction, nombre_comando: str):
        # Verificar el canal de clan configurado
        canal_clan_id = getattr(config, "MENSAJE_CLAN_CHANNEL_ID", None)
        if canal_clan_id and interaction.channel_id != canal_clan_id:
            await interaction.response.send_message("❌ Este comando no se puede usar en este canal.", ephemeral=True)
            return

        nombre_archivo = COMANDOS_VALIDOS.get(nombre_comando)
        if not nombre_archivo:
            await interaction.response.send_message("❌ Comando no reconocido.", ephemeral=True)
            return

        directorio_armando = getattr(config, "DIR_ARMANDO", "imagen/raid/raid/armando")
        ruta_imagen = os.path.join(directorio_armando, nombre_archivo)

        if not os.path.exists(ruta_imagen):
            logger.warning(f"⚠️ La plantilla '{nombre_archivo}' no se encontró en '{directorio_armando}'.")
            await interaction.response.send_message("❌ La imagen solicitada no se encuentra disponible en el servidor.", ephemeral=True)
            return

        try:
            # Diferimos la respuesta para evitar tiempos de espera agotados en Discord
            await interaction.response.defer()
            with open(ruta_imagen, "rb") as f:
                archivo_discord = discord.File(f, filename=nombre_archivo)
                await interaction.followup.send(file=archivo_discord)
        except Exception as e:
            logger.error(f"❌ Error al enviar la imagen del comando /{nombre_comando}: {e}")
            try:
                await interaction.followup.send("❌ Hubo un error al enviar la imagen.", ephemeral=True)
            except:
                pass

    # Registrar cada comando de forma dinámica en el árbol del bot
    for cmd in COMANDOS_VALIDOS.keys():
        
        # Creamos una función closure correcta fijando el comando actual con c=cmd
        def fabricar_callback(c=cmd):
            async def callback(interaction: discord.Interaction):
                await enviar_imagen_comando(interaction, c)
            return callback

        # Definimos el comando de barra con app_commands.Command
        slash_cmd = app_commands.Command(
            name=cmd,
            description=f"Muestra la plantilla de estrategia para {cmd}",
            callback=fabricar_callback()
        )
        
        # Añadimos el comando al árbol global del bot
        bot_instance.tree.add_command(slash_cmd)
        
    logger.info(f"✅ Se registraron {len(COMANDOS_VALIDOS)} comandos de barra de raids correctamente.")
