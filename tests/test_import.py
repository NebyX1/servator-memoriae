"""Import: TIFF/PDF multipágina, duplicados, archivos dañados (sin mocks de subida)."""
import io
import hashlib
from PIL import Image


def _png(text="acta 1883"):
    from PIL import ImageDraw
    im = Image.new("RGB", (400, 200), "white")
    ImageDraw.Draw(im).text((20, 80), text, fill="black")
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _tiff_multipage(n=3):
    frames = []
    for i in range(n):
        im = Image.new("RGB", (300, 200), "white")
        frames.append(im)
    buf = io.BytesIO()
    frames[0].save(buf, format="TIFF", save_all=True, append_images=frames[1:])
    return buf.getvalue()


def _pdf_bytes():
    pytest = __import__("pytest")
    pdfium = pytest.importorskip("pypdfium2")
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(100, 700, "Lavalleja 1883")
    c.showPage()
    c.drawString(100, 700, "página dos")
    c.showPage()
    c.save()
    return buf.getvalue()


def _mk_doc(c):
    col = c.post("/api/v1/collections", json={"title": "Fondo"}).get_json()
    doc = c.post("/api/v1/documents", json={"title": "Acta", "collection_id": col["id"]}).get_json()
    return doc["id"] if "id" in doc else doc["doc_id"] if "doc_id" in doc else list(doc.values())[0]


def test_tiff_multipage_y_duplicado(auth_client):
    doc_id = _mk_doc(auth_client)
    tiff = _tiff_multipage(3)
    r1 = auth_client.post(f"/api/v1/documents/{doc_id}/upload",
                          data={"files": (io.BytesIO(tiff), "acta-001.tif")},
                          content_type="multipart/form-data").get_json()
    assert len(r1["added"]) == 1 and r1["added"][0]["pages"] == 3, r1
    r2 = auth_client.post(f"/api/v1/documents/{doc_id}/upload",
                          data={"files": (io.BytesIO(tiff), "acta-001.tif")},
                          content_type="multipart/form-data").get_json()
    assert r2["duplicates"] and not r2["added"], r2
    got = auth_client.get(f"/api/v1/documents/{doc_id}").get_json()
    assert len(got["pages"]) == 3


def test_pdf_multipage(auth_client):
    doc_id = _mk_doc(auth_client)
    pdf = _pdf_bytes()
    r = auth_client.post(f"/api/v1/documents/{doc_id}/upload",
                         data={"files": (io.BytesIO(pdf), "legajo.pdf")},
                         content_type="multipart/form-data").get_json()
    assert r["added"] and r["added"][0]["pages"] == 2, r


def test_danado_no_rompe_lote(auth_client):
    doc_id = _mk_doc(auth_client)
    bueno = _png()
    r = auth_client.post(
        f"/api/v1/documents/{doc_id}/upload",
        data={"files": [(io.BytesIO(bueno), "buena.png"), (io.BytesIO(b"esto no es imagen"), "rota.png")]},
        content_type="multipart/form-data").get_json()
    assert len(r["added"]) == 1, r
    assert len(r["errors"]) == 1 and "admiten" in r["errors"][0]["error"], r


def test_orden_natural(auth_client):
    from app.routes.documents import _natural_key
    names = ["acta-10.png", "acta-2.png", "acta-1.png"]
    assert sorted(names, key=_natural_key) == ["acta-1.png", "acta-2.png", "acta-10.png"]


def test_error_durante_importacion_permite_reintentar_archivo_completo(auth_client, monkeypatch):
    from app.services_storage import ObjectStorage
    doc_id = _mk_doc(auth_client)
    contents = _tiff_multipage(3)
    put_file = ObjectStorage.put_file
    page_count = 0

    def falla_una_pagina(self, key, source):
        nonlocal page_count
        if key.startswith("pages/"):
            page_count += 1
            if page_count == 2:
                raise OSError("fallo al guardar")
        return put_file(self, key, source)

    monkeypatch.setattr(ObjectStorage, "put_file", falla_una_pagina)
    first = auth_client.post(f"/api/v1/documents/{doc_id}/upload",
                             data={"file": (io.BytesIO(contents), "legajo.tif")},
                             content_type="multipart/form-data").get_json()
    assert first["errors"] and not first["added"]
    assert auth_client.get(f"/api/v1/documents/{doc_id}").get_json()["pages"] == []
    second = auth_client.post(f"/api/v1/documents/{doc_id}/upload",
                              data={"file": (io.BytesIO(contents), "legajo.tif")},
                              content_type="multipart/form-data").get_json()
    assert not second["duplicates"] and second["added"][0]["pages"] == 3
    assert len(auth_client.get(f"/api/v1/documents/{doc_id}").get_json()["pages"]) == 3
