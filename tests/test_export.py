"""Export JSON, PDF y Word con texto revisado y caracteres Unicode."""
import io
import json


def _seed_doc(app, n_pages=2, n_lines=3):
    from app.extensions import db
    from app.models import Document, Page, Line
    with app.app_context():
        doc = Document(title="Acta Ñandú 1883", signature="LAV-1")
        db.session.add(doc)
        db.session.flush()
        for p in range(n_pages):
            pg = Page(document_id=doc.id, order_index=p, folio=f"{p+1}r",
                      width=800, height=1000, status="done")
            db.session.add(pg)
            db.session.flush()
            for i in range(n_lines):
                db.session.add(Line(page_id=pg.id, order_index=i,
                                    baseline=[[10, 20 + i * 30], [700, 20 + i * 30]],
                                    polygon=[[10, 10 + i * 30], [700, 10 + i * 30],
                                             [700, 35 + i * 30], [10, 35 + i * 30]],
                                    auto_text=f"año {i} niño",
                                    revised_text=f"año {i} niña" if i == 0 else None,
                                    confidence=0.9, state="confirmed" if i == 0 else "auto"))
        db.session.commit()
        return doc.id


def _build_export_json(app, doc_id, text_source="revised_fallback_auto"):
    from app.models import Document, Page, Line
    with app.app_context():
        d = Document.query.get(doc_id)
        pages = Page.query.filter_by(document_id=doc_id).order_by(Page.order_index).all()
        out = {"document": {"id": d.id, "title": d.title, "signature": d.signature,
                            "doc_type": d.doc_type, "year_start": d.year_start,
                            "year_end": d.year_end, "description": d.description,
                            "tags": d.tags or []},
               "engine": {"name": "kraken", "version": "kraken==7.1.1",
                          "recognizer": "ppocrv6-medium", "model_version": "v1",
                          "segmenter": "kraken baseline segmenter (kraken.segmentation, blla model bundled)"},
               "pages": []}
        for pg in pages:
            lines = Line.query.filter_by(page_id=pg.id).order_by(Line.order_index).all()
            out["pages"].append({
                "id": pg.id, "order": pg.order_index, "folio": pg.folio,
                "width": pg.width, "height": pg.height, "status": pg.status,
                "lines": [{"order": l.order_index, "baseline": l.baseline, "polygon": l.polygon,
                           "auto_text": l.auto_text, "revised_text": l.revised_text,
                           "text": (l.revised_text if (l.revised_text is not None and text_source.startswith("revised")) else (l.auto_text or "")),
                           "confidence": l.confidence, "state": l.state, "note": l.note or ""} for l in lines]})
        return out


def test_json_esquema_y_fallback(auth_client, app):
    doc_id = _seed_doc(app)
    payload = _build_export_json(app, doc_id)
    assert payload["engine"]["version"] == "kraken==7.1.1"
    assert len(payload["pages"]) == 2
    l0 = payload["pages"][0]["lines"][0]
    assert l0["text"] == "año 0 niña"  # revised gana
    l1 = payload["pages"][0]["lines"][1]
    assert l1["text"] == "año 1 niño"  # fallback auto
    assert [l["order"] for l in payload["pages"][0]["lines"]] == [0, 1, 2]
    json.dumps(payload, ensure_ascii=False)  # serializable con ñ


def test_pdf_lectura_con_enie(auth_client, app, tmp_path):
    pytest = __import__("pytest")
    pytest.importorskip("reportlab")
    doc_id = _seed_doc(app)
    out = str(tmp_path / "lectura.pdf")
    with app.app_context():
        from app.services_export_pdf import build_pdf
        res = build_pdf(doc_id, out, mode="pdf-lectura")
    assert res["pages"] == 2
    with open(out, "rb") as f:
        head = f.read(5)
    assert head == b"%PDF-"


def test_pdf_facsimil_geometria(auth_client, app, tmp_path):
    pytest = __import__("pytest")
    pytest.importorskip("pypdfium2")
    pytest.importorskip("reportlab")
    from PIL import Image
    doc_id = _seed_doc(app)
    img_path = str(tmp_path / "pg.png")
    Image.new("RGB", (800, 1000), "white").save(img_path)
    with app.app_context():
        from app.models import Page
        from app.services_storage import ObjectStorage
        from app.config import settings
        st = ObjectStorage(settings())
        for pg in Page.query.filter_by(document_id=doc_id).all():
            pg.image_key = "pages/test.png"
        from app.extensions import db
        db.session.commit()
        st.put_file("pages/test.png", img_path)
        from app.services_export_pdf import build_pdf
        out = str(tmp_path / "fac.pdf")
        res = build_pdf(doc_id, out, mode="pdf-facsimil", storage=st)
    assert res["pages"] == 2
    with open(out, "rb") as f:
        assert f.read(5) == b"%PDF-"


