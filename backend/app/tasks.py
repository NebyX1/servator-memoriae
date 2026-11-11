"""Worker tasks: transcribe, export, prepare_model, train. Idempotentes, por página, con checkpoints."""
import os, sys, json, io, hashlib, datetime, traceback
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "engine"))

def execute_job(job_id):
    from app import create_app
    app = create_app()
    with app.app_context():
        from app.extensions import db
        from app.models import Job
        job = Job.query.get(job_id)
        if not job or job.status in ("COMPLETED", "CANCELLED"):
            return
        # lock cooperativo simple
        job.status = "RUNNING"; job.phase = "iniciando"; db.session.commit()
        try:
            if job.kind == "transcribe":
                from app.services_gpu_lock import gpu_guard, paddle_guard
                from app.services_paddle import unload
                gpu = (job.payload or {}).get('device') == 'cuda'
                mode = (job.payload or {}).get('ocr_mode', 'kraken')
                if mode not in ('kraken', 'paddleocr_vl', 'dual') or (mode == 'dual' and not (job.payload or {}).get('paddle_revision')):
                    raise ValueError('Este trabajo usa un lector retirado. Sus resultados se conservan; iniciá una lectura nueva.')
                with gpu_guard(gpu):
                    if gpu and mode == 'kraken':
                        unload()
                    if mode != 'kraken':
                        with paddle_guard():
                            _transcribe(job)
                    else:
                        _transcribe(job)
            elif job.kind == "export":
                _export(job)
            elif job.kind == "prepare_model":
                _prepare(job)
            elif job.kind == "prepare_paddle":
                _prepare_paddle(job)
            elif job.kind == "train":
                _train(job)
            else:
                raise ValueError(f"kind desconocido {job.kind}")
            job = Job.query.get(job_id)
            if job.cancel_requested:
                job.status = "CANCELLED"
            else:
                job.status = "COMPLETED"; job.progress_done = job.progress_total
            db.session.commit()
        except Exception as e:
            traceback.print_exc()
            try:
                from app.services_queue import Cancelled
                job = Job.query.get(job_id)
                if isinstance(e, Cancelled):
                    job.status = "CANCELLED"
                    job.phase = "Cancelado"
                    job.error = ""
                else:
                    job.status = "FAILED"
                    job.error = str(e)[:2000] if isinstance(e, ValueError) else "Error interno. Revisá los registros con este ID."
                db.session.commit()
            except Exception:
                db.session.rollback()

def _ckpt(job, done, total=None, phase=None):
    from app.services_queue import progress
    progress(job.id, done, total, phase)

