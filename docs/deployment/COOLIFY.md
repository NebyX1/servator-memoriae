# Coolify

Conectá el repositorio como servicio Docker Compose y elegí `docker-compose.yml` en la raíz. Para GPU se necesita además `docker-compose.gpu.yml` y soporte NVIDIA en el host; validá el acceso desde el contenedor antes de usarlo en producción.

Incluí los servicios `paddle` y `worker-setup`, la red interna y el volumen persistente `model-cache`. No publiques el puerto 8080 del motor. La construcción de `paddle` utiliza el contexto adicional `service:worker` (o `service:worker-gpu` con el override); el constructor de Coolify debe admitir contextos de Compose. Si no aplica reservas NVIDIA del archivo adicional, desplegá CPU hasta tener acceso real y compatible a la GPU.

Para Coolify usá `FLASK_ENV=production` y `LOCAL_TEST_MODE=0`: el modo de prueba de `.env.example` es solo para esta computadora. Configurá `FRONT_BIND` para que el proxy de Coolify pueda acceder al frontend (por ejemplo `0.0.0.0` cuando corresponda). Definí `SECRET_KEY`, las credenciales de PostgreSQL y la URL de base coherente con ellas. No publiques `.env`. Conservá los volúmenes de PostgreSQL, datos y modelos entre despliegues. El servicio `init` aplica migraciones antes de iniciar el backend; investigá cualquier error de migración antes de continuar.

Exponé el frontend y configurá el proxy para aceptar al menos 550 MB. Comprobá `/health` y `/ready` y revisá `docs/VALIDATION_STATUS.md` para conocer los límites de la validación. Programá respaldos de la base y los volúmenes de datos/modelos según [BACKUP_RESTORE.md](BACKUP_RESTORE.md).
