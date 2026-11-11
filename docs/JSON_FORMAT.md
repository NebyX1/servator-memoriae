# Formato JSON de exportación

El esquema actual `servator-memoriae/1` conserva los identificadores, metadatos y renglones anteriores. `full_text` refleja el texto exportado; por defecto usa la revisión humana cuando existe. Las coordenadas de Kraken y los bloques de Paddle corresponden a la imagen procesada; la rotación aplicada se registra en `preprocessing`.

```json
{
  "schema": "servator-memoriae/1",
  "id": "documento-1",
  "title": "Acta",
  "collection_id": null,
  "metadata": {"type": "libro", "years": [1883, 1883], "signature": "", "description": "", "tags": []},
  "pages": [{
    "id": "pagina-1", "order": 0, "folio": "1r", "width": 1200, "height": 1800, "status": "needs_review",
    "lines": [],
    "ocr": {
      "ocr_mode": "dual",
      "review_status": "pending",
      "selected_transcription": null,
      "review": null,
      "engines": [
        {"name": "kraken", "model_version": "v1", "device": "cpu", "status": "completed", "text": "...", "lines": []},
        {"name": "paddleocr_vl", "model_version": "revision-hugging-face", "device": "cuda", "status": "completed", "text": "...", "blocks": [], "elapsed_seconds": 12.3}
      ]
    }
  }],
  "full_text": "",
  "meta": {"mixed": false, "text_source": "revised_fallback_auto"}
}
```

`ocr` es `null` en páginas anteriores sin resultados multimodales. Los motores conservan su estado, error, dispositivo, versión, texto y geometría cuando existe. Una revisión incluye autor, versión, origen, fecha y trabajo de procedencia. Los valores `review_status` son `pending`, `automatic`, `confirmed` o `previous_line_review` cuando se conserva una revisión de renglones anterior. En doble lectura pendiente no se selecciona ni exporta automáticamente ninguna de las dos propuestas nuevas como definitiva.
