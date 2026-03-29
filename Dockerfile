FROM python:3.11-slim

# Instalar dependencias del sistema (necesarias para bots de música)
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

# === SOLUCIÓN AL ERROR ACTUAL ===
# Copiar primero requirements.txt desde la raíz del proyecto
COPY requirements.txt .

# Actualizar pip e instalar dependencias
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

# Iniciar el bot (cambia "main.py" si tu archivo principal se llama diferente)
CMD ["python", "main.py"]
