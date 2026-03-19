FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml README.md ./
COPY src ./src
COPY knowledge ./knowledge

RUN pip install --no-cache-dir .

CMD ["uvicorn", "outbreaks.cag.api:app", "--host", "0.0.0.0", "--port", "8000"]
