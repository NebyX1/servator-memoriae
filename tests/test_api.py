"""API: auth, colecciones, documentos, concurrencia líneas (409)."""
from tests.conftest import make_user


def test_register_first_solo_un_uso(client):
    r = client.post("/api/v1/auth/register_first",
                    json={"email": "a@b.cd", "password": "clave-larga-1234"})
    assert r.status_code == 200
    r2 = client.post("/api/v1/auth/register_first",
                     json={"email": "x@y.zz", "password": "otra-clave-larga-1"})
    assert r2.status_code == 403


def test_login_y_me(auth_client):
    r = auth_client.get("/api/v1/auth/me").get_json()
    assert r["user"]["email"] == "admin@local.test"


def test_viewer_no_puede_subir(client, app):
    with app.app_context():
        make_user(email="v@v.vv", password="clave-larga-1234", role="viewer")
    client.post("/api/v1/auth/login", json={"email": "v@v.vv", "password": "clave-larga-1234"})
    r = client.post("/api/v1/collections", json={"title": "X"})
    assert r.status_code == 403


def test_colecciones_documentos_crud(auth_client):
    c = auth_client.post("/api/v1/collections", json={"title": "Lavalleja"}).get_json()
    d = auth_client.post("/api/v1/documents",
                         json={"title": "Acta 1", "collection_id": c["id"],
                               "doc_type": "libro", "year_start": 1883, "signature": "LAV-1",
                               "tags": ["a", "b"]})
    assert d.status_code == 201
    doc_id = d.get_json()["id"]
    got = auth_client.get(f"/api/v1/documents/{doc_id}").get_json()
    assert got["signature"] == "LAV-1" and got["pages"] == []


def test_concurrencia_linea_409(auth_client, app):
    with app.app_context():
        from app.extensions import db
        from app.models import Document, Page, Line
        doc = Document(title="D")
        db.session.add(doc)
        db.session.flush()
        pg = Page(document_id=doc.id, order_index=0, width=100, height=100, status="done")
        db.session.add(pg)
        db.session.flush()
        ln = Line(page_id=pg.id, order_index=0, auto_text="hola", version=1)
        db.session.add(ln)
        db.session.commit()
        lid, pid = ln.id, pg.id
    # versión vieja -> 409
    auth_client.patch(f"/api/v1/lines/{lid}", json={"revised_text": "A", "version": 1})
    r = auth_client.patch(f"/api/v1/lines/{lid}", json={"revised_text": "B", "version": 1})
    assert r.status_code == 409
    assert "combiná" in r.get_json()["error"]
    items = auth_client.get(f"/api/v1/pages/{pid}/lines").get_json()["items"]
    assert items[0]["revised_text"] == "A"
