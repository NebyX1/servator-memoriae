# Aislado de Kraken: comparte solamente las capas de Python/torch del worker.
# Compose inyecta el worker CPU o el worker GPU cu130 como contexto de build.
FROM worker_base

USER root
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
# Kraken se ejecuta en sus propios workers; no mezclar sus restricciones de
# click y safetensors con las del lector de documentos.
RUN pip uninstall -y kraken \
    && pip install --no-cache-dir "paddleocr[doc-parser]==3.7.0" "paddlex==3.7.2" "transformers==5.22.2"

COPY paddle_service/ /app/paddle_service/
COPY engine/paddle_assets.py engine/paddle_asset_manifest.json /app/engine/
RUN chown -R servator:servator /app/paddle_service
ENV PYTHONPATH=/app:/app/backend:/app/engine \
    PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1
USER servator
WORKDIR /app/backend
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4", "--timeout", "0", "paddle_service.server:app"]
