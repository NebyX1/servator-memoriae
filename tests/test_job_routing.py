"""Device routing and the review image must match the user's choices."""
import io
from types import SimpleNamespace

from PIL import Image


def test_inference_routes_to_selected_worker(app, monkeypatch):
    from app.services_queue import queue_for_job
    monkeypatch.setenv("RQ_GPU_QUEUE", "custom-gpu")
    cuda = SimpleNamespace(DEVICE_MODE="cuda", RQ_QUEUE="cpu-jobs")
    cpu = SimpleNamespace(DEVICE_MODE="cpu", RQ_QUEUE="cpu-jobs")
    def job(kind, device="auto"):
        return SimpleNamespace(kind=kind, payload={"device": device})
    assert queue_for_job(job("transcribe"), cuda) == "custom-gpu"
    assert queue_for_job(job("prepare_model"), cuda) == "custom-gpu"
    assert queue_for_job(job("transcribe", "cpu"), cuda) == "cpu-jobs"
    assert queue_for_job(job("transcribe"), cpu) == "cpu-jobs"
    assert queue_for_job(job("transcribe", "cuda"), cpu) == "custom-gpu"
    assert queue_for_job(job("export"), cuda) == "cpu-jobs"


def test_full_resolution_image_and_optional_thumbnail(auth_client):
    doc = auth_client.post("/api/v1/documents", json={"title": "Imagen"}).get_json()["id"]
    image = io.BytesIO()
    Image.new("RGB", (800, 600), "white").save(image, "PNG")
    image.seek(0)
    result = auth_client.post(f"/api/v1/documents/{doc}/upload", data={"files": (image, "page.png")})
    assert result.get_json()["added"]
    page = auth_client.get(f"/api/v1/documents/{doc}").get_json()["pages"][0]["id"]
    full = auth_client.get(f"/api/v1/pages/{page}/image")
    thumb = auth_client.get(f"/api/v1/pages/{page}/image?thumbnail=1")
    assert Image.open(io.BytesIO(full.data)).size == (800, 600)
    assert Image.open(io.BytesIO(thumb.data)).size == (320, 240)


def test_new_transcription_after_adding_pages(auth_client, monkeypatch):
    from app.routes import jobs
    monkeypatch.setattr(jobs, "dispatch", lambda job: None)
    doc = auth_client.post("/api/v1/documents", json={"title": "Acta"}).get_json()["id"]
    def upload(color, filename):
        image = io.BytesIO()
        Image.new("RGB", (10, 10), color).save(image, "PNG")
        image.seek(0)
        auth_client.post(f"/api/v1/documents/{doc}/upload", data={"files": (image, filename)})
    upload("white", "1.png")
    first = auth_client.post("/api/v1/jobs/transcribe", json={"document_id": doc})
    upload("black", "2.png")
    second = auth_client.post("/api/v1/jobs/transcribe", json={"document_id": doc})
    assert first.status_code == second.status_code == 201
    assert first.get_json()["job_id"] != second.get_json()["job_id"]
    assert second.get_json()["total"] == 2


def test_collection_export_contains_every_document(app):
    import json
    import zipfile
    from app.extensions import db
    from app.models import Collection, Document
    from app.services_queue import new_job
    from app.services_storage import ObjectStorage
    from app.config import settings
    from app.tasks import _export
    with app.app_context():
        collection = Collection(title="Archivo")
        db.session.add(collection)
        db.session.flush()
        documents = [Document(title=title, collection_id=collection.id) for title in ("Uno", "Dos")]
        db.session.add_all(documents)
        db.session.commit()
        job = new_job("export", None, {"collection_id": collection.id, "format": "json"})
        _export(job)
        path = ObjectStorage(settings()).get_path(job.payload["result_key"])
        with zipfile.ZipFile(path) as archive:
            assert set(archive.namelist()) == {f"{doc.id}.json" for doc in documents}
            assert {json.loads(archive.read(name))["title"] for name in archive.namelist()} == {"Uno", "Dos"}
