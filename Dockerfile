# Imagen base mínima
FROM python:3.11-slim

# Buenas prácticas de ejecución y menos caché
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 🔧 Instalar SIEMPRE deps de sistema para bluepy
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc make pkg-config \
    libbluetooth-dev libglib2.0-dev bluez \
    && rm -rf /var/lib/apt/lists/*

# Instalar Poetry (versionado) sin cache
RUN pip install --no-cache-dir "poetry==1.8.3"

# Config Poetry: sin virtualenvs, no interacción y cache temporal
ENV POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

# Copiar solo metadatos para aprovechar la caché de dependencias
COPY pyproject.toml poetry.lock* /app/

# Instalar solo dependencias de runtime (no instala el propio proyecto)
RUN poetry install --only main --no-root && rm -rf "$POETRY_CACHE_DIR"

# Copiar el paquete
COPY src /app/src

# Usuario no root
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# Ejecutar el módulo principal
CMD ["python", "-m", "gateway.main"]
