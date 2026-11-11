"""Jobs: transcribir, estado, SSE con reconexión + polling fallback."""
import json, datetime
from flask import Blueprint, request, jsonify, Response, g
from flask_login import login_required, current_user
from app.extensions import db
from app.models import Job, JobEvent, Page, Document
from app.utils_security import require
from app.services_queue import new_job, dispatch

bp = Blueprint("jobs", __name__)

@bp.post("/jobs/transcribe")
@login_required
@require("transcribe")
def transcribe():
    d = request.get_json(force=True) or {}
    doc_id = d.get("document_id")
    if not doc_id: return jsonify({"error": "document_id requerido"}), 422
    from app.services_device import resolve_device, get_ocr_mode
    from app.services_paddle import automatic_device, paddle_status, MODEL_REVISION
    mode = get_ocr_mode()
    try:
        if mode == 'kraken':
            device = resolve_device(d.get("device"))
        else:
            status = paddle_status()
            device = automatic_device(status)
            if not status['ready'] or status['device'] != device:
                return jsonify({"error": "PaddleOCR-VL todavía no está preparado para este equipo. Revisá el avance en Configuración."}), 409
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409
    pages = Page.query.filter_by(document_id=doc_id).order_by(Page.order_index).all()
    if not pages: return jsonify({"error": "El documento no tiene páginas"}), 422
    try:
        job = new_job("transcribe", current_user.id,
                      {"document_id": doc_id, "page_ids": [p.id for p in pages],
                       "model_version": d.get("model_version", "v1"),
                       "device": device, "ocr_mode": mode,
                       "kraken_device": 'cpu' if mode == 'dual' else device,
                       "paddle_revision": MODEL_REVISION if mode != 'kraken' else None},
                      idem_key=d.get("idempotency_key", ""), total=len(pages))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409
    if job.status == "PENDING":
        dispatch(job)
    return jsonify({"job_id": job.id, "total": len(pages), "device": device, "ocr_mode": mode}), 201

@bp.get("/jobs/<job_id>")
@login_required
def job_status(job_id):
    j = Job.query.get_or_404(job_id)
    return jsonify({"id": j.id, "kind": j.kind, "status": j.status, "phase": j.phase,
        "device": (j.payload or {}).get("device") if j.kind == "transcribe" else None,
        "done": j.progress_done, "total": j.progress_total, "error": j.error,
        "cancel_requested": j.cancel_requested})

@bp.post("/jobs/<job_id>/cancel")
@login_required
def job_cancel(job_id):
    j = Job.query.get_or_404(job_id)
    j.cancel_requested = True; db.session.commit()
    return jsonify({"ok": True})

@bp.post("/jobs/<job_id>/retry")
@login_required
@require("transcribe")
def job_retry(job_id):
    j = Job.query.get_or_404(job_id)
    payload = j.payload or {}
    if j.kind == 'transcribe' and (payload.get('ocr_mode', 'kraken') not in ('kraken', 'paddleocr_vl', 'dual')
        or (payload.get('ocr_mode') == 'dual' and not payload.get('paddle_revision'))):
        return jsonify({'error': 'Este trabajo usa un lector retirado. Sus resultados se conservan; iniciá una lectura nueva.'}), 409
    j.status = "PENDING"; j.cancel_requested = False; j.error = ""
    db.session.commit(); dispatch(j)
    return jsonify({"ok": True})

@bp.get("/jobs/<job_id>/events")
@login_required
def job_events(job_id):
    """SSE autenticado con Last-Event-ID + heartbeat. Polling fallback: ?poll=1."""
    j = Job.query.get_or_404(job_id)
    if request.args.get("poll"):
        evs = JobEvent.query.filter_by(job_id=job_id).order_by(JobEvent.seq).all()
        return jsonify({"status": j.status, "done": j.progress_done, "total": j.progress_total,
                        "phase": j.phase, "events": [{"seq": e.seq, "kind": e.kind, "data": e.data} for e in evs]})
    last = int(request.headers.get("Last-Event-ID", request.args.get("last", 0)) or 0)
    def gen():
        yield ": heartbeat\n\n"
        evs = JobEvent.query.filter(JobEvent.job_id == job_id, JobEvent.seq > last).order_by(JobEvent.seq).all()
        for e in evs:
            yield f"id: {e.seq}\nevent: {e.kind}\ndata: {json.dumps(e.data, ensure_ascii=False)}\n\n"
        # estado actual como evento final del snapshot
        yield f"event: status\ndata: {json.dumps({'status': j.status, 'done': j.progress_done, 'total': j.progress_total, 'phase': j.phase})}\n\n"
    return Response(gen(), mimetype="text/event-stream", headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})

@bp.get("/reader/status")
def reader_status():
    import os
    md = os.environ.get("MODEL_DIR", "./data/models")
    files = os.listdir(md) if os.path.isdir(md) else []
    ready = any(f.endswith(".safetensors") for f in files)
    return jsonify({"reader": "ready" if ready else "pending",
                    "message": "Lector listo para transcribir" if ready else "Estamos preparando el lector. Esta descarga se hace una sola vez."})
