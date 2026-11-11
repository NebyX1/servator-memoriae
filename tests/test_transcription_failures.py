"""Regresiones del estado de trabajos de transcripción."""
import sys
import types
import pytest


def test_transcripcion_informa_fallos_sin_perder_paginas_exitosas(app, monkeypatch):
    from app.extensions import db
    from app.models import Document, Job, Page, Line
    from app.tasks import _transcribe

    with app.app_context():
        document = Document(title="Ejemplo")
        db.session.add(document)
        db.session.flush()
        good = Page(document_id=document.id, order_index=0, image_key="good.png", status="imported")
        bad = Page(document_id=document.id, order_index=1, image_key="bad.png", status="imported")
        db.session.add_all([good, bad]); db.session.flush()
        job = Job(kind="transcribe", status="RUNNING", payload={"page_ids": [good.id, bad.id], "device": "cpu"})
        db.session.add(job); db.session.commit()

        def transcribe(path, **kwargs):
            if path.endswith("bad.png"):
                raise RuntimeError("fallo de lectura")
            return [{"order": 0, "text": "Texto leído", "baseline": [], "polygon": [], "confidence": 0.9}]
        monkeypatch.setitem(sys.modules, "kraken_adapter", types.SimpleNamespace(transcribe_image=transcribe, ENGINE_VERSION="test"))

        with pytest.raises(ValueError, match="No se pudieron transcribir 1 página"):
            _transcribe(job)
        assert Page.query.get(good.id).status == "done"
        assert Page.query.get(bad.id).status == "failed"
        assert Line.query.filter_by(page_id=good.id).one().auto_text == "Texto leído"
