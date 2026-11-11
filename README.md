# Servator Memoriae

Una herramienta local para organizar escaneos históricos, transcribirlos y revisar el texto junto a cada página. Permite agrupar documentos en colecciones, importar imágenes y PDF, y exportar los resultados en JSON, PDF o Word editable. El reconocimiento automático puede cometer errores: revisá las transcripciones antes de usarlas como fuente.

## Empezar

Necesitás Docker con Compose y espacio para imágenes, datos y el modelo. Desde la raíz del proyecto:

Si le pedís a un agente que configure el proyecto en otra computadora, indicále que lea primero [INSTRUCCIONES_AGENTE.md](INSTRUCCIONES_AGENTE.md): debe inspeccionar el sistema, la GPU y los recursos disponibles antes de elegir CPU o CUDA.

```powershell
# Windows
.\scripts\bootstrap.ps1 -Device auto
```

```bash
# Linux o macOS
bash scripts/bootstrap.sh --device auto
```

Abrí **http://localhost:8787**. La configuración inicial es de prueba local: entrás directamente, sin cuenta ni contraseña, y los cambios se guardan. El acceso se limita a esta computadora. El primer arranque puede demorar mientras se descargan las imágenes y el modelo. El script conserva `.env` y los volúmenes; el dispositivo elegido queda en `.device`. Podés forzar `cpu` o `cuda`. Consultá [Docker](docs/deployment/DOCKER.md) para los requisitos y [Coolify](docs/deployment/COOLIFY.md) para el despliegue.

### Usar cuentas fuera del modo de prueba

Para habilitar el acceso con cuentas, configurá `LOCAL_TEST_MODE=0` y `FLASK_ENV=production` en `.env` y recreá el servicio backend. Para publicar en otro equipo, seguí además las indicaciones de [Coolify](docs/deployment/COOLIFY.md). El modo de prueba no se habilita en producción ni cuando `FRONT_BIND` no es `127.0.0.1`.

Creá el primer usuario solo cuando necesites acceso autenticado:

Definí una contraseña privada en tu terminal y pasala al comando de creación, sin guardarla en el repositorio. En PowerShell:

```powershell
$env:ADMIN_PASSWORD = Read-Host 'Contraseña inicial'
docker compose exec -e ADMIN_PASSWORD backend flask --app wsgi create-admin
Remove-Item Env:ADMIN_PASSWORD
```

En Linux/macOS:

```bash
read -rs -p 'Contraseña inicial: ' ADMIN_PASSWORD; echo
export ADMIN_PASSWORD
docker compose exec -e ADMIN_PASSWORD backend flask --app wsgi create-admin
unset ADMIN_PASSWORD
```

El correo inicial predeterminado es `admin@local`; puede configurarse con `ADMIN_EMAIL` en el entorno del contenedor. Guardá la contraseña en un lugar seguro.

## Usar el archivo

1. En **Configuración → Motor de transcripción**, elegí Kraken, PaddleOCR-VL o Análisis doble. En Kraken podés elegir Automático, CPU o GPU NVIDIA; PaddleOCR-VL selecciona el dispositivo automáticamente. La primera preparación descarga aproximadamente 2,1 GB y comprueba una imagen real. Mientras tanto podés usar Kraken.
2. Creá un documento individual o una colección desde el asistente.
3. Agregá escaneos JPG, PNG, TIFF o PDF, uno a uno o en lote. Cada archivo admite hasta 512 MB.
4. Iniciá la transcripción y seguí el progreso. Revisá cada página y corregí los renglones necesarios.
5. Exportá el documento como JSON, PDF de lectura, PDF facsímil o Word editable (.docx).

[Guía de uso](docs/USER_GUIDE.md) · [Mejorar la lectura](docs/TRAINING_GUIDE.md) · [Respaldo y restauración](docs/deployment/BACKUP_RESTORE.md) · [Estado de validación](docs/VALIDATION_STATUS.md)

La preparación de ejemplos revisados está disponible, pero el entrenamiento y la evaluación de modelos propios todavía no están validados de extremo a extremo. La selección del lector no garantiza que sea el mejor para todas las caligrafías: medí resultados con documentos reales antes de adoptar un modelo para una colección.

## Diagnóstico

Consultá `http://localhost:8787/health` y `/ready`; la segunda ruta puede indicar que el lector aún se está preparando. Ejecutá `python scripts/diagnose.py --json --out .agent-report.json` para guardar un informe local. No borres volúmenes para solucionar problemas; revisá `docker compose ps` y los logs de `backend`, `worker`, `dispatcher` e `init`.
