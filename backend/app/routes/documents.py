"""Colecciones, documentos, páginas, líneas, subida e importación robusta."""
import os, io, re, hashlib, datetime, mimetypes
from flask import Blueprint, request, jsonify, g, send_file
from flask_login import current_user, login_required
from app.extensions import db
from app.models import Collection, Document, SourceFile, Page, Line, TranscriptionVersion
from app.utils_security import require
from app.config import settings
from app.services_storage import ObjectStorage

bp = Blueprint("docs", __name__)

def _storage():
    return ObjectStorage(settings())

def _natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s or "")]

def _detect_kind(filename, header: bytes):
    fn = filename.lower()
    if fn.endswith((".tif", ".tiff")): return "tiff"
    if fn.endswith(".pdf"): return "pdf"
    if header[:4] == b"%PDF": return "pdf"
    if header[:2] in (b"II", b"MM"): return "tiff"
    return "image"

def _split_pdf(data: bytes, max_pages):
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(data)
    n = len(pdf)
    if n > max_pages:
        raise ValueError(f"El PDF tiene {n} páginas y el límite es {max_pages}")
    out = []
    for i in range(n):
        page = pdf[i]
        bmp = page.render(scale=2).to_pil()
        buf = io.BytesIO(); bmp.save(buf, format="PNG")
        out.append(buf.getvalue())
    return out

def _split_tiff(data: bytes, max_pages):
    from PIL import Image
    im = Image.open(io.BytesIO(data))
    out = []
    try:
        for i in range(max_pages + 1):
            im.seek(i)
            frame = im.copy().convert("RGB")
            buf = io.BytesIO(); frame.save(buf, format="PNG")
            out.append(buf.getvalue())
    except EOFError:
        pass
    if len(out) > max_pages:
        raise ValueError(f"El TIFF tiene más de {max_pages} páginas")
    return out

@bp.get("/collections")
@login_required
def list_collections():
    q = (request.args.get("q") or "").lower()
    items = Collection.query.order_by(Collection.created_at.desc()).limit(100).all()
    res = [{"id": c.id, "title": c.title, "description": c.description} for c in items
           if not q or q in (c.title or "").lower()]
    return jsonify({"items": res})

@bp.post("/collections")
@login_required
@require("upload")
def create_collection():
    d = request.get_json(force=True) or {}
    c = Collection(title=d.get("title", "Sin título")[:512], description=d.get("description", ""),
                   owner_id=current_user.id)
    db.session.add(c); db.session.commit()
    return jsonify({"id": c.id, "title": c.title}), 201

@bp.get("/documents")
@login_required
def list_docs():
    q = (request.args.get("q") or "").lower()
    col = request.args.get("collection_id")
    query = Document.query
    if col: query = query.filter_by(collection_id=col)
    docs = query.order_by(Document.created_at.desc()).limit(200).all()
    out = []
    for d in docs:
        if q and q not in ((d.title or "") + " " + (d.signature or "") + " " + " ".join(d.tags or [])).lower():
            continue
        npages = Page.query.filter_by(document_id=d.id).count()
        out.append({"id": d.id, "title": d.title, "collection_id": d.collection_id,
                    "doc_type": d.doc_type, "year_start": d.year_start, "year_end": d.year_end,
                    "signature": d.signature, "pages": npages})
    return jsonify({"items": out})

@bp.post("/documents")
@login_required
@require("upload")
def create_doc():
    d = request.get_json(force=True) or {}
    doc = Document(title=d.get("title", "Sin título")[:512], collection_id=d.get("collection_id"),
                   doc_type=d.get("doc_type", "libro"), year_start=d.get("year_start"),
                   year_end=d.get("year_end"), signature=d.get("signature", ""),
                   description=d.get("description", ""), tags=d.get("tags", [])[:20],
                   owner_id=current_user.id)
    db.session.add(doc); db.session.commit()
    return jsonify({"id": doc.id}), 201

@bp.get("/documents/<doc_id>")
@login_required
def get_doc(doc_id):
    d = Document.query.get_or_404(doc_id)
    pages = Page.query.filter_by(document_id=doc_id).order_by(Page.order_index).all()
    return jsonify({"id": d.id, "title": d.title, "collection_id": d.collection_id,
        "doc_type": d.doc_type, "year_start": d.year_start, "year_end": d.year_end,
        "signature": d.signature, "description": d.description, "tags": d.tags,
        "pages": [{"id": p.id, "order": p.order_index, "folio": p.folio, "status": p.status,
                   "width": p.width, "height": p.height} for p in pages]})

