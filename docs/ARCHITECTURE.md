# Arquitectura

```
frontend (SPA) → Flask API (backend/app) → Postgres + S3/MinIO-local + Redis/RQ
                                              ↓ jobs transcribe/export/train
                              worker → Kraken / PaddleOCR-VL (servicio aislado en red interna)
                              worker-setup → descarga y prueba visual de PaddleOCR-VL
```

## Componentes
- **API Flask** (`backend/app/__init__.py` factory, blueprints en `routes/`): `auth` (sesión, registro inicial de un solo uso, rate-limit login 10/min), `documents` (colecciones, documentos, subida con hash + expansión PDF/TIFF, páginas, renglones con 409 optimista), `jobs` (estado + eventos), `models_ep` (versiones, activación), `exports` (jobs de exportación), `training` (runs + snapshot + partición por página).
- **Modelos** (`models/__init__.py`): User (argon2, roles viewer/reviewer/analyst/admin/superadmin), Collection, Document, SourceFile (sha256, original inmutable), Page (order_index, folio, rotación, recorte), Line (baseline/polygon, auto/revised, confidence, state, version), TranscriptionVersion, Job/JobEvent (idempotencia `uq_job_idem`), ModelVersion, TrainingRun, Export, AuditLog.
- **Servicios**: `services_storage.py` (ObjectStorage: local o S3), `services_queue.py` (`new_job` + `dispatch` RQ), `services_export_pdf.py` (`build_pdf` facsímil/lectura), `utils_security.py` (capacidades por rol + `require`), `tasks.py` + `rq_callbacks.py` (ejecución worker).
- **Motores**: `engine/kraken_adapter.py` conserva Kraken; `engine/paddle_assets.py` verifica los archivos oficiales, `services_paddle.py` usa la canalización oficial aislada de `paddle_service/server.py` y `services_comparison.py` alinea las propuestas. `OcrResult` guarda cada motor y `OcrReview` cada confirmación humana. El entrenamiento está deshabilitado hasta validar su implementación de extremo a extremo.
- **Límites corregidos**: `MAX_CONTENT_LENGTH = MAX_UPLOAD_MB (512) * 1024 * 1024` (`config.py`, `__init__.py:16`), `MAX_PAGES_PER_FILE` (500), timeouts (descarga 120 s, train 8 h), streaming (lectura por bloques de 1 MB en `ensure_model`), modelos en directorio escribible `MODEL_DIR`/`MODEL_CACHE_DIR`.
- **Seguridad**: `ProxyFix`, CORS solo `/api/*`, `Cache-Control: no-store`, `X-Request-ID`, error handler JSON con request_id, `SECRET_KEY` ≥ 32 y `DEV_AUTH_BYPASS` prohibido en producción (fail-closed).
- **Salud**: `GET /health` (proceso), `GET /ready` (DB `SELECT 1` + reader ready si hay `.safetensors` en `MODEL_DIR`).
