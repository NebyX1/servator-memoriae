# S3 local reproducible (opcional)

Por defecto la instalación local usa almacenamiento en filesystem (`S3_USE_LOCAL=1`):
cero pulls extra, datos en el volumen `servator-data`.

## Perfil `s3` (API S3 real local)

Imagen fijada y verificada en Docker Hub (2026-11-10): `adobe/s3mock:5.2.3`.

```powershell
docker compose --profile s3 up -d
# en .env:
S3_USE_LOCAL=0
S3_ENDPOINT=http://s3mock:9090
```

## Decisión documentada

`minio/minio` ya no existe en Docker Hub (pull: "repository does not exist",
verificado 2026-11-10; `quay.io/minio/minio` exige auth anónima no disponible
desde este entorno) y el tag `RELEASE.2024-12-18T16-39-13Z` nunca existió.
Por eso el servicio MinIO se reemplazó por filesystem local + s3mock opcional.
Ver `docs/ARCHITECTURE_REFERENCE.md`.
