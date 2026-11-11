FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app:/app/engine \
    TORCH_INDEX_URL=${TORCH_INDEX_URL:-https://download.pytorch.org/whl/cpu}

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 10001 servator

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --index-url ${TORCH_INDEX_URL:-https://download.pytorch.org/whl/cpu} \
      "torch==2.14.0" "torchvision==0.29.0" \
 && pip install --no-cache-dir -r /tmp/requirements.txt \
 && pip install --no-cache-dir "kraken==7.1.1"

COPY backend/requirements-word.txt /tmp/requirements-word.txt
RUN pip install --no-cache-dir -r /tmp/requirements-word.txt

COPY backend/ /app/backend/
COPY backend/wsgi.py backend/gunicorn.conf.py /app/
COPY engine/ /app/engine/
COPY worker/run.py /app/worker/run.py

RUN chown -R servator:servator /app
USER servator
WORKDIR /app/backend
CMD ["python", "/app/worker/run.py"]
