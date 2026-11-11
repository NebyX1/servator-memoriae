FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TORCH_INDEX_URL=${TORCH_INDEX_URL:-https://download.pytorch.org/whl/cpu}

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl ca-certificates procps \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /tmp/requirements.txt
# torch CPU primero (rueda CPU, imagen ligera)
RUN pip install --no-cache-dir --index-url ${TORCH_INDEX_URL:-https://download.pytorch.org/whl/cpu} \
      "torch==2.14.0" "torchvision==0.29.0" \
 && pip install --no-cache-dir -r /tmp/requirements.txt

COPY backend/ /app/
COPY engine/ /app/engine/
COPY scripts/dispatch.py /app/scripts_dispatch.py

RUN chmod +x /app/entrypoint.sh
EXPOSE 5000
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "-c", "gunicorn.conf.py", "wsgi:app"]
