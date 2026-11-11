# Compatibilidad

## Entornos
| SO | Python | CPU | GPU |
|---|---|---|---|
| Linux x86_64 | 3.11 | Perfil CPU | Perfil NVIDIA con torch cu130, sujeto a controlador y toolkit |
| Windows / Docker Desktop con WSL2 | 3.11 en contenedor | Perfil CPU | Perfil NVIDIA si Docker accede a una GPU compatible |

`DEVICE_MODE`: `auto` (prueba CUDA, si no CPU), `cpu`, `cuda`. La API nunca carga el modelo; solo el worker (`transcribe_image` carga perezosa con `device` explícito).

## Blackwell: cu130 vs cu126
- Las ruedas `torch==2.14.0` / `torchvision==0.29.0` usadas aquí son build **cu130** (CUDA 13.0), que cubre Blackwell (SM 100/120) con driver reciente (R580+).
- `cu126` (CUDA 12.6) **no** garantiza Blackwell: en esa serie puede no haber kernels/SM adecuados y PyTorch puede caer a CPU o fallar al inicializar CUDA. En ese caso instalar la variante cu130 o usar `DEVICE_MODE=cpu`.
- Regla: en Blackwell, usar cu130 + driver vigente. No se promete soporte de GPUs antiguas (Kepler/Maxwell parciales o anteriores): pueden funcionar en CPU, pero CUDA no está garantizada.

## Notas
- `kraken==7.1.1` requiere las versiones de torch indicadas; no mezclar con torch cu12x si se quiere GPU Blackwell.
- La transcripción en CPU puede ser considerablemente más lenta. El entrenamiento de Kraken está deshabilitado hasta validarse de extremo a extremo.
- La RTX 3050 se probó en Windows/Docker; la RTX 5060 Ti y Apple Silicon no se probaron. Verificá el hardware, la memoria y una inferencia real en cada equipo antes de anunciar compatibilidad.
