"""La preferencia elegida debe llegar al worker apropiado y no fingir GPU."""
import datetime
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest
from tests.conftest import make_user


def worker_status(gpu=False):
    return {"cpu": {"available": True}, "cuda": {"available": gpu, "name": "NVIDIA de prueba" if gpu else None}, "redis_ok": True}


def mock_workers(monkeypatch, available):
    monkeypatch.setattr("app.services_device.probe_workers", lambda: worker_status(available))
    monkeypatch.setattr("app.routes.settings.probe_workers", lambda: worker_status(available))


def test_settings_persist_and_reject_unavailable_gpu(auth_client, app, monkeypatch):
    from app.services_device import _preference_path
    monkeypatch.setenv("DEVICE_MODE", "cpu")
    mock_workers(monkeypatch, False)
    status = auth_client.get("/api/v1/settings/processing")
    assert status.status_code == 200
    assert status.get_json()["preferred"] == "cpu"
    assert status.get_json()["effective"] == "cpu"
    assert auth_client.put("/api/v1/settings/processing", json={"device": "auto"}).status_code == 200
    assert json.loads(_preference_path().read_text(encoding="utf-8")) == {"device": "auto"}
    rejected = auth_client.put("/api/v1/settings/processing", json={"device": "cuda"})
    assert rejected.status_code == 409
    assert auth_client.get("/api/v1/settings/processing").get_json()["preferred"] == "auto"
    assert auth_client.put("/api/v1/settings/processing", json={"device": "tpu"}).status_code == 422


def test_selected_gpu_routes_new_jobs_and_reports_when_it_disappears(auth_client, app, monkeypatch):
    from app.extensions import db
    from app.models import Document, Page
    from app.services_queue import queue_for_job
    monkeypatch.setenv("DEVICE_MODE", "cpu")
    mock_workers(monkeypatch, True)
    captured = []
    monkeypatch.setattr("app.routes.jobs.dispatch", lambda job: captured.append(dict(job.payload)))
    saved = auth_client.put("/api/v1/settings/processing", json={"device": "cuda"})
    assert saved.status_code == 200
    assert saved.get_json()["effective"] == "cuda"
    with app.app_context():
        doc = Document(title="Página de prueba")
        db.session.add(doc); db.session.flush()
        db.session.add(Page(document_id=doc.id, order_index=0, status="imported")); db.session.commit()
        doc_id = doc.id
    created = auth_client.post("/api/v1/jobs/transcribe", json={"document_id": doc_id})
    assert created.status_code == 201
    assert created.get_json()["device"] == "cuda"
    assert captured[-1]["device"] == "cuda"
    job = SimpleNamespace(kind="transcribe", payload=captured[-1])
    assert queue_for_job(job, SimpleNamespace(DEVICE_MODE="cpu", RQ_QUEUE="servator")) == "servator-gpu"
    explicit_cpu = auth_client.post("/api/v1/jobs/transcribe", json={"document_id": doc_id, "device": "cpu"})
    assert explicit_cpu.get_json()["device"] == "cpu"
    mock_workers(monkeypatch, False)
    assert auth_client.get("/api/v1/settings/processing").get_json()["effective"] is None
    unavailable = auth_client.post("/api/v1/jobs/transcribe", json={"document_id": doc_id})
    assert unavailable.status_code == 409
    assert "GPU" in unavailable.get_json()["error"]


def test_automatic_chooses_gpu_only_when_available(auth_client, monkeypatch):
    from app.services_device import resolve_device, save_preference
    save_preference("auto")
    mock_workers(monkeypatch, True)
    assert resolve_device() == "cuda"
    mock_workers(monkeypatch, False)
    assert resolve_device() == "cpu"


def test_only_administrators_change_preference(app, client, monkeypatch):
    mock_workers(monkeypatch, False)
    make_user(role="viewer")
    login = client.post("/api/v1/auth/login", json={"email": "admin@local.test", "password": "una-clave-larga-1234"})
    assert login.status_code == 200
    assert client.get("/api/v1/settings/processing").status_code == 200
    assert client.put("/api/v1/settings/processing", json={"device": "cpu"}).status_code == 403


def test_gpu_is_reported_only_after_worker_verification(monkeypatch):
    from app.services_device import probe_workers
    now = datetime.datetime.utcnow()
    cpu = SimpleNamespace(key=b"cpu", last_heartbeat=now, get_state=lambda: "idle")
    gpu = SimpleNamespace(key=b"gpu", last_heartbeat=now, get_state=lambda: "busy")
    metadata = {b"cpu": {b"servator_device": b"cpu"},
                b"gpu": {b"servator_device": b"cuda", b"servator_cuda_ready": b"1", b"servator_gpu_name": b"RTX prueba"}}

    class Connection:
        def ping(self): return True
        def hgetall(self, key): return metadata[key]

    conn = Connection()
    class Queue:
        def __init__(self, name, connection): self.name = name
    class Worker:
        @staticmethod
        def all(queue): return [cpu] if queue.name == "servator" else [gpu]
    monkeypatch.setitem(sys.modules, "redis", SimpleNamespace(Redis=SimpleNamespace(from_url=lambda *args, **kwargs: conn)))
    monkeypatch.setitem(sys.modules, "rq", SimpleNamespace(Queue=Queue, Worker=Worker))
    monkeypatch.setenv("RQ_QUEUE", "servator")
    monkeypatch.setenv("RQ_GPU_QUEUE", "servator-gpu")
    assert probe_workers()["cuda"] == {"available": True, "name": "RTX prueba"}
    del metadata[b"gpu"][b"servator_cuda_ready"]
    assert probe_workers()["cuda"]["available"] is False
    metadata[b"gpu"][b"servator_cuda_ready"] = b"1"
    gpu.last_heartbeat = now - datetime.timedelta(minutes=5)
    assert probe_workers()["cuda"]["available"] is False


def test_gpu_worker_checks_cuda_before_advertising_it(monkeypatch):
    from worker.run import device_metadata
    monkeypatch.setenv("DEVICE_MODE", "cuda")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout='{"name":"RTX prueba","cuda":"13.0"}\n'))
    metadata = device_metadata()
    assert metadata["servator_device"] == "cuda"
    assert metadata["servator_cuda_ready"] == "1"
    assert metadata["servator_gpu_name"] == "RTX prueba"

    def failure(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "CUDA")
    monkeypatch.setattr(subprocess, "run", failure)
    with pytest.raises(RuntimeError, match="GPU NVIDIA"):
        device_metadata()
