# AGENTS.md — Servator Memoriae (Memoria Histórica)

## Configura y levanta nuestro proyecto

Si sos un agente (o humano) y tenés que poner el proyecto de pie:

1. **Inspeccionar primero el equipo y leer** `INSTRUCCIONES_AGENTE.md`: sistema, arquitectura, CPU, RAM, disco, Docker, GPU, controlador y acceso real a GPU desde Docker. No supongas que tiene el hardware de otra instalación. Leer además `docs/deployment/*` (arquitectura, variables, GPU), `.env.example`
   y `scripts/diagnose.py --help`. No adivines rutas del backend: las reales son
   `backend/app/__init__.py::create_app`, `backend/app/routes/*` y
   `backend/app/tasks.py::execute_job`.
2. **Ejecutar bootstrap** (idempotente, conserva `.env`, nunca `down -v`):
   - Linux/macOS: `bash scripts/bootstrap.sh --device auto` (`cpu` o `cuda` para forzar).
   - Windows: `.\scripts\bootstrap.ps1 -Device auto`.
   - El perfil queda persistido en `.device` y `DEVICE_MODE` en `.env`.
   - Sin NVIDIA Toolkit el stack CPU debe arrancar igual (ver `docker-compose.gpu.yml`).
3. **Resolver**: si algo falla, reintentá el bootstrap (es idempotente), revisá
   `docker compose ps`, `docker compose logs backend worker dispatcher init`,
   y `python scripts/diagnose.py`. No borres volúmenes (`down -v` prohibido);
   backup con `python scripts/backup.py`, restore con `python scripts/restore.py --src <dir>`.
4. **Verificar salud + inferencia**:
   - `curl http://localhost:8787/health` y `/ready` (vía frontend same-origin `/api/v1`).
   - El job `prepare_model` descarga el lector una sola vez; `diagnose.py` reporta
     `inference.smoke`. GPU: `nvidia-smi` + `torch.cuda.is_available()`.
5. **Devolver**: URL final, modo (`cpu`/`cuda` según `.device`), resultado de
   salud e inferencia. **Conservar informe local** en `.agent-report.json`
   (`python scripts/diagnose.py --json > .agent-report.json`).

## Reglas del repo

- Código real, sin placeholders. `SECRET_KEY`, `ADMIN_PASSWORD` y credenciales
  solo por entorno/`.env` (nunca commitear).
- `client_max_body_size 550m` / `MAX_UPLOAD_MB=512` son el contrato de subidas.
- GPU solo vía `docker-compose.gpu.yml` (`worker-gpu` + `train-worker`, `count: 1`, torch cu130).
- PaddleOCR-VL usa `paddle` en la red interna y `worker-setup` para su preparación; los pesos permanecen en `model-cache`. El override GPU reserva un dispositivo NVIDIA para el servicio. No anunciarlo como preparado sin una inferencia real; consultar `docs/MODELS.md` y el campo `paddle` de `scripts/diagnose.py`.
