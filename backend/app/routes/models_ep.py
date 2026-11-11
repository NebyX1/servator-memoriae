"""Model registry: manifiesto, descarga, activación."""
import os
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.models import ModelVersion
from app.utils_security import require
from app.services_queue import new_job, dispatch

bp = Blueprint("models_ep", __name__)

@bp.get("/models")
@login_required
def list_models():
    items = ModelVersion.query.order_by(ModelVersion.created_at.desc()).all()
    return jsonify({"items": [{"id": m.id, "name": m.name, "version": m.version, "kind": m.kind,
        "sha256": m.sha256, "size": m.size_bytes, "source": m.source, "license": m.license,
        "engine": m.engine_version, "active_global": m.is_active_global,
        "active_collection": m.active_for_collection, "metrics": m.metrics} for m in items]})

@bp.post("/models/download-base")
@login_required
@require("admin")
def download_base():
    job = new_job("prepare_model", current_user.id, {"model": "ppocrv6-medium", "version": "v1"},
                  idem_key="prepare-v1", total=1)
    dispatch(job)
    return jsonify({"job_id": job.id}), 201

@bp.post("/models/<mid>/activate")
@login_required
@require("activate_model")
def activate(mid):
    m = ModelVersion.query.get_or_404(mid)
    d = request.get_json(force=True, silent=True) or {}
    scope = d.get("collection_id")
    if scope:
        # desactiva otros para esa colección
        for o in ModelVersion.query.filter_by(active_for_collection=scope).all():
            o.active_for_collection = None
        m.active_for_collection = scope
    else:
        for o in ModelVersion.query.filter_by(is_active_global=True).all():
            o.is_active_global = False
        m.is_active_global = True
    db.session.commit()
    return jsonify({"ok": True})

@bp.post("/models/import-local")
@login_required
@require("admin")
def import_local():
    """Importar artefactos oficiales para instalaciones sin conexión."""
    d = request.get_json(force=True, silent=True) or {}
    path = d.get("path", "")
    if not os.path.isfile(path):
        return jsonify({"error": "Archivo local no encontrado en el servidor"}), 422
    import hashlib, shutil
    h = hashlib.sha256(open(path, "rb").read()).hexdigest()
    dst = os.path.join(os.environ.get("MODEL_DIR", "./data/models"), os.path.basename(path))
    shutil.copyfile(path, dst)
    m = ModelVersion(name="ppocrv6-medium", version=d.get("version", "imported"), kind="recognizer",
                     weights_key=dst, sha256=h, size_bytes=os.path.getsize(dst),
                     source="import-local", license=d.get("license", "Apache-2.0"), engine_version="kraken==7.1.1")
    db.session.add(m); db.session.commit()
    return jsonify({"id": m.id, "sha256": h}), 201
