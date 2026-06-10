FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY cdk-cli ./cdk-cli

RUN python -m pip install --upgrade pip \
    && python -m pip install -e ./cdk-cli

WORKDIR /workspace

ENTRYPOINT ["cdk"]
