# Referencia de arquitectura — reutilización de geo-padrones (commit b442df6)

## Qué se reutilizó
Patrón Flask factory + blueprints + `ProxyFix` + CORS limitada a `/api/*` + `X-Request-ID`/`Cache-Control: no-store`; modelo `Job/JobEvent` con clave de idempotencia (`uq_job_idem`); RBAC por capacidades con decorador `require(cap)`; subida con sha256 y deduplicación; endpoints `/health` y `/ready`; errores JSON con `request_id`; CLI `create-admin`.

## Qué cambió (Servator Memoriae)
- Dominio: colecciones/documentos/páginas/renglones `Line` (baseline, polygon, auto/revised, confidence, state, version) + `SourceFile` (original inmutable) + `TranscriptionVersion` + `ModelVersion` + `TrainingRun` + `Export` + `AuditLog`.
- Motor OCR: `engine/kraken_adapter.py` (kraken 7.1.1, reconocedor PP-OCRv6 medium Zenodo 21788410, segmentador baseline kraken/blla). `transcribe_image` con carga perezosa en worker; `train_finetune` vía `ketos train`.
- Revisión con concurrencia optimista (`PATCH /lines/<id>` con `version`, 409 si colisiona) y estados `auto|confirmed|corrected|illegible|bad_cut|skipped`.
- Entrenamiento con snapshot inmutable, partición **por página** y **CER de corpus** (suma, no promedio).
- Exportación PDF facsímil (imagen + texto invisible por renglón, geometría original) y lectura (DejaVu/ñ/tildes, marca pendiente).

## Límites corregidos respecto al origen
| Límite | Corrección |
|---|---|
| Subidas | `MAX_UPLOAD_MB = 512` aplicado como `MAX_CONTENT_LENGTH` (413 si excede) + validación por archivo con mensaje claro. |
| Páginas | `MAX_PAGES_PER_FILE = 500`; PDF/TIFF que exceden se rechazan con error, no se truncan en silencio. |
| Timeouts | Descarga modelo 120 s; `ketos train` 8 h; login rate-limit 10/min; limiter global 300/min. |
| Streaming | Descarga y hash por bloques de 1 MB; escritura atómica `.part` → `os.replace`. |
| Modelos escribibles | `MODEL_DIR` y `MODEL_CACHE_DIR` configurables, creados con `makedirs`; registro `manifest.json` con sha/tamaño/fuente/licencia. |
| Smoke real | `smoke_test()` con inferencia sobre imagen sintética redistribuible; `test_engine_smoke.py` hace skip honesto si no hay modelo. |

## Decisiones de despliegue verificadas el 2026-11-10 (levantamiento real)
- `minio/minio` **ya no existe en Docker Hub** (pull: "repository does not exist",
  incluso `:latest`; `quay.io/minio/minio` exige auth no disponible aquí) y el tag
  `RELEASE.2024-12-18T16-39-13Z` nunca existió. Decisión: almacenamiento local
  reproducible por defecto (`S3_USE_LOCAL=1`, volumen `servator-data`) + servicio
  opcional `s3mock` (perfil `s3`, imagen verificada `adobe/s3mock:5.2.3`) para API S3
  real local; variables `S3_*` conservadas para un endpoint existente.
- Contextos de build: todos los Dockerfiles usan rutas relativas a la raíz del repo
  (`backend/`, `engine/`, `worker/`, `frontend/`), por lo que **todos los servicios
  compilan con `context: .`** (el fallo inicial `COPY backend/: not found` fue por
  contextos `./backend`/`./frontend`).
- Healthcheck de MinIO (`mc --version`) eliminado: el binario `mc` no existe en la
  imagen del servidor. `s3mock` no lleva healthcheck; `init`/`backend` no dependen de
  él y el entrypoint omite el bucket con `S3_USE_LOCAL=1`.
- Migraciones: `backend/migrations/` ahora contiene env Alembic real + migración
  inicial `c9c5fea87e18` (15 tablas, `db upgrade` verificado en sqlite desde cero).
- Dependencia `python-magic-bin` eliminada: sin rueda Linux y sin uso en el código.
- Techo torch en `2.14.0`/`0.29.0`: el metadata publicado de kraken 7.1.1 exige
  `torch<=2.14,>=2.9.0` y en PEP 440 `2.14.1 > 2.14` (pip falla ResolutionImpossible).
  `torch==2.14.0`/`torchvision==0.29.0` verificados en índices cpu, cu126 y cu130.
- `wait_db` del entrypoint normaliza la URL antes de psycopg2: SQLAlchemy usa
  `postgresql+psycopg2://…` y libpq exige `postgresql://…` (fallaba con
  `invalid dsn: missing "="`).
- El `command` de `init` es `["init-only"]` (sin repetir el entrypoint, que ya es
  `ENTRYPOINT`); y el entrypoint nunca hace `shift` antes de `exec "$@"`
  (el `shift` eliminaba `gunicorn`/`python` → exit 127 y backend en Restarting).
- Permisos: `backend`/`dispatcher` corren como uid 10001 (`user:` en compose;
  worker ya lo trae en su Dockerfile) e `init` (root) hace
  `chown -R 10001:10001 /models /data` en cada arranque. Sin esto, los
  directorios creados por root (`/data/objects/...`, `/models/*.part`)
  bloqueaban al worker (`PermissionError`, jobs FAILED).
- RQ 1.x exige `Retry(max, interval)`: pasar tupla `(1, [30])` a `enqueue`
  rompe con `'tuple' object has no attribute 'max'` (job queda PENDING y lo
  rescata el dispatcher; corregido a `Retry` real).
- Adaptador reescrito a la API real de kraken 7.1 (`kraken.tasks.*`), no a
  `kraken.lib.models.load_any`/`kraken.rpred` (inexistente para PP-OCRv6).
- Healthcheck de frontend contra `127.0.0.1` (no `localhost`): evita flapping
  por resolución IPv6 dentro de `nginx:alpine`.
- Healthcheck del dispatcher: la imagen `python:3.11-slim` no trae `ps`; se
  agregó `procps` al `apt-get` de `backend/Dockerfile`.
