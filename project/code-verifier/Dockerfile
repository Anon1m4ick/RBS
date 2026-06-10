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

RUN python -m pip install --upgrade pip \
    && python -m pip install -e "./code-verifier[dev]"

WORKDIR /app/code-verifier

CMD ["python", "-m", "pytest"]
