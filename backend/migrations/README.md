# Migraciones iniciales

Este directorio (`backend/migrations/`) contendrá las migraciones Alembic/Flask-Migrate.

## Estado
Vacías al inicio: ejecutar `flask --app "app:create_app()" db init` (si no existe) y luego `db migrate -m "init"` + `db upgrade`.

## Reglas
- Nunca editar una migración ya aplicada en otro entorno; crear una nueva.
- `db upgrade` es idempotente y es el paso de release (Docker/Coolify) antes de levantar la API.
- Verificar con `db heads` y `db history` ante una migración interrumpida.
