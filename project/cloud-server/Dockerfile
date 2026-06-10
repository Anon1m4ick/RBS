FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        clamav \
        clamav-freshclam \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY code-verifier ./code-verifier
COPY cloud-server ./cloud-server

RUN python -m pip install --upgrade pip \
    && python -m pip install -e ./code-verifier -e "./cloud-server[dev]"

WORKDIR /app/cloud-server

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "oblak_server.main:app", "--host", "0.0.0.0", "--port", "8000"]
