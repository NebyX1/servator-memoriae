#!/usr/bin/env bash
# Bootstrap idempotente Servator Memoriae. Nunca hace `down -v`.
# Uso: scripts/bootstrap.sh [--device auto|cpu|cuda] [--yes] [--help]
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
DEVICE_ARG="" ; YES=0
for a in "$@"; do
  case "$a" in
    --device) shift2=1 ;;
    --device=*) DEVICE_ARG="${a#--device=}" ;;
    auto|cpu|cuda) DEVICE_ARG="$a" ;;
    --yes|-y) YES=1 ;;
    --help|-h) sed -n '1,12p' "$0"; echo "Ej: scripts/bootstrap.sh --device auto"; exit 0 ;;
  esac
done
# captura valor tras --device suelto
prev=""
for a in "$@"; do
  if [ "$prev" = "--device" ]; then DEVICE_ARG="$a"; fi
  prev="$a"
done
DEVICE_ARG="${DEVICE_ARG:-auto}"
case "$DEVICE_ARG" in auto|cpu|cuda) ;; *) echo "Dispositivo inválido: use auto, cpu o cuda" >&2; exit 1 ;; esac
command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1 && docker info >/dev/null 2>&1 || { echo "Docker Compose o su motor no están disponibles" >&2; exit 1; }

log(){ echo "[bootstrap] $*"; }
have(){ command -v "$1" >/dev/null 2>&1; }

[ -f .env ] || { log ".env no existe -> copio .env.example"; cp .env.example .env; }
log ".env conservado (no se sobrescribe)."

# secretos: SECRET_KEY >=32
gen_secret(){ python3 -c "import secrets;print(secrets.token_hex(32))" 2>/dev/null || openssl rand -hex 32; }
if grep -q "cambiar-por" .env || ! grep -q "^SECRET_KEY=" .env; then
  S="$(gen_secret)"
  if grep -q "^SECRET_KEY=" .env; then sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$S/" .env; else echo "SECRET_KEY=$S" >> .env; fi
  log "SECRET_KEY generado."
fi
set -a; . ./.env; set +a

# perfil de dispositivo (persistir en .device)
resolve_device(){
  local want="$1" has_nvidia=0 has_toolkit=0
  have nvidia-smi && nvidia-smi -L >/dev/null 2>&1 && has_nvidia=1
  docker info 2>/dev/null | grep -qi nvidia && has_toolkit=1
  # Docker Desktop/WSL puede exponer /dev/dxg sin listar runtime NVIDIA.
  if [ "$want" = auto ] && [ "$has_nvidia" = 1 ] && [ "$has_toolkit" = 0 ]; then
    local probe_image=python:3.11-slim
    docker run --rm --gpus all --entrypoint /bin/sh "$probe_image" -c 'test -e /dev/nvidia0 || test -e /dev/dxg' >/dev/null 2>&1 && has_toolkit=1
  fi
  case "$want" in
    cpu) echo cpu ;;
    cuda) [ "$has_nvidia" = 1 ] || { echo "AVISO: --device cuda pero sin nvidia-smi; sigo con cuda (fallará inferencia GPU)." >&2; }; echo cuda ;;
    *) if [ "$has_nvidia" = 1 ] && [ "$has_toolkit" = 1 ]; then echo cuda; else echo cpu; fi ;;
  esac
}
DEVICE="$(resolve_device "$DEVICE_ARG")"
echo "$DEVICE" > .device
log "perfil dispositivo: $DEVICE (pedido: $DEVICE_ARG) -> .device"
# inyecta DEVICE_MODE + TORCH_INDEX_URL en .env sin duplicar
upsert(){ k="$1"; v="$2"; grep -q "^$k=" .env && sed -i "s|^$k=.*|$k=$v|" .env || echo "$k=$v" >> .env; }
if [ "$DEVICE" = "cuda" ]; then
  upsert DEVICE_MODE cuda
  upsert TORCH_INDEX_URL "https://download.pytorch.org/whl/cu130"
else
  upsert DEVICE_MODE cpu
  upsert TORCH_INDEX_URL "https://download.pytorch.org/whl/cpu"
