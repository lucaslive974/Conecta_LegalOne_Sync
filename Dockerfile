FROM python:3.12-slim

# Avoid interactive prompts during apt-get
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=America/Sao_Paulo \
    DB_PATH=/app/data/historico_processos.db \
    STORAGE_DIR=/app/storage \
    TEMP_DIR=/app/temp

# Install LibreOffice (for accurate DOCX to PDF rendering), fonts, and utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer \
    fonts-dejavu \
    fonts-liberation \
    ca-certificates \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Create persistence and scratch directories
RUN mkdir -p /app/data /app/storage /app/temp

# Copy pyproject.toml and source code
COPY pyproject.toml README.md ./
COPY source/ /app/source/

# Install package and dependencies via pyproject.toml
RUN pip install --no-cache-dir .

# Default entry point (CLI script declared in pyproject.toml)
ENTRYPOINT ["legalone-sync"]
