"""Opciones de procesamiento para próximas transcripciones."""
from flask import Blueprint, jsonify, request
from flask_login import login_required

from app.services_device import processing_status, probe_workers, save_preference, get_ocr_mode, VALID_DEVICES, VALID_OCR_MODES
from app.utils_security import require

bp = Blueprint("settings", __name__)


@bp.get("/settings/processing")
@login_required
def get_processing():
    try:
        return jsonify(processing_status())
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 503


@bp.put("/settings/processing")
@login_required
@require("admin")
def set_processing():
    data = request.get_json(silent=True) or {}
    device = data.get("device")
    mode = data.get("ocr_mode")
    if device is not None and device not in VALID_DEVICES:
        return jsonify({"error": "Elegí Automático, CPU o GPU NVIDIA."}), 422
    if mode is not None and mode not in VALID_OCR_MODES:
        return jsonify({"error": "Elegí un motor de transcripción válido."}), 422
    if device is None and mode is None:
        return jsonify({"error": "Elegí una opción para guardar."}), 422
    if device is not None and (mode or get_ocr_mode()) != "kraken":
        return jsonify({"error": "El dispositivo solo se configura al elegir Kraken."}), 409
    if device == "cuda" and not probe_workers()["cuda"]["available"]:
        return jsonify({"error": "La GPU todavía no está disponible. Revisá el componente GPU y volvé a intentar."}), 409
    try:
        save_preference(device=device, ocr_mode=mode)
        if mode in ("paddleocr_vl", "dual"):
            from flask_login import current_user
            from app.models import Job
            from app.services_queue import new_job, dispatch
            from app.services_paddle import automatic_device, paddle_status
            paddle = paddle_status()
            target = automatic_device(paddle)
            active = Job.query.filter(Job.kind == 'prepare_paddle', Job.status.in_(['PENDING', 'QUEUED', 'RUNNING'])).first()
            if not active and (not paddle['ready'] or paddle['device'] != target):
                job = new_job('prepare_paddle', current_user.id, {'device': target}, total=1)
                dispatch(job)
        return jsonify(processing_status())
    except (OSError, ValueError):
        return jsonify({"error": "No se pudo guardar la configuración. Volvé a intentarlo."}), 503
