"""Bot de Discord que extrae texto de imágenes de horarios con OCR."""

from __future__ import annotations

import io
import asyncio
import json
import logging
import os
import subprocess

import discord
import pytesseract
import requests
from PIL import Image, ImageEnhance, UnidentifiedImageError
from discord.ext import commands
from pytesseract import TesseractError

# Configuración obligatoria para entornos Linux/Railway (Nixpacks)
pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'


CHANNEL_ID = 1548412740723286147
IMAGE_BATCH_WINDOW_SECONDS = 8
MAX_IMAGE_BYTES = 10 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 20


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("horario-bot")


intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
pending_images: list[tuple[discord.Message, discord.Attachment]] = []
pending_batch_task: asyncio.Task[None] | None = None
pending_batch_lock = asyncio.Lock()


class OneDriveUpdateError(RuntimeError):
    """Error controlado al localizar o actualizar el libro RAID."""


def is_image_attachment(attachment: discord.Attachment) -> bool:
    """Indica si un adjunto parece ser una imagen."""
    if attachment.content_type:
        return attachment.content_type.lower().startswith("image/")

    image_extensions = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff")
    return attachment.filename.lower().endswith(image_extensions)


def extract_text_from_image(image_bytes: bytes) -> str:
    """Ejecuta OCR sobre los bytes de una imagen aplicando preprocesamiento de contraste."""
    with Image.open(io.BytesIO(image_bytes)) as image:
        # Convertir a escala de grises
        gray_image = image.convert("L")
        
        # Aumentar la resolución al doble para mejorar la precisión del OCR en fuentes pequeñas
        width, height = gray_image.size
        resized_image = gray_image.resize((width * 2, height * 2), Image.Resampling.LANCZOS)
        
        # Aplicar un realce de contraste fuerte para destacar las letras claras sobre el fondo oscuro
        enhancer = ImageEnhance.Contrast(resized_image)
        enhanced_image = enhancer.enhance(2.0)
        
        language = os.getenv("TESSERACT_LANG", "spa+eng")
        return pytesseract.image_to_string(enhanced_image, lang=language).strip()


def download_image(url: str) -> bytes:
    """Descarga una imagen respetando un límite de tamaño."""
    response = requests.get(
        url,
        headers={"User-Agent": "horario-discord-bot/1.0"},
        timeout=DOWNLOAD_TIMEOUT_SECONDS,
        stream=True,
    )
    response.raise_for_status()

    content_length = response.headers.get("Content-Length")
    if content_length and int(content_length) > MAX_IMAGE_BYTES:
        raise ValueError("La imagen supera el límite de 10 MB.")

    image_bytes = bytearray()
    for chunk in response.iter_content(chunk_size=64 * 1024):
        image_bytes.extend(chunk)
        if len(image_bytes) > MAX_IMAGE_BYTES:
            raise ValueError("La imagen supera el límite de 10 MB.")

    return bytes(image_bytes)


def update_raid_workbook(ocr_text: str) -> dict[str, object]:
    """Actualiza la fecha del jefe reconocido usando el helper de Microsoft Graph."""
    try:
        completed = subprocess.run(
            ["node", "onedrive_graph.mjs"],
            input=json.dumps({"ocrText": ocr_text}, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except FileNotFoundError as error:
        raise OneDriveUpdateError("No está disponible Node.js para conectar con OneDrive.") from error
    except subprocess.TimeoutExpired as error:
        raise OneDriveUpdateError("Microsoft Graph tardó demasiado en responder.") from error

    output = completed.stdout.strip()
    if not output:
        raise OneDriveUpdateError("El conector de OneDrive no devolvió una respuesta.")

    try:
        result = json.loads(output)
    except json.JSONDecodeError as error:
        raise OneDriveUpdateError("La respuesta del conector de OneDrive no es válida.") from error

    if not result.get("ok"):
        raise OneDriveUpdateError(
            str(result.get("error", "No se pudo actualizar el libro RAID."))
        )

    return result


async def process_image_batch(
    batch: list[tuple[discord.Message, discord.Attachment]],
) -> None:
    """Procesa dos o más capturas juntas antes de actualizar el libro."""
    texts: list[str] = []
    failed_files: list[str] = []

    for _, attachment in batch:
        try:
            image_bytes = download_image(attachment.url)
            text = extract_text_from_image(image_bytes)
        except requests.RequestException:
            logger.exception("No se pudo descargar %s", attachment.url)
            failed_files.append(attachment.filename)
            continue
        except (UnidentifiedImageError, TesseractError, ValueError) as error:
            logger.warning("No se pudo procesar %s: %s", attachment.filename, error)
            failed_files.append(attachment.filename)
            continue
        except Exception:
            logger.exception("Error inesperado procesando %s", attachment.filename)
            failed_files.append(attachment.filename)
            continue

        if text:
            texts.append(text)
        else:
            failed_files.append(attachment.filename)

    reply_target = batch[-1][0]
    if not texts:
        await reply_target.reply("No encontré texto legible en las capturas recibidas.")
        return

    combined_text = "\n\n".join(texts)
    try:
        update = update_raid_workbook(combined_text)
    except OneDriveUpdateError as error:
        logger.warning("No se actualizó OneDrive para el lote de imágenes: %s", error)
        await reply_target.reply(
            f"Procesé {len(texts)} captura(s), pero no actualicé el libro RAID: {error}"
        )
        return

    updates = update.get("updates", [])
    update_summary = ", ".join(
        f"{item['boss']} → {item['sourceDateTime']} ({item['cell']})"
        for item in updates
    )
    status = (
        f"Procesé {len(texts)} captura(s) consecutiva(s). "
        f"Actualicé en {update['workbook']} / {update['worksheet']}: {update_summary}."
    )
    if failed_files:
        status += f" No pude leer: {', '.join(failed_files)}."

    await reply_target.reply(status[:1990])


async def queue_image_batch(
    message: discord.Message,
    attachments: list[discord.Attachment],
) -> None:
    """Agrupa capturas consecutivas mediante una ventana de espera reiniciable."""
    global pending_batch_task

    async with pending_batch_lock:
        pending_images.extend((message, attachment) for attachment in attachments)
        if pending_batch_task and not pending_batch_task.done():
            pending_batch_task.cancel()
        pending_batch_task = asyncio.create_task(flush_image_batch())


async def flush_image_batch() -> None:
    """Espera a que termine el lote y lo procesa como un único OCR."""
    global pending_batch_task

    try:
        await asyncio.sleep(IMAGE_BATCH_WINDOW_SECONDS)
    except asyncio.CancelledError:
        return

    async with pending_batch_lock:
        batch = pending_images.copy()
        pending_images.clear()
        pending_batch_task = None

    if batch:
        await process_image_batch(batch)


@bot.event
async def on_ready() -> None:
    """Registra que el bot terminó de conectarse."""
    logger.info("Bot conectado como %s", bot.user)


@bot.event
async def on_message(message: discord.Message) -> None:
    """Procesa imágenes enviadas al canal configurado por ID."""
    if message.author.bot:
        return

    if message.channel.id == CHANNEL_ID:
        image_attachments = [
            attachment
            for attachment in message.attachments
            if is_image_attachment(attachment)
        ]

        if image_attachments:
            await queue_image_batch(message, image_attachments)

    # Conserva disponibles los comandos de discord.py, como !help.
    await bot.process_commands(message)


def main() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError(
            "Falta la variable de entorno DISCORD_TOKEN. "
            "Configúrala con el token del bot de Discord."
        )

    bot.run(token)


if __name__ == "__main__":
    main()
