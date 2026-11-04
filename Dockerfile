FROM python:3.12-slim

# Evita perguntas interativas durante o apt-get
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=America/Sao_Paulo

# Instala LibreOffice (para conversão fiel de DOCX para PDF), fontes e utilitários
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer \
    fonts-dejavu \
    fonts-liberation \
    ca-certificates \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Cria diretórios de persistência e scratch
RUN mkdir -p /app/data /app/storage /app/temp

# Copia pyproject.toml e código-fonte
COPY pyproject.toml README.md ./
COPY source/ /app/source/

# Instala o pacote e suas dependências via pyproject.toml
RUN pip install --no-cache-dir .

# Ponto de entrada padrão (script CLI registrado no pyproject.toml)
ENTRYPOINT ["legalone-sync"]
