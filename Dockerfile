FROM python:3.13-slim

# Instalar Tesseract OCR y dependencias del sistema operativo
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-spa \
    && rm -rf /var/lib/apt/lists/*

# Configurar el directorio de trabajo
WORKDIR /app

# Copiar e instalar las dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código del bot
COPY . .

# Comando para iniciar la aplicación (ejecutando gunicorn o python main.py según corresponda)
CMD ["python", "main.py"]
