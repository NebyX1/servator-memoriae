"""Preferencia de procesamiento y disponibilidad real de workers."""
import datetime
import json
import os
import tempfile
from pathlib import Path

from app.config import settings

VALID_DEVICES = ("auto", "cpu", "cuda")
VALID_OCR_MODES = ("kraken", "paddleocr_vl", "dual")


def _preference_path():
    return Path(settings().DATA_DIR) / "config" / "processing.json"


def get_preference():
    path = _preference_path()
    if not path.exists():
        default = settings().DEVICE_MODE
        return default if default in VALID_DEVICES else "auto"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))["device"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError("No se pudo leer la configuración de procesamiento.") from exc
    if value not in VALID_DEVICES:
        raise ValueError("La configuración de procesamiento no es válida.")
    return value


def get_ocr_mode():
    path = _preference_path()
    if not path.exists():
        return "kraken"
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
        value = stored.get("ocr_mode", "kraken")
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError("No se pudo leer la configuración de procesamiento.") from exc
    if value not in VALID_OCR_MODES or (value == 'dual' and stored.get('ocr_schema_version') != 2):
        # La preferencia antigua no debe iniciar otro motor sin una elección nueva.
        save_preference(ocr_mode='kraken')
        return 'kraken'
    return value


def save_preference(device=None, ocr_mode=None):
    if device is not None and device not in VALID_DEVICES:
        raise ValueError("Elegí Automático, CPU o GPU NVIDIA.")
    if ocr_mode is not None and ocr_mode not in VALID_OCR_MODES:
        raise ValueError("Elegí un motor de transcripción válido.")
    path = _preference_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Mantener el formato histórico si todavía no se eligió un motor nuevo.
    existing = {"device": get_preference()}
    if path.exists():
        existing.update(json.loads(path.read_text(encoding="utf-8")))
    if device is not None:
        existing["device"] = device
    if ocr_mode is not None:
        existing["ocr_mode"] = ocr_mode
        existing["ocr_schema_version"] = 2
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            name = stream.name
            json.dump(existing, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def probe_workers():
    """Solo se anuncia GPU si un worker reciente verificó CUDA al arrancar."""
    result = {"cpu": {"available": False}, "cuda": {"available": False, "name": None}, "redis_ok": False}
    try:
        import redis
        from rq import Queue, Worker
        s = settings()
        conn = redis.Redis.from_url(s.REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
        conn.ping()
        result["redis_ok"] = True
        for kind, queue in (("cpu", s.RQ_QUEUE), ("cuda", os.environ.get("RQ_GPU_QUEUE", "servator-gpu"))):
            for worker in Worker.all(queue=Queue(queue, connection=conn)):
                beat = worker.last_heartbeat
                if not beat or (datetime.datetime.utcnow() - beat.replace(tzinfo=None)).total_seconds() > 120:
                    continue
                if worker.get_state() not in ("idle", "busy", "started"):
                    continue
                metadata = conn.hgetall(worker.key)
                if not metadata:
                    continue
                device = metadata.get(b"servator_device", b"").decode("utf-8", "replace")
                # Los workers CPU anteriores al cambio también son válidos para CPU.
                if kind == "cpu" and device in ("", "cpu"):
                    result["cpu"]["available"] = True
                if kind == "cuda" and device == "cuda" and metadata.get(b"servator_cuda_ready") == b"1":
                    result["cuda"] = {"available": True,
                                      "name": metadata.get(b"servator_gpu_name", b"").decode("utf-8", "replace") or "NVIDIA"}
                    break
    except Exception:
        # No afirmar disponibilidad de GPU si Redis o el worker no responden.
        pass
    return result


def processing_status():
    preferred = get_preference()
    devices = probe_workers()
    gpu_available = devices["cuda"]["available"]
    if preferred == "auto":
        effective = "cuda" if gpu_available else "cpu"
    elif preferred == "cuda" and not gpu_available:
        effective = None
    else:
        effective = preferred
    from app.services_paddle import paddle_status, automatic_device
    paddle = paddle_status()
    expected = automatic_device(paddle)
    paddle['expected_device'] = expected
    if paddle['ready'] and paddle['device'] != expected:
        paddle['ready'] = False
    return {"preferred": preferred, "effective": effective, "devices": devices,
            "ocr_mode": get_ocr_mode(), "paddle": paddle}


def resolve_device(requested=None):
    """La elección queda fijada para cada trabajo antes de ponerlo en cola."""
    selected = get_preference() if requested is None else requested
    if selected not in VALID_DEVICES:
        raise ValueError("Elegí Automático, CPU o GPU NVIDIA.")
    if selected == "cpu":
        return "cpu"
    devices = probe_workers()
    if selected == "cuda" and not devices["cuda"]["available"]:
        raise ValueError("La GPU no está disponible. Activá el componente GPU o elegí CPU en Configuración.")
    return "cuda" if devices["cuda"]["available"] else "cpu"
