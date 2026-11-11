# Estado de validación

## PaddleOCR-VL-1.6 y análisis doble — 2026-11-11

En Windows/Docker con RTX 3050 (8 GB) y torch cu130, la canalización oficial `PaddleOCRVL` con backend Transformers procesó un manuscrito real y devolvió nueve bloques. Una prueba aislada con SQLite y colas Redis reales procesó el mismo manuscrito con Kraken en CPU y PaddleOCR-VL en GPU: ambos resultados se conservaron y se identificaron 66 diferencias, sin elegir una lectura automáticamente. Se confirmó una transcripción y se generaron JSON, PDF de lectura, PDF facsímil y Word. La misma prueba procesó dos páginas en una colección y verificó el orden en el JSON exportado. La imagen original y la base del usuario solo se leyeron. En una imagen de contenedor sin acceso a GPU, la prueba sintética de Paddle en CPU devolvió texto y explicó el cambio automático de dispositivo; también se comprobaron errores por imagen inválida y modelo ausente.

Se construyó e inició además un proyecto Compose CPU nuevo, con base, almacenamiento y cola aislados y sin iniciar el lector opcional. Kraken transcribió una copia temporal del manuscrito (31 renglones) y se generó su JSON. Una primera imagen sintética no produjo renglones; no se tomó como prueba satisfactoria de reconocimiento. La imagen definitiva de Paddle también se construyó con torch `2.14.0+cpu` y procesó una imagen sintética sin GPU y sin conexión de red, en 14,2 segundos en este equipo. Se retiraron los contenedores y archivos temporales del ensayo sin borrar volúmenes.

Estas pruebas comprueban ejecución y preservación, no exactitud. La comparación de interfaz usa respuestas controladas. La RTX 5060 Ti, un despliegue Coolify real y el entrenamiento de Kraken no se probaron; el entrenamiento sigue deshabilitado hasta contar con una validación real. Las secciones siguientes son históricas y no describen componentes activos.

## Qwen y doble lectura — 2026-11-11

En Windows/Docker se verificaron los hashes de Q4_K_M y el proyector F16 oficiales. Qwen transcribió una imagen sintética en CPU y en la RTX 3050; el log confirmó la carga de `mmproj` y la prueba GPU mostró uso de memoria. Una prueba aislada con SQLite y Redis ejecutó la lectura doble por la cola real, conservó ambos resultados, detectó diferencias, confirmó una propuesta y generó JSON, PDF de lectura, PDF facsímil y Word. También se procesó en modo de solo lectura una imagen existente del archivo, sin modificar el original ni sus revisiones. La prueba de interfaz de comparación usa respuestas controladas, por separado de la inferencia real. La batería Python final pasó 51 casos y omitió uno; las pruebas de navegador pasaron en modo local y autenticado. El respaldo SQL se restauró dos veces en PostgreSQL temporal y conservó los mismos conteos; la restauración de volúmenes reales no se ejecutó. Esto no mide exactitud de manuscritos ni sustituye una evaluación con referencias humanas. El entrenamiento sigue deshabilitado.

## Configuración de procesamiento — 2026-11-11

En este equipo se probó el selector de CPU/GPU y su persistencia; cada trabajo conserva el dispositivo resuelto al encolarse. La verificación integrada usó una base SQLite y colas Redis aisladas con una imagen sintética: la transcripción en CPU terminó con 5 renglones y la transcripción en GPU terminó con 4. En el contenedor GPU, `torch==2.14.0+cu130` informó CUDA 13.0 disponible sobre NVIDIA GeForce RTX 3050. Estas pruebas comprueban ejecución, no precisión en manuscritos ni compatibilidad con otros equipos. El entrenamiento personalizado sigue sin estar validado.

> La evidencia de esta tabla es histórica. Tras la revisión de noviembre de 2026, el inicio de nuevos entrenamientos quedó deshabilitado por falta de una evaluación válida; la activación de modelos no está validada. Las pruebas previas de inferencia no garantizan el funcionamiento de los cambios posteriores; volvé a ejecutar el diagnóstico y los ensayos del despliegue actual.

> Actualizado 2026-11-10 con stack Docker real. No se confunde prueba omitida con aprobada.

## Probado OK (evidencia)
| Fecha | Qué | Resultado |
|---|---|---|
| 2026-11-10 | `bootstrap.ps1 -Device cpu` idempotente (5 rebuilds por fallos reales, conserva `.env`/datos) | exit 0, URL http://localhost:8787, modo cpu |
| 2026-11-10 | `docker compose ps` (final, tras fix `procps`) | **6/6 healthy**: postgres, redis, backend, worker, dispatcher, frontend |
| 2026-11-10 | `init`: migración real `c9c5fea87e18` en Postgres | `Context impl PostgresqlImpl`, 15 tablas |
| 2026-11-10 | `prepare_model` en worker CPU | COMPLETED; `ModelVersion v1`, 63.779.644 bytes, md5 `e3411a45…` = API Zenodo |
| 2026-11-10 | `GET /ready` | `{"db":true,"reader":"ready"}` |
| 2026-11-10 | E2E HTTP (scripts en `%TEMP%\opencode\e2e_*.py`) | login+CSRF, colección, documento, upload PNG→1 pág, transcribe COMPLETED, 2 renglones kraken real (conf 0.96/0.99, texto exacto), patch revisión + 409 en versión vieja, exports JSON (4101 B, schema + full_text revisado), PDF lectura (1963 B) y facsímil (4944 B) |
| 2026-11-10 | PDF lectura: extracción pypdf | ó/—/“transcripción”/“Página” extraíbles (0 U+FFFD); confusión real documentada: kraken leyó “José”→“Jos” en bitmap PIL (corregible por revisión) |
| 2026-11-10 | `pytest tests/ -q` (host, sqlite) | **15 passed, 1 skipped** (skip honesto: smoke con modelo real) |
| 2026-11-10 | `npm run build` frontend | tsc + vite 5.4.21 OK |
| 2026-11-10 | `backup.py --db-only` | `backups/smoke/db.sql` 44 KB, 14 CREATE TABLE |
| 2026-11-10 | `docker compose config` CPU y CPU+GPU overlay | OK |

## Fallos reales encontrados y corregidos (todos con evidencia de build/log)
`minio/minio` inexistente en Hub → local+s3mock; contextos de build a raíz;
`python-magic-bin` sin rueda Linux → eliminado; techo torch `2.14.0` (kraken exige
`torch<=2.14`); DSN `+psycopg2` normalizada para psycopg2; `command: ["init-only"]`;
sin `shift` antes de `exec`; `Retry(max, interval)`; `dispatch.py` con `time` y
rutas por entorno; adaptador a `kraken.tasks.*`; servicios como uid 10001 +
`chown` en `init`; healthcheck a `127.0.0.1`. Detalle en `ARCHITECTURE_REFERENCE.md`.

## Pendiente / no ejecutado
- `MODEL=1 pytest tests/test_engine_smoke.py` (host sin torch; inferencia real probada en contenedor worker).
- `ketos train` real + activación/rollback por colección (implementado, no ejecutado: requiere GPU + tiempo).
- Perfil GPU `cu130`/Blackwell en contenedor (configuración preparada, sin toolkit verificado aquí).
- Restore desde backup con datos reales, carga contra Postgres, revisión visual de PDF facsímil buscable.
- Telemetría: no hay; instalación 100 % local.
