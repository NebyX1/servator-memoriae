# Troubleshooting

| Síntoma | Causa probable | Acción |
|---|---|---|
| 401 No autenticado | Sesión vencida | Re-login; revisar cookie/CSRF (`/api/v1/auth/csrf`). |
| 403 Sin permiso | Rol sin capability | Admin debe subir rol (viewer→reviewer→analyst→admin). |
| 409 Otro editor guardó antes | Colisión de `version` en `PATCH /lines` | Recargar líneas y reintentar con `version` fresca. |
| 413 / Supera 512 MB | Límite `MAX_UPLOAD_MB` | Dividir TIFF/PDF en lotes <512 MB y <500 páginas. |
| PDF/TIFF con errores parciales | Archivo dañado o exceso de páginas | Leer `errors[]` del upload; re-exportar páginas sanas; lo bueno se conserva. |
| `reader: pending` en `/ready` | Sin `.safetensors` en `MODEL_DIR` | Ejecutar `ensure_model()` o copiar `ppocrv6-medium-v1.safetensors`; revisar `manifest.json`. |
| CUDA no disponible / cae a CPU | torch cu126 o driver viejo en Blackwell | Instalar torch cu130 + driver R580+, o `DEVICE_MODE=cpu`. |
| Entrenamiento | Función aún no validada | Las correcciones se conservan; el entrenamiento de modelos propios permanece deshabilitado. |
| PaddleOCR-VL no queda preparado | Descarga incompleta, falta de disco, incompatibilidad CUDA o prueba visual fallida | Ver el progreso y error en Configuración, `docker compose logs worker-setup paddle`, comprobar espacio y reintentar. Kraken sigue disponible. |
| DB vacía tras restore | Solo se restauró dump o solo `data/` | Restaurar ambos; claves `storage_key`/`image_key` deben existir en volumen. |
| Rate-limit login | >10 intentos/min | Esperar un minuto; verificar credenciales. |
