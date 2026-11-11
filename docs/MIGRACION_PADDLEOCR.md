# Migración del segundo lector

La instalación sustituye el servicio exclusivo de Qwen3-VL por PaddleOCR-VL-1.6. El servicio retirado, su adaptador y su descargador ya no forman parte del arranque. Las preferencias antiguas de ese motor y del análisis doble anterior migran automáticamente a Kraken; el dispositivo y las demás opciones se conservan. Los resultados, revisiones y trabajos antiguos se conservan con su procedencia original; un trabajo antiguo no puede reiniciarse con otro motor por accidente. En la interfaz se presentan como «lectura histórica».

En la migración de esta computadora se identificaron y eliminaron el contenedor dedicado, sus imágenes sin otros consumidores y los dos pesos exclusivos (modelo GGUF y proyector visual, 3.333.461.920 bytes en total), además de su manifiesto y prueba local. No se eliminó ningún volumen: el caché contiene también Kraken y el volumen de datos contiene el archivo. Se revisaron las ubicaciones de Hugging Face y Ollama accesibles; una instalación de otro modelo de la familia Qwen en Ollama se dejó intacta al no poder atribuirla a este proyecto. No se ejecutó ninguna limpieza global de Docker ni se alteró el VHDX. El espacio físico liberado en Windows puede diferir del tamaño lógico eliminado.

Inventario de la eliminación efectivamente realizada:

- Contenedor `memoria-historica-qwen-1` (`36fc30989e32…`), dedicado al lector anterior.
- Imágenes sin consumidores `ghcr.io/ggml-org/llama.cpp:server` (`4d2de15a0ffb…`), `server-cuda12` (`a361e47e28e8…`) y `server-cuda13` (`4f27e30d776d…`).
- En la carpeta exclusiva `/models/qwen3-vl-4b`: `Qwen3VL-4B-Instruct-Q4_K_M.gguf` (2.497.281.664 bytes), `mmproj-Qwen3VL-4B-Instruct-F16.gguf` (836.180.256 bytes) y su manifiesto; además `/data/config/qwen-smoke.json`. La carpeta quedó vacía y se retiró.
- Se conservaron todos los volúmenes y los pesos de Kraken. El manifiesto de Ollama `~/.ollama/models/manifests/registry.ollama.ai/library/qwen3` corresponde a otra instalación no atribuida al proyecto y no se tocó. La caché general de construcción de Docker también se conservó porque puede contener capas compartidas.

Antes de la migración se guardó un respaldo lógico de PostgreSQL en `backups/20261111-032758/db.sql`; es una copia de la base, no de los archivos de imagen.

Después de actualizar, comprobá `docker compose -f docker-compose.yml -f docker-compose.gpu.yml ps`, `docker compose logs paddle worker-setup` y `python scripts/diagnose.py`. La primera selección de PaddleOCR-VL prepara y comprueba el modelo; los archivos permanecen en el volumen `model-cache` para siguientes arranques. Consultá [MODELS.md](MODELS.md) para las versiones, recursos y compatibilidad.

## Archivos de la integración

- Servicio y archivos oficiales: `paddle_service/Dockerfile`, `paddle_service/server.py`, `engine/paddle_assets.py` y `engine/paddle_asset_manifest.json`.
- Backend: `backend/app/services_paddle.py`, `services_comparison.py`, `services_device.py`, `services_gpu_lock.py`, `services_ocr.py`, `services_queue.py`, `tasks.py` y las rutas `routes/settings.py`, `routes/jobs.py` y `routes/documents.py`.
- Interfaz: `frontend/src/features/settings/Settings.tsx`, `digitize/Wizard.tsx` y `documents/OcrReview.tsx`, junto con los ensayos de navegador de `frontend/e2e/`.
- Infraestructura y diagnóstico: `docker-compose.yml`, `docker-compose.gpu.yml`, `scripts/bootstrap.ps1`, `scripts/bootstrap.sh`, `scripts/diagnose.py`, `scripts/restore.py` y `AGENTS.md`.
- Pruebas: `tests/test_dual_ocr.py`, `tests/test_paddle_failures.py`, `tests/real_paddle_workflow.py` y `tests/real_cpu_stack.py`.
- Documentación: `README.md`, `docs/API.md`, `docs/ARCHITECTURE.md`, `docs/JSON_FORMAT.md`, `docs/MODELS.md`, `docs/USER_GUIDE.md`, `docs/TROUBLESHOOTING.md`, `docs/VALIDATION_STATUS.md` y las guías de `docs/deployment/`.
- Código retirado: `backend/app/services_qwen.py`, `engine/qwen_assets.py` y `engine/qwen-models.ini`. Las menciones restantes en pruebas y documentación histórica sirven para comprobar y explicar la migración; no inician el motor anterior.
