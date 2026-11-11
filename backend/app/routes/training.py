"""Mejorar lectura: perfiles, snapshots, particiones, entrenamiento, evaluación, activación."""
import datetime
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.models import TrainingRun, ModelVersion, Line, Page, Job, Document
from app.utils_security import require
from app.services_queue import new_job, dispatch

bp = Blueprint("training", __name__)

@bp.get("/training/examples")
@login_required
def training_examples():
    """Resume ejemplos revisados sin afirmar que ya existe un ajuste funcional."""
    documents = Document.query.order_by(Document.created_at.desc()).limit(200).all()
    ids = [doc.id for doc in documents]
    pages = Page.query.filter(Page.document_id.in_(ids)).all() if ids else []
    page_docs = {page.id: page.document_id for page in pages}
    counts = {doc.id: {"pages": 0, "reviewed_pages": set(), "lines": 0} for doc in documents}
    for page in pages:
        counts[page.document_id]["pages"] += 1
    lines = Line.query.filter(Line.page_id.in_(list(page_docs)),
                              Line.state.in_(["confirmed", "corrected"])).all() if page_docs else []
    for line in lines:
        text = line.revised_text if line.revised_text is not None else line.auto_text
        if not (text or "").strip():
            continue
        count = counts[page_docs[line.page_id]]
        count["lines"] += 1
        count["reviewed_pages"].add(line.page_id)
    return jsonify({"training_available": False, "items": [
        {"id": doc.id, "title": doc.title, "pages": counts[doc.id]["pages"],
         "reviewed_pages": len(counts[doc.id]["reviewed_pages"]),
         "lines": counts[doc.id]["lines"]} for doc in documents]})

@bp.post("/training/runs")
@login_required
@require("train")
def create_run():
    d = request.get_json(force=True) or {}
    page_ids = d.get("page_ids", [])
    if not page_ids:
        return jsonify({"error": "Elegí páginas con revisiones confirmadas"}), 422
    # snapshot inmutable: imágenes, texto, geometría, autores, hashes
    lines = Line.query.filter(Line.page_id.in_(page_ids), Line.state.in_(["confirmed", "corrected"])).all()
    if len(lines) < 10:
        return jsonify({"error": "Todavía no tenemos suficientes ejemplos para medir bien la mejora. Confirmá más renglones.",
                        "lines": len(lines)}), 422
    # El adaptador actual no produce un modelo evaluable a partir de imágenes reales.
    # No crear una ejecución que pueda aparentar éxito con métricas inválidas.
    return jsonify({"error": "El entrenamiento todavía no está disponible. Tus correcciones se conservan para una futura versión."}), 503

@bp.post("/training/runs/<rid>/start")
@login_required
@require("train")
def start_run(rid):
    TrainingRun.query.get_or_404(rid)
    return jsonify({"error": "El entrenamiento todavía no está disponible. Tus correcciones se conservan para una futura versión."}), 503

@bp.get("/training/runs")
@login_required
def list_runs():
    items = TrainingRun.query.order_by(TrainingRun.created_at.desc()).limit(50).all()
    return jsonify({"items": [{"id": r.id, "name": r.name, "status": r.status, "metrics": r.metrics,
                               "result_model": r.result_model_id} for r in items]})

@bp.get("/training/runs/<rid>")
@login_required
def get_run(rid):
    r = TrainingRun.query.get_or_404(rid)
    return jsonify({"id": r.id, "name": r.name, "status": r.status, "config": r.config,
                    "snapshot": r.snapshot, "metrics": r.metrics, "result_model": r.result_model_id})
