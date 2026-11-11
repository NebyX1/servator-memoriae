# API v1 (`/api/v1`)

Sesión por cookie. CSRF para SPA same-origin: `GET /api/v1/auth/csrf`. Errores: `{"error": "...", "request_id": "..."}`. Códigos usados: 401 no autenticado, 403 sin permiso / registro inicial ya usado, 404, 409 (concurrencia / exportación no lista), 413 (>512 MB), 422 (validación), 500.

## Auth
- `GET /auth/me` → `{user | null}` (público).
- `POST /auth/login` `{email, password}` (rate-limit 10/min; anti-enumeración) → `{user}`.
- `POST /auth/logout` (login) → `{ok}`.
- `POST /auth/register_first` `{email, password ≥12}` — solo si no hay usuarios; 403 si ya existe.

## Colecciones y documentos (login; escritura requiere capability `upload`)
- `GET /collections?q=` → `{items: [{id, title, description}]}`.
- `POST /collections` `{title ≤512, description}` → 201 `{id, title}`.
- `GET /documents?q=&collection_id=` → `{items: [{id, title, collection_id, doc_type, year_start, year_end, signature, pages}]}`.
- `POST /documents` `{title, collection_id, doc_type, year_start, year_end, signature, description, tags[≤20]}` → 201 `{id}`.
- `GET /documents/<id>` → ficha + `pages[{id, order, folio, status, width, height}]`.
- `POST /documents/<id>/upload` multipart `files`/`file` → `{added[{file, pages, source_id}], duplicates[{file, source_id}], errors[{file, error}]}`. Orden natural de nombres; dedupe por sha256; expande PDF (`pypdfium2`, scale 2) y TIFF (frames PIL) hasta 500 páginas; valida imagen real; normaliza a PNG + thumb 320 px (respeta EXIF).
- `PATCH /documents/<id>/pages/order` `{order: [page_ids]}` (upload).
- `PATCH /pages/<id>` `{folio ≤64, rotation, crop}` (review).
- `GET /pages/<id>/lines` → `{items: [{id, order, baseline, polygon, auto_text, revised_text, confidence, state, note, version}]}`.
- `GET /pages/<id>/ocr` → propuestas independientes, comparación y última revisión, o `{available: false}`. `POST /pages/<id>/ocr/review` con `{job_id, text, source, version}` guarda una nueva revisión humana; devuelve 409 ante cambios concurrentes.
- `PATCH /lines/<id>` `{revised_text, state, note ≤2000, version}` (review) → `{ok, version}`; 409 si `version` difiere.
- `GET /pages/<id>/image` → PNG (miniatura o página).

## Jobs / modelos / exports / training
- `GET /settings/processing` devuelve `ocr_mode`, preferencia Kraken, disponibilidad real de workers y `paddle` con estado, versión, hardware, dispositivo y preparación. `PUT /settings/processing` acepta `{ocr_mode: kraken|paddleocr_vl|dual}` o `{device: auto|cpu|cuda}`; el dispositivo solo se cambia en modo Kraken. La primera selección de PaddleOCR-VL encola `prepare_paddle`.
- `GET /jobs/<id>`, eventos SSE/stream según `routes/jobs.py`.
- Modelos (`models_ep.py`): listar versiones, descargar/activar (capability `activate_model`).
- `POST /exports` `{document_id, collection_id, format: json|pdf-facsimil|pdf-lectura|docx|zip, text_source, include_originals, idempotency_key}` (export) → 201 `{job_id}`. Un documento en `docx` se descarga como Word editable; una colección se descarga como ZIP con un Word por documento.
- `GET /exports/<job_id>/download` → archivo si `COMPLETED`, si no 409.
- `GET /training/examples` resume correcciones disponibles. La creación y el inicio de entrenamientos devuelven 503: aún no están validados. `GET /training/runs` y `GET /training/runs/<id>` conservan el historial.

## Capacidades por rol
viewer: read · reviewer: +review · analyst: +upload/transcribe/export · admin/superadmin: +train/activate_model/admin.