@bp.post("/documents/<doc_id>/upload")
@login_required
@require("upload")
def upload(doc_id):
    """Subida por archivo con hash, validación real y expansión PDF/TIFF a páginas."""
    s = settings()
    d = Document.query.get_or_404(doc_id)
    files = request.files.getlist("files") or ([request.files["file"]] if "file" in request.files else [])
    if not files:
        return jsonify({"error": "Sin archivos. Agregá escaneos JPG, PNG, TIFF o PDF."}), 422
    st = _storage()
    from PIL import Image
    added, dupes, errors = [], [], []
    # orden natural de filenames
    files = sorted(files, key=lambda f: _natural_key(f.filename))
    base_order = Page.query.filter_by(document_id=doc_id).count()
    for f in files:
        savepoint = None
        stored_keys = []
        starting_order = base_order
        try:
            data = f.read()
            if len(data) > s.MAX_UPLOAD_MB * 1024 * 1024:
                errors.append({"file": f.filename, "error": f"Supera el límite de {s.MAX_UPLOAD_MB} MB"})
                continue
            sha = hashlib.sha256(data).hexdigest()
            dupe = SourceFile.query.filter_by(sha256=sha, document_id=doc_id).first()
            if dupe:
                dupes.append({"file": f.filename, "source_id": dupe.id})
                continue
            kind = _detect_kind(f.filename, data[:8])
            if kind == "pdf":
                try: pages_img = _split_pdf(data, s.MAX_PAGES_PER_FILE)
                except Exception as e:
                    errors.append({"file": f.filename, "error": f"Esta página no se pudo abrir ({e}). Las otras se conservaron."})
                    continue
            elif kind == "tiff":
                try: pages_img = _split_tiff(data, s.MAX_PAGES_PER_FILE)
                except Exception as e:
                    errors.append({"file": f.filename, "error": f"TIFF dañado o excesivo: {e}"})
                    continue
            else:
                # valida imagen real
                try:
                    im = Image.open(io.BytesIO(data)); im.verify()
                except Exception:
                    errors.append({"file": f.filename, "error": "Archivo dañado o formato no admitido (se admiten JPG, PNG, TIFF, PDF)"})
                    continue
                pages_img = [data]
            # Cada archivo es atómico: si falla una página no debe quedar un
            # original parcial que luego se confunda con una subida duplicada.
            savepoint = db.session.begin_nested()
            # preserva original inmutable
            src = SourceFile(document_id=doc_id, filename=f.filename, sha256=sha,
                             size_bytes=len(data), mime=mimetypes.guess_type(f.filename)[0] or "application/octet-stream",
                             storage_key=f"originals/{doc_id}/{sha[:12]}-{f.filename}",
                             pages_detected=len(pages_img))
            import tempfile
            tmp = tempfile.mktemp(); open(tmp, "wb").write(data)
            stored_keys.append(src.storage_key)
            st.put_file(src.storage_key, tmp); os.remove(tmp)
            db.session.add(src); db.session.flush()
            for i, pdata in enumerate(pages_img):
                # normaliza a PNG + thumbnail, respeta EXIF
                from PIL import ImageOps
                im = Image.open(io.BytesIO(pdata)); im = ImageOps.exif_transpose(im).convert("RGB")
                key = f"pages/{doc_id}/{src.id}-{i}.png"
                thkey = f"thumbs/{doc_id}/{src.id}-{i}.png"
                import tempfile as _t
                t1 = _t.mktemp(suffix=".png"); im.save(t1)
                stored_keys.append(key)
                st.put_file(key, t1)
                th = im.copy(); th.thumbnail((320, 320)); t2 = _t.mktemp(suffix=".png"); th.save(t2)
                stored_keys.append(thkey)
                st.put_file(thkey, t2)
                for t in (t1, t2):
                    try: os.remove(t)
                    except Exception: pass
                p = Page(document_id=doc_id, source_file_id=src.id, order_index=base_order,
                         width=im.width, height=im.height, image_key=key, thumb_key=thkey, status="imported")
                db.session.add(p); base_order += 1
            savepoint.commit()
            added.append({"file": f.filename, "pages": len(pages_img), "source_id": src.id})
        except Exception as e:
            if savepoint is not None:
                savepoint.rollback()
                base_order = starting_order
                for key in stored_keys:
                    try:
                        st.delete(key)
                    except Exception:
                        pass
            errors.append({"file": getattr(f, 'filename', '?'), "error": str(e)[:300]})
    db.session.commit()
    return jsonify({"added": added, "duplicates": dupes, "errors": errors})

@bp.patch("/documents/<doc_id>/pages/order")
@login_required
@require("upload")
def reorder(doc_id):
    d = request.get_json(force=True) or {}
    ids = d.get("order", [])
    for i, pid in enumerate(ids):
        p = Page.query.filter_by(id=pid, document_id=doc_id).first()
        if p: p.order_index = i
    db.session.commit()
    return jsonify({"ok": True})

@bp.patch("/pages/<page_id>")
@login_required
@require("review")
def patch_page(page_id):
    p = Page.query.get_or_404(page_id)
    d = request.get_json(force=True) or {}
    if "folio" in d: p.folio = str(d["folio"])[:64]
    if "rotation" in d: p.rotation = int(d["rotation"]) % 360
    if "crop" in d: p.crop = d["crop"]
    db.session.commit()
    return jsonify({"ok": True})

