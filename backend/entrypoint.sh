#!/bin/sh
# Idempotente: migra + crea bucket. "init-only" termina tras init (servicio init).
set -eu

MODE="${1:-serve}"

wait_db() {
  python - "$DATABASE_URL" <<'PY'
import sys, time, os
try:
    import psycopg2
except ImportError:
    sys.exit(0)
url = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DATABASE_URL", "")
if url.startswith("sqlite"):
    sys.exit(0)
# psycopg2 no entiende el sufijo de driver SQLAlchemy ("+psycopg2"/"+psycopg")
for prefix in ("postgresql+psycopg2://", "postgresql+psycopg://", "postgresql+asyncpg://", "postgres+psycopg2://"):
    if url.startswith(prefix):
        url = "postgresql://" + url[len(prefix):]
        break
for i in range(60):
    try:
        c = psycopg2.connect(url, connect_timeout=5)
        c.close()
        sys.exit(0)
    except Exception as e:
        print(f"[entrypoint] db no lista ({i}): {e}", flush=True)
        time.sleep(2)
sys.exit(1)
PY
}

echo "[entrypoint] esperando DB..."
wait_db || { echo "[entrypoint] DB no disponible"; exit 1; }

echo "[entrypoint] flask db upgrade..."
# Nunca marcar migraciones como aplicadas si fallaron: ocultaría una base incompatible.
flask --app wsgi db upgrade

echo "[entrypoint] init bucket..."
USE_LOCAL="${S3_USE_LOCAL:-1}"
if [ "$USE_LOCAL" = "1" ]; then
  echo "[entrypoint] S3_USE_LOCAL=1: almacenamiento local, omito bucket."
else
python - <<'PY'
import os
try:
    import boto3
    from botocore.client import Config
    ep = os.environ.get("S3_ENDPOINT", "")
    if ep:
        s3 = boto3.client("s3", endpoint_url=ep,
                          aws_access_key_id=os.environ.get("S3_ACCESS_KEY", "minioadmin"),
                          aws_secret_access_key=os.environ.get("S3_SECRET_KEY", "minioadmin"),
                          region_name=os.environ.get("S3_REGION", "us-east-1"),
                          config=Config(signature_version="s3v4"))
        bkt = os.environ.get("S3_BUCKET", "servator")
        try:
            s3.head_bucket(Bucket=bkt)
            print(f"[entrypoint] bucket {bkt} existe")
        except Exception:
            s3.create_bucket(Bucket=bkt)
            print(f"[entrypoint] bucket {bkt} creado")
    else:
        print("[entrypoint] sin S3_ENDPOINT, omito bucket (modo local)")
except Exception as e:
    print(f"[entrypoint] bucket omitido: {e}")
PY
fi

if [ "$MODE" = "init-only" ]; then
  chown -R 10001:10001 /models /data 2>/dev/null || \
    echo "[entrypoint] aviso: no se pudo ajustar ownership (montaje externo?)"
  echo "[entrypoint] init completo."
  exit 0
fi

# Permisos de volúmenes para el worker (uid 10001): solo init los ajusta (root).
if [ "$MODE" = "fix-perms" ]; then
  chown -R 10001:10001 /models /data 2>/dev/null || \
    echo "[entrypoint] aviso: no se pudo ajustar ownership (montaje externo?)"
  echo "[entrypoint] permisos listos."
  exit 0
fi

if [ "$#" -eq 0 ]; then
  set -- gunicorn -c gunicorn.conf.py wsgi:app
fi
echo "[entrypoint] ejecutando: $*"
exec "$@"