def _transcribe(job):
    if (job.payload or {}).get('ocr_mode', 'kraken') != 'kraken':
        return _transcribe_multimodal(job)
    from app.extensions import db
    from app.models import Page, Line, TranscriptionVersion, ModelVersion
    import kraken_adapter
    from app.config import settings
    from app.services_storage import ObjectStorage
    s = settings(); st = ObjectStorage(s)
    p = job.payload or {}
    page_ids = p.get("page_ids", [])
    model_version = p.get("model_version", "v1")
    device = p.get("device") or "auto"
    if device == "auto":
        device = s.DEVICE_MODE
    if device == "cuda":
        import torch
        if not torch.cuda.is_available():
            raise ValueError("La tarjeta NVIDIA no está disponible dentro del contenedor. Podemos continuar con el procesador (usá device=cpu).")
    # modelo activo global como fallback
    total = len(page_ids)
    failed_pages = []
    for i, pid in enumerate(page_ids):
        job2 = Job.query.get(job.id) if False else None
        from app.models import Job as J
        j = J.query.get(job.id)
        if j.cancel_requested:
            return
        _ckpt(job, i, total, f"Transcribiendo página {i+1} de {total}")
        page = Page.query.get(pid)
        if not page: continue
        # punto de recuperación por página: salta si ya tiene versión de este modelo
        existing = TranscriptionVersion.query.filter_by(page_id=pid, model_version=model_version).first()
        lines_done = Line.query.filter_by(page_id=pid).count()
        if existing and lines_done > 0 and not p.get("force"):
            continue
        page.status = "processing"; db.session.commit()
        img_path = st.get_path(page.image_key)
        try:
            recs = kraken_adapter.transcribe_image(img_path, version=model_version,
                device_mode="cpu" if device == "auto" and False else device)
        except FileNotFoundError:
            page.status = "failed"; db.session.commit()
            failed_pages.append(i + 1)
            from app.services_queue import emit
            emit(job.id, "page_error", {"page_id": pid, "error": "No se encontró el modelo o la imagen de esta página."})
            continue
        except Exception as e:
            page.status = "failed"; db.session.commit()
            failed_pages.append(i + 1)
            from app.services_queue import emit
            emit(job.id, "page_error", {"page_id": pid, "error": f"Esta página no se pudo abrir ({str(e)[:200]}). Las otras se conservaron."})
            continue
        # guarda versión + renglones (conserva revised_text existentes)
        old = {l.order_index: l for l in Line.query.filter_by(page_id=pid).all()}
        db.session.add(TranscriptionVersion(page_id=pid, version=(existing.version + 1 if existing else 1),
                                            engine=kraken_adapter.ENGINE_VERSION, model_version=model_version,
                                            payload={"lines": len(recs)}))
        if not recs:
            page.status = "needs_review"  # no declarar vacía sin evidencia
        else:
            page.status = "done"
        # limpia auto anteriores solo si no hay revisión humana
        if not any((l.revised_text is not None) for l in old.values()):
            Line.query.filter_by(page_id=pid).delete()
            old = {}
        for r in recs:
            l = old.get(r["order"])
            if l:
                l.auto_text = r["text"]; l.baseline = r["baseline"]; l.polygon = r["polygon"]
                l.confidence = r["confidence"]
            else:
                db.session.add(Line(page_id=pid, order_index=r["order"], baseline=r["baseline"],
                                    polygon=r["polygon"], auto_text=r["text"], confidence=r["confidence"], state="auto"))
        db.session.commit()
    if failed_pages:
        numbers = ", ".join(str(number) for number in failed_pages[:20])
        more = " y otras" if len(failed_pages) > 20 else ""
        raise ValueError(f"No se pudieron transcribir {len(failed_pages)} página(s): {numbers}{more}. Las demás páginas se conservaron; revisá los registros e intentá nuevamente.")
    _ckpt(job, total, total, "Revisión lista")


