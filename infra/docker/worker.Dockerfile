FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    libpq-dev \
    libproj-dev \
    proj-bin \
    proj-data \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml README.md ./
COPY config ./config
COPY src ./src
COPY knowledge ./knowledge
COPY services ./services
COPY pipelines ./pipelines
COPY libs ./libs

RUN uv pip install --system -e .

RUN useradd -m -u 1000 appuser && chown -R appuser /app
USER appuser

CMD ["python", "-m", "services.worker.app.main"]
