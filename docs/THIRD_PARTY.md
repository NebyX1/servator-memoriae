# Terceros (THIRD_PARTY)

| Paquete / dato | Versión / fuente | Licencia | Uso |
|---|---|---|---|
| kraken | 7.1.1 | Ver upstream (Apache-2.0 histórica) | Segmentación baseline + recognizer + `ketos train` |
| torch / torchvision | 2.14.0 / 0.29.0 (cu130) | BSD-3 | Backend ML del worker |
| PP-OCRv6 medium | Zenodo 21788410, `medium.safetensors` 63.8 MB, DOI 10.5281/zenodo.21788410 | Apache-2.0 | Pesos reconocedor base |
| pypdfium2 | requirements backend | Apache-2.0 | Split PDF (render scale 2) + PDF facsímil |
| Pillow | requirements backend | HPND | Split TIFF, normalización PNG, thumbs, smoke test |
| reportlab | requirements backend | BSD | PDF lectura (fuente DejaVu/serif con ñ/tildes) |
| Flask / SQLAlchemy / Flask-Login / Flask-WTF / Flask-Migrate / Flask-Limiter / Flask-CORS | requirements backend | Varias (MIT/BSD) | API, sesiones, CSRF, migraciones, límites |
| argon2-cffi | requirements backend | MIT | Hash de contraseñas |
| DejaVuSans | sistema (`/usr/share/fonts`) o Arial en Windows | Bitstream Vera / propietaria | Fuente incrustada PDF |

Los pesos del modelo no se versionan en git; se descargan a `MODEL_DIR` y se registran en `manifest.json`. Al redistribuir pesos, conservar DOI y aviso Apache-2.0.
