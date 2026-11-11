# Modelos

## Fuentes
| Pieza | Fuente | Detalle |
|---|---|---|
| Reconocedor | Zenodo 21788410 | `medium.safetensors` 63.779.644 bytes, md5 `e3411a453ce3b9e9efae3f8631d85762` (API Zenodo, verificado en contenedor), DOI `10.5281/zenodo.21788410`, URL `https://zenodo.org/records/21788410/files/medium.safetensors?download=1` |
| Segmentador | kraken 7.1.1 | `blla.mlmodel` empaquetado en el wheel (`kraken.tasks.SegmentationTaskModel`), sin descarga |
| Entrenamiento | Deshabilitado | La preparación de ejemplos existe; el entrenamiento y su evaluación no están validados de extremo a extremo. |
| Segundo lector | [PaddleOCR-VL-1.6](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6) | 0.9B, revisión `132c45f52c0a26ed5a6b2f6bd8e3985794cc27dd`; estructura: `PP-DocLayoutV3`, revisión `e4f489dc536556fc1be02b973ba06756e0d4a2ac`. |

## Licencias
- Pesos `medium.safetensors`: **Apache-2.0** (según registro Zenodo). Conservar aviso y DOI al redistribuir.
- Código kraken: revisar licencia upstream antes de distribuir contenedores con pesos incluidos.

## Caché
- `MODEL_DIR` (default `./data/models`): pesos `ppocrv6-medium-<version>.safetensors` + `manifest.json` (`engine/model_manifest_template.json` como plantilla).
- `MODEL_CACHE_DIR` (`./data/models/cache`): caché HF/torch. Ambos deben ser escribibles por el worker (uid 10001; `init` hace `chown` en cada arranque).
- `manifest.json` por entrada: name, version, file, sha256, size, source, doi, license, engine, segmenter, preprocessing (height 64, normalización default kraken, codec embebido).
- Carga del reconocedor: `kraken.tasks.RecognitionTaskModel.load_model()` (nuevo plugin `kraken.loaders:safetensors`; el legacy `kraken.lib.models.load_any` solo entiende VGSL y falla con PP-OCRv6). Equivale al CLI oficial `kraken -i p.png o.txt segment -bl ocr -m medium.safetensors` (verificado en contenedor CPU).

## Activación
`ModelVersion`: `is_active_global` o `active_for_collection`. Solo rol con `activate_model`. La activación no borra versiones previas; el historial y métricas (CER) quedan en `TrainingRun.metrics` y `ModelVersion.metrics`. Verificar `GET /ready` (`reader: ready` si hay `.safetensors` en `MODEL_DIR`).

## PaddleOCR-VL 1.6 y análisis doble

Se usa la canalización oficial `PaddleOCRVL(pipeline_version="v1.6", engine="transformers")`, aislada en el servicio interno `paddle`: PaddleOCR 3.7.0, PaddleX 3.7.2 y Transformers 5.22.2, sobre torch 2.14.0 (cu130 en GPU). El backend Transformers es una opción de inferencia documentada por PaddleOCR. Los archivos del reconocedor y del detector de estructura ocupan aproximadamente 2,1 GB; se descargan una sola vez en `MODEL_DIR/paddleocr-vl-1.6`, con revisiones y hashes fijados. Para la primera descarga se necesitan unos 4,3 GB libres adicionales durante el ensamblado. La descarga se reanuda; la inferencia posterior no requiere internet.

`worker-setup` descarga y realiza una lectura real antes de anunciar el modelo como preparado. El servicio conserva una instancia en memoria y serializa las inferencias. En análisis doble Kraken usa CPU y después Paddle el dispositivo automático; Redis coordina el acceso a GPU. Si GPU no es compatible o falla, se informa el uso de CPU, que puede tardar mucho y consumir varios GB de RAM. Se recomienda 8 GB de VRAM disponibles para la RTX 3050 y más de 8 GB de RAM del sistema; las necesidades dependen del tamaño de página y del resto de aplicaciones.

Paddle detecta regiones con PP-DocLayoutV3 y conserva sus etiquetas, coordenadas y orden cuando el modelo los devuelve. La orientación y la corrección de deformación automáticas están desactivadas; se registra la rotación explícita de la página. Los resultados permanecen separados y la revisión final es humana. Los avisos sobre fechas, cifras y posibles nombres son heurísticos y no miden precisión. No hay garantía de que una lectura sea más correcta: evaluá con transcripciones de referencia.

La RTX 3050 se probó en este entorno; no se probó una RTX 5060 Ti. El worker usa torch cu130 para admitir arquitecturas recientes, pero la compatibilidad depende también del controlador y Docker. Consultá la [documentación de PaddleOCR para NVIDIA Blackwell](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/PaddleOCR-VL-NVIDIA-Blackwell.html) y ejecutá la comprobación real en el equipo de destino.
