# Configurar y levantar Servator Memoriae en otra computadora

Esta guía es para Codex, OpenCode u otro agente. Si el usuario pide **«configurá y levantá el proyecto»**, seguí estos pasos en orden desde la raíz del repositorio. Leé también `AGENTS.md`, `.env.example` y `docs/deployment/`.

## 1. Primero: inspeccionar el equipo

**No asumas que la computadora tiene la misma GPU o versión de CUDA que otra instalación.** Antes de instalar, construir o cambiar la configuración, identificá:

1. Sistema operativo y arquitectura (x86_64/AMD64 o ARM), CPU, RAM y espacio libre; en Docker Desktop comprobá también la memoria asignada a Docker.
2. Docker en ejecución y `docker compose version`. Revisá que el puerto configurado —8787 por defecto— esté libre o corresponda a esta instalación.
3. GPU NVIDIA, modelo, VRAM y controlador con `nvidia-smi` y `nvidia-smi -L`, si existen. Una GPU AMD, Intel o Apple no habilita el perfil NVIDIA de este proyecto.
4. Que Docker pueda usar realmente la GPU: en Linux comprobá NVIDIA Container Toolkit; en Windows, Docker Desktop con WSL2. No concluyas que CUDA funciona solo porque `nvidia-smi` funciona en el host.
5. Estado previo de `.env`, `.device`, servicios y volúmenes. Conservá los datos y las opciones del usuario.

Ejemplos de consulta, sin instalar nada:

```powershell
# Windows PowerShell
Get-CimInstance Win32_OperatingSystem | Select-Object Caption, OSArchitecture, TotalVisibleMemorySize, FreePhysicalMemory
Get-CimInstance Win32_Processor | Select-Object Name, NumberOfLogicalProcessors
Get-PSDrive -PSProvider FileSystem | Select-Object Name, Free
docker version
docker compose version
docker info
nvidia-smi
nvidia-smi -L
python scripts/diagnose.py --help
```

```bash
# Linux/macOS; algunos comandos pueden no estar disponibles
uname -a
uname -m
getconf _NPROCESSORS_ONLN
df -h .
docker version
docker compose version
docker info
nvidia-smi       # si hay NVIDIA y está instalado
nvidia-smi -L
python3 scripts/diagnose.py --help
```

En Linux consultá también `free -h`; en macOS, `sysctl hw.memsize`. Si falta NVIDIA, seguí por CPU. La versión máxima de CUDA que anuncia el controlador **no es** el runtime dentro del contenedor: el perfil GPU usa PyTorch `cu130`. Comprobá controlador, arquitectura y acceso desde Docker. La RTX 3050 se probó; la RTX 5060 Ti y Apple Silicon no se probaron en esta instalación. No prometas compatibilidad sin una prueba real.

La primera instalación necesita Git, internet y espacio para imágenes Docker y modelos. Python 3 en el host permite ejecutar diagnóstico y respaldos; no hace falta instalar torch en el host. PaddleOCR-VL y su detector ocupan unos 2,1 GB persistentes y necesitan alrededor de 4,3 GB libres durante la descarga y el ensamblado; imágenes y documentos requieren espacio adicional. Paddle en CPU puede ser lento y consumir varios GB de RAM. Si faltan recursos, informalo y mantené disponible Kraken cuando sea posible.

## 2. Preparar y arrancar

Instalá Docker Desktop o Docker Engine con Compose si faltan, siguiendo las instrucciones oficiales del sistema y sin cambiar CUDA del host por suposición. Después ejecutá:

```powershell
# Windows, desde la raíz
.\scripts\bootstrap.ps1 -Device auto
```

```bash
# Linux/macOS, desde la raíz
bash scripts/bootstrap.sh --device auto
```

`auto` intenta detectar NVIDIA y el acceso desde Docker; si no puede comprobarlos, usa CPU. Se puede solicitar `cpu` o `cuda` cuando corresponda. El perfil queda en `.device` y `DEVICE_MODE` en `.env`. CPU no necesita NVIDIA; GPU agrega `docker-compose.gpu.yml`. Si GPU falla por compatibilidad, informá el error y reintentá con CPU, sin borrar datos.

El bootstrap crea `.env` desde `.env.example` si no existe, genera `SECRET_KEY` y conserva un `.env` existente. No sobrescribas opciones o credenciales del usuario; nunca publiques `.env`, `.agent-report.json`, bases, documentos, respaldos ni pesos. La instalación nueva usa **modo de prueba local sin login** (`LOCAL_TEST_MODE=1`, `FLASK_ENV=development`, `FRONT_BIND=127.0.0.1`). No lo expongas a la red ni mediante un proxy. Para acceso remoto o Coolify seguí `docs/deployment/COOLIFY.md` y configurá autenticación y secretos propios.

Kraken es el lector predeterminado. PaddleOCR-VL-1.6 es opcional: al seleccionarlo en Configuración, `worker-setup` descarga los archivos una vez y realiza una lectura de prueba. El análisis doble conserva ambas propuestas. Si la construcción de Paddle falla, el bootstrap intenta iniciar los servicios principales para mantener Kraken disponible.

## 3. Comprobar y resolver

Abrí `http://localhost:8787` o el puerto configurado. Comprobá los servicios y su funcionamiento real:

```bash
docker compose ps
docker compose logs --tail 100 backend worker worker-setup dispatcher paddle
```

Para consultar servicios GPU agregá `-f docker-compose.yml -f docker-compose.gpu.yml`. Comprobá `/health` y `/ready`: el segundo debe informar base disponible y lector listo; la primera descarga puede estar en curso. Ejecutá `python scripts/diagnose.py --json --out .agent-report.json` (o `python3` en Linux/macOS). Verificá `inference.smoke` para Kraken. Para GPU comprobá `gpu_worker.cuda_available` y el dispositivo desde el contenedor. Si se prepara Paddle, comprobá `paddle.ready`, el dispositivo efectivo y una lectura real; que el servicio responda no prueba por sí solo que el modelo funcione.

Si algo falla, revisá logs, espacio, memoria, red y perfil; corregí la causa y reintentá el bootstrap. No simules avances ni declares GPU o inferencia disponibles sin evidencia. **Nunca ejecutes `docker compose down -v`, `docker system prune --volumes` ni borres volúmenes o directorios de usuario para resolver un fallo.** Para respaldos consultá `docs/deployment/BACKUP_RESTORE.md`.

Al terminar, informá la URL, el modo CPU/GPU realmente comprobado, el modelo de GPU si existe, el resultado de salud e inferencia y las limitaciones. El entrenamiento de Kraken sigue deshabilitado hasta estar validado; conservar correcciones no equivale a entrenar un modelo.