def _transcribe_multimodal(job):
    from app.extensions import db
    from app.models import Page, OcrResult, Job
    from app.services_storage import ObjectStorage
    from app.config import settings
    from app.services_comparison import compare_texts
    from app.services_queue import emit
    from app.services_paddle import transcribe_image
    import kraken_adapter
    payload = job.payload or {}
    mode, device = payload['ocr_mode'], payload['device']
    pages = payload.get('page_ids', [])
    storage = ObjectStorage(settings())
    partial_pages = []
    for index, page_id in enumerate(pages):
        if Job.query.get(job.id).cancel_requested:
            return
        page = Page.query.get(page_id)
        if not page:
            partial_pages.append(index + 1)
            continue
        _ckpt(job, index, len(pages), f'Preparando página {index + 1} de {len(pages)}')
        image_path = storage.get_path(page.image_key)
        engines = ['kraken', 'paddleocr_vl'] if mode == 'dual' else ['paddleocr_vl']
        for engine in engines:
            previous = OcrResult.query.filter_by(job_id=job.id, page_id=page_id, engine=engine).first()
            if previous and previous.status == 'completed':
                continue
            if previous:
                db.session.delete(previous)
                db.session.flush()
            actual_device = payload.get('kraken_device', 'cpu') if engine == 'kraken' else device
            version = payload.get('model_version', 'v1') if engine == 'kraken' else payload['paddle_revision']
            result = OcrResult(job_id=job.id, page_id=page_id, engine=engine,
                               model_version=version, device=actual_device, status='failed', details={})
            try:
                label = 'Kraken' if engine == 'kraken' else 'PaddleOCR-VL'
                _ckpt(job, index, len(pages), f'{label}: detectando regiones y leyendo página {index + 1} de {len(pages)}')
                if engine == 'kraken':
                    rotation = (page.rotation or 0) % 360
                    if rotation:
                        # Ambos motores deben leer la misma orientación, sin alterar el original.
                        import tempfile
                        from PIL import Image, ImageOps
                        with tempfile.TemporaryDirectory(prefix='servator-kraken-page-') as temp:
                            rotated_path = os.path.join(temp, 'page.png')
                            with Image.open(image_path) as original:
                                ImageOps.exif_transpose(original).convert('RGB').rotate(-rotation, expand=True).save(rotated_path)
                            lines = kraken_adapter.transcribe_image(rotated_path, version=version, device_mode=actual_device)
                    else:
                        lines = kraken_adapter.transcribe_image(image_path, version=version, device_mode=actual_device)
                    if not lines:
                        raise ValueError('Kraken no detectó renglones en esta página.')
                    result.text = '\n'.join(line['text'] for line in lines)
                    result.details = {'lines': lines, 'preprocessing': {'rotation': rotation}}
                else:
                    recognized = transcribe_image(image_path, device=actual_device, rotation=page.rotation or 0)
                    result.text = recognized['text']
                    result.device = recognized['device']
                    result.details = {'blocks': recognized.get('blocks', []),
                                      'elapsed_seconds': recognized.get('elapsed_seconds'),
                                      'preprocessing': recognized.get('preprocessing', {}),
                                      'pipeline_version': recognized.get('pipeline_version'),
                                      'backend': recognized.get('backend'),
                                      'fallback_reason': recognized.get('fallback_reason')}
                result.status = 'completed'
            except Exception as exc:
                from app.services_queue import Cancelled
                if isinstance(exc, Cancelled):
                    raise
                result.error = str(exc)[:1000] or 'No se pudo completar la lectura.'
                emit(job.id, 'page_error', {'page_id': page_id, 'engine': engine, 'error': result.error})
            db.session.add(result)
            db.session.commit()
        results = OcrResult.query.filter_by(job_id=job.id, page_id=page_id).all()
        if any(r.status != 'completed' for r in results) or len(results) != len(engines):
            partial_pages.append(index + 1)
        if mode == 'dual':
            _ckpt(job, index, len(pages), f'Comparando lecturas de la página {index + 1}')
            # La comparación se calcula al consultar; los textos persistidos son la fuente.
            if len(results) == 2 and all(r.status == 'completed' for r in results):
                by_engine = {r.engine: r.text for r in results}
                compare_texts(by_engine['kraken'], by_engine['paddleocr_vl'])
        page.status = 'needs_review' if any(r.status == 'completed' for r in results) else 'failed'
        db.session.commit()
        _ckpt(job, index + 1, len(pages), f'Guardada página {index + 1} de {len(pages)}')
    if partial_pages:
        raise ValueError('Lectura parcial o fallida en las páginas ' + ', '.join(map(str, partial_pages)) +
                         '. Las propuestas obtenidas se conservaron para revisión y reintento.')
    _ckpt(job, len(pages), len(pages), 'Listo para revisar')