def test_word_conserva_paginas_texto_revisado_y_marcas(app, tmp_path):
    from docx import Document as WordDocument
    from app.extensions import db
    from app.models import Line, Page
    from app.services_export_docx import build_docx

    doc_id = _seed_doc(app)
    output = tmp_path / "transcripcion.docx"
    with app.app_context():
        first_page = Page.query.filter_by(document_id=doc_id, order_index=0).one()
        first_line = Line.query.filter_by(page_id=first_page.id, order_index=0).one()
        first_line.revised_text = "año \x00 niña & <época>"
        second_line = Line.query.filter_by(page_id=first_page.id, order_index=1).one()
        second_line.state = "bad_cut"
        db.session.commit()
        summary = build_docx(doc_id, str(output))

    word = WordDocument(output)
    paragraphs = [p.text for p in word.paragraphs]
    assert paragraphs[0] == "Acta Ñandú 1883"
    assert "Signatura: LAV-1" in paragraphs
    assert "Página 1 · folio 1r" in paragraphs
    assert "Página 2 · folio 2r" in paragraphs
    assert "año � niña & <época>" in paragraphs
    assert "año 1 niño [pendiente de revisión]" in paragraphs
    assert paragraphs.index("Página 1 · folio 1r") < paragraphs.index("año 2 niño") < paragraphs.index("Página 2 · folio 2r")
    assert len(word.element.body.xpath('.//w:br[@w:type="page"]')) == 1
    assert summary == {"mode": "docx", "pages": 2, "pending": 1}


def test_word_puede_exportar_texto_automatico_y_paginas_vacias(app, tmp_path):
    from docx import Document as WordDocument
    from app.extensions import db
    from app.models import Page
    from app.services_export_docx import build_docx

    doc_id = _seed_doc(app, n_pages=1, n_lines=1)
    output = tmp_path / "automatico.docx"
    with app.app_context():
        db.session.add(Page(document_id=doc_id, order_index=1, status="imported"))
        db.session.commit()
        summary = build_docx(doc_id, str(output), text_source="auto")
    text = '\n'.join(p.text for p in WordDocument(output).paragraphs)
    assert "año 0 niño" in text
    assert "año 0 niña" not in text
    assert "[Sin transcripción; pendiente de revisión]" in text
    assert summary["pending"] == 1


def test_word_solicitar_y_descargar_por_api(auth_client, app, monkeypatch):
    from docx import Document as WordDocument
    from app.extensions import db
    from app.models import Job
    from app.tasks import _export

    doc_id = _seed_doc(app, n_pages=1, n_lines=2)
    monkeypatch.setattr("app.routes.exports.dispatch", lambda job: None)
    response = auth_client.post("/api/v1/exports", json={"document_id": doc_id, "format": "docx"})
    assert response.status_code == 201
    job_id = response.get_json()["job_id"]
    with app.app_context():
        job = db.session.get(Job, job_id)
        _export(job)
        job.status = "COMPLETED"
        db.session.commit()
    # Las imágenes Linux mínimas pueden no registrar .docx en /etc/mime.types.
    import mimetypes
    monkeypatch.setattr(mimetypes, "guess_type", lambda *args, **kwargs: (None, None))
    downloaded = auth_client.get(f"/api/v1/exports/{job_id}/download")
    assert downloaded.status_code == 200
    assert downloaded.mimetype == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert ".docx" in downloaded.headers["Content-Disposition"]
    word = WordDocument(io.BytesIO(downloaded.data))
    assert "año 0 niña" in [paragraph.text for paragraph in word.paragraphs]


def test_coleccion_word_contiene_todos_los_documentos(app):
    import zipfile
    from docx import Document as WordDocument
    from app.config import settings
    from app.extensions import db
    from app.models import Collection, Document
    from app.services_queue import new_job
    from app.services_storage import ObjectStorage
    from app.tasks import _export

    with app.app_context():
        collection = Collection(title="Archivo")
        db.session.add(collection)
        db.session.flush()
        documents = [Document(title=title, collection_id=collection.id) for title in ("Primero", "Segundo")]
        db.session.add_all(documents)
        db.session.commit()
        job = new_job("export", None, {"collection_id": collection.id, "format": "docx"})
        _export(job)
        path = ObjectStorage(settings()).get_path(job.payload["result_key"])
        with zipfile.ZipFile(path) as archive:
            assert set(archive.namelist()) == {f"{doc.id}.docx" for doc in documents}
            titles = {WordDocument(io.BytesIO(archive.read(name))).paragraphs[0].text for name in archive.namelist()}
            assert titles == {"Primero", "Segundo"}
