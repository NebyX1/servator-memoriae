"""Exportaciones JSON, PDF y Word como trabajos asíncronos."""
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from app.models import Job, Export, Document, Collection
from app.extensions import db
from app.utils_security import require
from app.services_queue import new_job, dispatch

bp = Blueprint("exports", __name__)

@bp.post("/exports")
@login_required
@require("export")
def create_export():
    d = request.get_json(force=True) or {}
    fmt = d.get("format", "json")
    if fmt not in ("json", "pdf-facsimil", "pdf-lectura", "docx", "zip"):
        return jsonify({"error": "Formato no válido"}), 422
    doc_id, collection_id = d.get("document_id"), d.get("collection_id")
    if bool(doc_id) == bool(collection_id):
        return jsonify({"error": "Elegí un documento o una colección."}), 422
    if doc_id and not Document.query.get(doc_id):
        return jsonify({"error": "Documento no encontrado."}), 404
    if collection_id and not Collection.query.get(collection_id):
        return jsonify({"error": "Colección no encontrada."}), 404
    job = new_job("export", current_user.id, {"document_id": d.get("document_id"),
        "collection_id": d.get("collection_id"), "format": fmt,
        "text_source": d.get("text_source", "revised_fallback_auto"),
        "include_originals": bool(d.get("include_originals", False))},
        idem_key=d.get("idempotency_key", ""), total=1)
    dispatch(job)
    return jsonify({"job_id": job.id}), 201

@bp.get("/exports/<job_id>/download")
@login_required
def download(job_id):
    from app.services_storage import ObjectStorage
    from app.config import settings
    from flask import send_file
    j = Job.query.get_or_404(job_id)
    key = (j.payload or {}).get("result_key", "")
    if not key or j.status != "COMPLETED":
        return jsonify({"error": "Exportación aún no disponible"}), 409
    st = ObjectStorage(settings())
    mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document" if key.lower().endswith(".docx") else None
    return send_file(st.get_path(key), as_attachment=True, download_name=key.split("/")[-1], mimetype=mime)