def _export(job):
    from app.extensions import db
    from app.models import Document, Page, Line, Collection
    from app.config import settings
    from app.services_storage import ObjectStorage
    import tempfile
    s = settings(); st = ObjectStorage(s)
    p = job.payload or {}
    fmt = p.get("format", "json")
    text_source = p.get("text_source", "revised_fallback_auto")
    doc_ids = []
    if p.get("document_id"): doc_ids = [p["document_id"]]
    elif p.get("collection_id"):
        doc_ids = [d.id for d in Document.query.filter_by(collection_id=p["collection_id"]).all()]
    _ckpt(job, 0, max(1, len(doc_ids)), "Preparando exportación")
    if not doc_ids:
        raise ValueError("No hay documentos para exportar.")
    if p.get("collection_id") and fmt in ("json", "pdf-facsimil", "pdf-lectura", "docx"):
        # Cada documento de la colección debe llegar al usuario, no solo el último.
        import zipfile
        from app.services_export_pdf import build_pdf
        with tempfile.TemporaryDirectory() as temp_dir:
            zpath = os.path.join(temp_dir, "coleccion.zip")
            with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
                for i, did in enumerate(doc_ids):
                    if fmt == "json":
                        data = _build_json(did, text_source)
                        z.writestr(f"{did}.json", json.dumps(data, ensure_ascii=False, indent=2))
                    elif fmt == "docx":
                        from app.services_export_docx import build_docx
                        word_path = os.path.join(temp_dir, f"{did}.docx")
                        build_docx(did, word_path, text_source=text_source)
                        z.write(word_path, arcname=f"{did}.docx")
                    else:
                        pdf_path = os.path.join(temp_dir, f"{did}.pdf")
                        build_pdf(did, pdf_path, mode=fmt, text_source=text_source, storage=st)
                        z.write(pdf_path, arcname=f"{did}.pdf")
                    _ckpt(job, i + 1, len(doc_ids), "Preparando documentos")
            key = f"exports/{job.id}/coleccion.zip"
            st.put_file(key, zpath)
        job.payload = {**job.payload, "result_key": key}
        db.session.commit()
        _ckpt(job, len(doc_ids), len(doc_ids), "Exportación lista")
        return
    if fmt == "json":
        for i, did in enumerate(doc_ids):
            data = _build_json(did, text_source)
            import tempfile as _t
            t = _t.mktemp(suffix=".json"); open(t, "w", encoding="utf-8").write(json.dumps(data, ensure_ascii=False, indent=2))
            key = f"exports/{job.id}/{did}.json"
            st.put_file(key, t)
            job.payload = {**job.payload, "result_key": key, "summary": {"mixed": data["meta"].get("mixed", False)}}
            db.session.commit()
            _ckpt(job, i + 1, len(doc_ids), "Escribiendo JSON")
    elif fmt in ("pdf-facsimil", "pdf-lectura"):
        from app.services_export_pdf import build_pdf
        for i, did in enumerate(doc_ids):
            t = tempfile.mktemp(suffix=".pdf")
            summary = build_pdf(did, t, mode=fmt, text_source=text_source, storage=st)
            key = f"exports/{job.id}/{did}.pdf"
            st.put_file(key, t)
            job.payload = {**job.payload, "result_key": key, "summary": summary}
            db.session.commit()
            _ckpt(job, i + 1, len(doc_ids), "Escribiendo PDF")
    elif fmt == "docx":
        from app.services_export_docx import build_docx
        with tempfile.TemporaryDirectory() as temp_dir:
            did = doc_ids[0]
            word_path = os.path.join(temp_dir, f"{did}.docx")
            summary = build_docx(did, word_path, text_source=text_source)
            key = f"exports/{job.id}/{did}.docx"
            st.put_file(key, word_path)
        job.payload = {**job.payload, "result_key": key, "summary": summary}
        db.session.commit()
        _ckpt(job, 1, 1, "Escribiendo Word")
    elif fmt == "zip":
        import zipfile, tempfile as _t
        zpath = _t.mktemp(suffix=".zip")
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            for did in doc_ids:
                data = _build_json(did, text_source)
                z.writestr(f"{did}.json", json.dumps(data, ensure_ascii=False, indent=2))
        key = f"exports/{job.id}/coleccion.zip"
        st.put_file(key, zpath)
        job.payload = {**job.payload, "result_key": key}
        db.session.commit()
    _ckpt(job, len(doc_ids), len(doc_ids), "Exportación lista")