@bp.get("/pages/<page_id>/lines")
@login_required
def page_lines(page_id):
    lines = Line.query.filter_by(page_id=page_id).order_by(Line.order_index).all()
    return jsonify({"items": [{"id": l.id, "order": l.order_index, "baseline": l.baseline,
        "polygon": l.polygon, "auto_text": l.auto_text, "revised_text": l.revised_text,
        "confidence": l.confidence, "state": l.state, "note": l.note, "version": l.version} for l in lines]})


@bp.get('/pages/<page_id>/ocr')
@login_required
def page_ocr(page_id):
    Page.query.get_or_404(page_id)
    from app.services_ocr import latest_page_ocr
    from app.services_comparison import compare_texts
    data = latest_page_ocr(page_id)
    if not data:
        return jsonify({'available': False})
    job, results, review = data['job'], data['results'], data['review']
    by_engine = {(r.engine if r.engine in ('kraken', 'paddleocr_vl') else 'historical'):
                 {'text': r.text, 'status': r.status, 'error': r.error,
                  'device': r.device, 'model_version': r.model_version,
                  'elapsed_seconds': (r.details or {}).get('elapsed_seconds'),
                  'fallback_reason': (r.details or {}).get('fallback_reason')} for r in results}
    k, other = by_engine.get('kraken'), by_engine.get('paddleocr_vl') or by_engine.get('historical')
    comparison = compare_texts(k['text'], other['text']) if k and other and k['status'] == other['status'] == 'completed' else None
    raw_mode = (job.payload or {}).get('ocr_mode')
    mode = raw_mode if raw_mode in ('dual', 'paddleocr_vl') else 'historical'
    review_source = (review.source if review and review.source in ('kraken', 'paddleocr_vl', 'manual', 'mixed') else 'historical')
    return jsonify({'available': True, 'job_id': job.id, 'mode': mode,
        'engines': by_engine, 'comparison': comparison,
        'review': {'text': review.text, 'source': review_source, 'version': review.version,
                   'job_id': review.job_id, 'user_id': review.user_id,
                   'created_at': review.created_at.isoformat()} if review else None})


@bp.post('/pages/<page_id>/ocr/review')
@login_required
@require('review')
def review_page_ocr(page_id):
    from app.models import OcrReview, OcrResult
    from sqlalchemy.exc import IntegrityError
    Page.query.get_or_404(page_id)
    data = request.get_json(silent=True) or {}
    job_id, text = data.get('job_id'), data.get('text')
    source = data.get('source', 'manual')
    if not isinstance(text, str) or len(text) > 1000000 or source not in ('kraken', 'paddleocr_vl', 'historical', 'manual', 'mixed'):
        return jsonify({'error': 'Revisá el texto y el origen de la transcripción.'}), 422
    if not OcrResult.query.filter_by(page_id=page_id, job_id=job_id, status='completed').first():
        return jsonify({'error': 'No se encontró la lectura seleccionada.'}), 404
    if source in ('kraken', 'paddleocr_vl', 'historical'):
        query = OcrResult.query.filter_by(page_id=page_id, job_id=job_id, status='completed')
        proposal = (query.filter(~OcrResult.engine.in_(['kraken', 'paddleocr_vl'])).first()
                    if source == 'historical' else query.filter_by(engine=source).first())
        if not proposal or proposal.text != text:
            return jsonify({'error': 'El texto modificado debe guardarse como corrección manual.'}), 422
        if source == 'historical':
            source = proposal.engine
    previous = OcrReview.query.filter_by(page_id=page_id).order_by(OcrReview.version.desc()).first()
    version = previous.version if previous else 0
    if data.get('version', 0) != version:
        return jsonify({'error': 'Otra persona guardó una revisión. Recargá antes de volver a guardar.'}), 409
    db.session.add(OcrReview(page_id=page_id, job_id=job_id, user_id=current_user.id,
                             version=version + 1, source=source, text=text))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({'error': 'Otra persona guardó una revisión. Recargá antes de volver a guardar.'}), 409
    return jsonify({'ok': True, 'version': version + 1})

@bp.patch("/lines/<line_id>")
@login_required
@require("review")
def patch_line(line_id):
    l = Line.query.get_or_404(line_id)
    d = request.get_json(force=True) or {}
    # control de concurrencia optimista
    if "version" in d and int(d["version"]) != l.version:
        return jsonify({"error": "Otro editor guardó antes. Recargá y combiná los cambios."}), 409
    if "revised_text" in d: l.revised_text = d["revised_text"]
    if "state" in d and d["state"] in ("auto", "confirmed", "corrected", "illegible", "bad_cut", "skipped"):
        l.state = d["state"]
    if "note" in d: l.note = str(d["note"])[:2000]
    l.version += 1
    db.session.commit()
    return jsonify({"ok": True, "version": l.version})

@bp.get("/pages/<page_id>/image")
@login_required
def page_image(page_id):
    p = Page.query.get_or_404(page_id)
    st = _storage()
    key = (p.thumb_key or p.image_key) if request.args.get("thumbnail") == "1" else p.image_key
    path = st.get_path(key)
    return send_file(path, mimetype="image/png")
