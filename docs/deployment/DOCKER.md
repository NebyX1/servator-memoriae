# Docker (despliegue)

El archivo real es `docker-compose.yml` en la raíz. Incluye PostgreSQL, Redis, inicialización de base, backend, worker, despachador y frontend. Los archivos y modelos persisten en volúmenes Docker separados; no uses `docker compose down -v` si querés conservarlos.

## Inicio

En Windows ejecutá `.\scripts\bootstrap.ps1 -Device auto`; en Linux/macOS, `bash scripts/bootstrap.sh --device auto`. También podés forzar `cpu` o `cuda`. Se conserva `.env` y se registra el dispositivo en `.device`. CUDA requiere una GPU NVIDIA, un driver compatible y acceso a GPU desde Docker; el perfil CPU no requiere NVIDIA. La construcción de GPU descarga imágenes y dependencias grandes.

En la aplicación, **Configuración** permite elegir Kraken, PaddleOCR-VL o análisis doble. La elección de CPU, GPU o Automático corresponde a Kraken; PaddleOCR-VL usa el dispositivo automático. La GPU solo se ofrece cuando el worker del override está conectado y ha comprobado CUDA. Si falta, ejecutá el bootstrap con `cuda` en el host y actualizá el estado. La preferencia se guarda en el volumen de datos; `.device` conserva el perfil del último bootstrap.

El servicio `paddle` usa la red interna y no publica puertos. `worker-setup` prepara el modelo sin bloquear la cola de Kraken. Los pesos del lector y detector persisten en `model-cache`; nunca elimines el volumen al actualizar. La imagen CUDA del lector requiere un controlador compatible; consultá los logs `docker compose logs paddle worker-setup` si la preparación falla.

El bootstrap construye primero los servicios principales. Si la construcción opcional de `paddle` falla, inicia Kraken igualmente y muestra un aviso; al resolver el problema ejecutá el bootstrap otra vez. En un despliegue manual con Compose, podés iniciar `postgres redis init backend worker worker-setup dispatcher frontend` para usar Kraken mientras se repara ese servicio.

Abrí `http://localhost:8787` (o el puerto `FRONT_PORT`). La configuración nueva de `.env.example` habilita el modo de prueba local sin login (`LOCAL_TEST_MODE=1`, `FLASK_ENV=development`, `FRONT_BIND=127.0.0.1`). Los documentos y cambios se conservan en los mismos volúmenes. El bootstrap no modifica un `.env` existente, por lo que una instalación previa debe actualizar estas tres variables si se desea este modo.

Para volver al acceso con cuentas, fijá `LOCAL_TEST_MODE=0` y `FLASK_ENV=production` y recreá el backend. Si necesitás crear la cuenta inicial, consultá el comando en el README. `LOCAL_TEST_MODE=1` no arranca con entorno de producción ni con `FRONT_BIND` distinto de `127.0.0.1`; no expongas este modo con un proxy externo.

`/health` comprueba el proceso y `/ready` informa la base y el estado del lector. El modelo puede tardar en descargarse durante el primer arranque. `python scripts/diagnose.py --json --out .agent-report.json` registra el diagnóstico del host: la inferencia de un modelo guardado en un volumen Docker debe comprobarse dentro del worker, no se deduce del estado de Python en el host.

## Configuración

Tomá `.env.example` como referencia. No publiques `.env`, `SECRET_KEY` ni contraseñas. Por defecto se utiliza almacenamiento local en el volumen `servator-data`, con modelos en `model-cache` (`/models`). El perfil `s3` es opcional. Para un S3 externo configurá `S3_USE_LOCAL=0` y las variables `S3_*` en todos los servicios.

El límite de archivo es 512 MB (`MAX_UPLOAD_MB=512`); el proxy debe admitir al menos `client_max_body_size 550m`. Para recuperación consultá [BACKUP_RESTORE.md](BACKUP_RESTORE.md). Las migraciones fallidas detienen el arranque: no marques manualmente una migración como aplicada sin verificar el esquema.

Para ejecutar el worker fuera de Docker instalá también `pip install -r backend/requirements-word.txt`; las imágenes de worker CPU y GPU ya incluyen esa dependencia para exportar a Word.
