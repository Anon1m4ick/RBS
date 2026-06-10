FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        e2fsprogs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY firecracker-runner ./firecracker-runner

RUN python -m pip install --upgrade pip \
    && python -m pip install -e ./firecracker-runner

WORKDIR /workspace

ENTRYPOINT ["oblak-firecracker-run"]
