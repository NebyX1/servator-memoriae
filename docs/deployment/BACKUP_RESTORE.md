# Respaldo y restauración

Respaldá la base de datos y los volúmenes de datos y modelos juntos. Las referencias de las páginas apuntan a archivos guardados en esos volúmenes; restaurar solamente la base puede dejar imágenes y exportaciones inaccesibles.

Para respaldar base, archivos y modelos de forma coherente, primero detené los componentes que pueden escribir. Mantené PostgreSQL y Redis activos:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml stop backend dispatcher worker worker-gpu worker-setup
python scripts/backup.py
python scripts/backup.py --help
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

El script resuelve los nombres reales de volúmenes de Compose, usa `pg_dump` para PostgreSQL y omite la copia física de Redis mientras está activo. Si usás `s3mock`, detenelo antes de respaldar su volumen. `--db-only` guarda solo la base y no sustituye el respaldo de archivos y modelos.

El script informa el directorio de salida. Para restaurar, detené primero backend, dispatcher y workers; detené también `paddle` si vas a reemplazar el volumen de modelos. PostgreSQL debe permanecer activo para importar `db.sql`; si el respaldo incluye una copia física de Redis, detené Redis antes de restaurarla:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml stop backend dispatcher worker worker-gpu worker-setup paddle
python scripts/restore.py --src <directorio-del-respaldo>
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

La restauración reemplaza datos. Los respaldos nuevos incluyen instrucciones para sustituir las tablas al importar; los volcados antiguos pueden requerir restauración en una base vacía. Revisá las opciones con `python scripts/restore.py --help` y probá el procedimiento en un entorno separado antes de usarlo con datos de producción. No uses `docker compose down -v` como paso de diagnóstico.