def _build_json(doc_id, text_source):
    from app.models import Document, Page, Line, SourceFile, ModelVersion
    from app.services_ocr import export_page_ocr
    d = Document.query.get(doc_id)
    pages = Page.query.filter_by(document_id=doc_id).order_by(Page.order_index).all()
    items, full, mixed = [], [], False
    has_rev = has_auto = False
    for pg in pages:
        lines = Line.query.filter_by(page_id=pg.id).order_by(Line.order_index).all()
        ocr = export_page_ocr(pg.id, text_source)
        li = []
        for l in lines:
            use_rev = l.revised_text is not None and text_source.startswith("revised")
            txt = l.revised_text if use_rev else l.auto_text
            if l.revised_text is not None: has_rev = True
            if l.auto_text: has_auto = True
            li.append({"id": l.id, "order": l.order_index, "baseline": l.baseline, "polygon": l.polygon,
                       "auto_text": l.auto_text, "revised_text": l.revised_text, "text": txt,
                       "state": l.state, "confidence": l.confidence, "note": l.note})
            if not ocr:
                full.append(txt or "")
        if ocr and ocr['selected_transcription'] is not None:
            full.append(ocr['selected_transcription'])
        items.append({"id": pg.id, "order": pg.order_index, "folio": pg.folio, "width": pg.width,
                      "height": pg.height, "status": pg.status, "lines": li, "ocr": ocr})
    mixed = has_rev and has_auto
    return {"schema": "servator-memoriae/1", "id": d.id, "title": d.title,
            "collection_id": d.collection_id, "metadata": {"type": d.doc_type, "years": [d.year_start, d.year_end],
            "signature": d.signature, "description": d.description, "tags": d.tags},
            "pages": items, "full_text": "\n".join(full),
            "meta": {"mixed": mixed, "text_source": text_source,
                     "engine": "ver páginas.ocr; las páginas antiguas utilizan kraken==7.1.1",
                     "normalization": "se conserva Unicode original (NFC), sin normalizar grafías"}}

def _prepare(job):
    import kraken_adapter
    from app.extensions import db
    from app.models import ModelVersion
    import hashlib
    def cb(done, total):
        from app.services_queue import emit
        emit(job.id, "progress", {"done": done, "total": total, "phase": "Descargando lector"})
    _ckpt(job, 0, 1, "Descargando lector (una sola vez)")
    w = kraken_adapter.ensure_model("v1", progress_cb=cb)
    sha = kraken_adapter.sha256_file(w)
    _ckpt(job, 0, 1, "Verificando y cargando")
    try:
        res = kraken_adapter.smoke_test("v1")
    except Exception as e:
        res = {"ok": False, "error": str(e)[:500]}
    if not res.get("ok"):
        raise ValueError(f"No se pudo comprobar el lector: {res.get('error', 'no se detectaron líneas en la prueba')}")
    if not ModelVersion.query.filter_by(version="v1", name="ppocrv6-medium").first():
        db.session.add(ModelVersion(name="ppocrv6-medium", version="v1", kind="recognizer",
            weights_key=w, sha256=sha, size_bytes=os.path.getsize(w),
            source=kraken_adapter.MODEL_URL, license="Apache-2.0", engine_version=kraken_adapter.ENGINE_VERSION,
            is_active_global=True, metrics={"smoke": res}))
        db.session.commit()
    _ckpt(job, 1, 1, "Lector listo para transcribir")


def _prepare_paddle(job):
    from engine.paddle_assets import ensure_assets
    from app.services_paddle import prepare
    def progress_bytes(done, total, phase):
        _ckpt(job, done, total, phase)
    from app.services_gpu_lock import gpu_guard, paddle_guard, resource_guard
    with resource_guard('paddle-download'):
        ensure_assets(progress=progress_bytes)
    _ckpt(job, 0, 1, 'Comprobando lectura real de una imagen')
    device = (job.payload or {}).get('device', 'cpu')
    with gpu_guard(device == 'cuda'):
        with paddle_guard():
            result = prepare(device)
    actual = result.get('device', device)
    _ckpt(job, 1, 1, f'PaddleOCR-VL comprobado en {"GPU" if actual == "cuda" else "CPU"}')

def _train(job):
    # Los jobs creados antes de deshabilitar el entrenamiento también deben fallar
    # claramente: el adaptador anterior no entrenaba ni evaluaba imágenes reales.
    from app.extensions import db
    from app.models import TrainingRun
    run = TrainingRun.query.get((job.payload or {}).get("training_run_id"))
    if run:
        run.status = "FAILED"
        db.session.commit()
    raise ValueError("El entrenamiento todavía no está disponible; tus correcciones se conservan.")