fi
set -a; . ./.env; set +a

have docker || { log "ERROR: docker no instalado"; exit 1; }
docker compose version >/dev/null 2>&1 || { log "ERROR: docker compose v2 requerido"; exit 1; }

GPU_FLAG=""
if [ "$DEVICE" = "cuda" ]; then GPU_FLAG="-f docker-compose.gpu.yml"; log "GPU: override activado (worker-gpu + train-worker)."; else log "CPU: stack base (sin toolkit requerido)."; fi

CORE_SERVICES="init backend worker worker-setup dispatcher frontend"
if [ "$DEVICE" = "cuda" ]; then CORE_SERVICES="$CORE_SERVICES worker-gpu"; fi
log "build de servicios principales..."
# shellcheck disable=SC2086
docker compose -f docker-compose.yml $GPU_FLAG build $CORE_SERVICES
log "build del lector opcional PaddleOCR-VL..."
# shellcheck disable=SC2086
if docker compose -f docker-compose.yml $GPU_FLAG build paddle; then
  log "up (sin -v)..."
  # shellcheck disable=SC2086
  docker compose -f docker-compose.yml $GPU_FLAG up -d
else
  log "AVISO: no se pudo construir PaddleOCR-VL. Se iniciará Kraken; revisá la conexión y reintentá el bootstrap."
  # shellcheck disable=SC2086
  docker compose -f docker-compose.yml $GPU_FLAG stop paddle >/dev/null 2>&1 || true
  # shellcheck disable=SC2086
  docker compose -f docker-compose.yml $GPU_FLAG up -d $CORE_SERVICES
fi

log "esperando backend healthy..."
for i in $(seq 1 60); do
  if docker compose ps backend --format json 2>/dev/null | grep -qi "healthy\|running"; then break; fi
  sleep 3
done
docker compose ps

log "migrate + storage (servicio init ya lo hizo; refuerzo idempotente)..."
docker compose run --rm init || docker compose --profile tools run --rm init || true

log "descarga modelo (job prepare_model, idempotente)..."
docker compose exec -T backend python - <<'PY' || true
import os
os.environ.setdefault("FLASK_ENV", "production")
try:
    from wsgi import app
    with app.app_context():
        from app.models import Job, ModelVersion
        from app.services_queue import new_job, dispatch
        if ModelVersion.query.filter_by(version="v1").first():
            print("modelo v1 ya registrado, omito prepare_model")
        else:
            # usuario sistema: primer superadmin o sin usuario
            from app.models import User
            u = User.query.first()
            uid = u.id if u else None
            j = new_job("prepare_model", uid, {}, idem_key="prepare-v1", total=1)
            try:
                dispatch(j)
                print(f"prepare_model encolado {j.id} status={j.status}")
            except Exception as e:
                print(f"prepare_model PENDING (dispatcher lo tomará): {e}")
except Exception as e:
    print(f"prepare_model omitido: {e}")
PY

log "smoke tests..."
FRONT_PORT="${FRONT_PORT:-8787}"
curl -fsS "http://localhost:${FRONT_PORT}/health" && echo " frontend /health OK" || log "WARN frontend health falló"
curl -fsS "http://localhost:${FRONT_PORT}/ready" && echo " frontend /ready OK" || log "WARN ready falló (DB/modelo pendiente es normal al inicio)"
python3 scripts/diagnose.py || true

URL="http://localhost:${FRONT_PORT}"
log "=================================================="
log "URL: $URL"
log "modo: $DEVICE"
docker compose ps --format "table {{.Name}}\t{{.Status}}" || docker compose ps
if [ "${LOCAL_TEST_MODE:-0}" = "1" ]; then
  log "Modo de prueba local: acceso directo, sin contraseña."
else
  log "Primer acceso: creá admin con: docker compose exec backend flask --app wsgi create-admin (ADMIN_PASSWORD en entorno)"
fi
log "Informe: scripts/diagnose.py --json > .agent-report.json"
python3 scripts/diagnose.py --json > .agent-report.json || true
log "=================================================="
