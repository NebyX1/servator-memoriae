# PROGRESS — lista persistente de avances y pendientes

> Este registro es histórico. Para el estado actual de GPU, PaddleOCR-VL y pruebas consultá `docs/VALIDATION_STATUS.md`; para iniciar en otro equipo, `INSTRUCCIONES_AGENTE.md`. El entrenamiento continúa deshabilitado hasta su validación.

## Levantamiento real 2026-11-10 (stack Docker CPU, verificado)
- [x] `bootstrap.ps1 -Device cpu` → exit 0; 6/6 servicios sanos en http://localhost:8787 (modo cpu, `.device`).
- [x] Migración `c9c5fea87e18` aplicada en Postgres; `init` idempotente.
- [x] `prepare_model` COMPLETED en worker: PP-OCRv6 medium real (63.779.644 B, md5 = API Zenodo), `ModelVersion v1`; `/ready` → reader ready.
- [x] Transcripción kraken 7.1.1 real vía `kraken.tasks.*` (adaptador reescrito; ruta CLI oficial reproducida en contenedor con texto exacto).
- [x] E2E HTTP completo: login/CSRF → colección → documento → upload → transcribe → 2 renglones (0.96/0.99) → patch revisión + 409 → JSON + 2 PDF descargados y validados (pypdf extrae ó/—/tildes, 0 U+FFFD).
- [x] `pytest` 15 passed/1 skip; `npm run build` OK; `backup --db-only` OK (44 KB).
- [x] 11 fallos reales de integración encontrados por los logs y corregidos (ver `docs/ARCHITECTURE_REFERENCE.md` y `VALIDATION_STATUS.md`).
- [x] Admin inicial creado (`admin@local`, superadmin).

## Pendiente honesto
- [ ] Smoke host con modelo (`MODEL=1 ...`) — host sin torch; inferencia probada en worker.
- [ ] `ketos train` real + activación/rollback — implementado, sin GPU/tiempo para ejecutarlo.
- [ ] Perfil GPU cu130 en contenedor con NVIDIA Toolkit.
- [ ] Restore con datos reales; prueba de carga; revisión visual facsímil.
