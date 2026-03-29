FROM python:3.11-slim

# ==================== INSTALACIÓN DE DEPENDENCIAS DEL SISTEMA ====================
# Esto es lo que faltaba y lo que hace que falle el pip install
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    gcc \
    g++ \
    make \
    python3-dev \
    libopus-dev \
    libffi-dev \
    libsodium-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar requirements primero (mejora el cache de Docker)
COPY requirements.txt .

# Actualizar pip e instalar las librerías de Python
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código del bot
COPY . .

# Comando para iniciar el bot
ENTRYPOINT ["python", "main.py"]
