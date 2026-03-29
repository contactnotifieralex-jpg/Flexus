FROM python:3.11-slim

# Instalación de herramientas de audio
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

# Instalación de librerías
RUN pip install --no-cache-dir -r requirements.txt

# Comando para arrancar el bot
ENTRYPOINT ["python", "main.py"]
