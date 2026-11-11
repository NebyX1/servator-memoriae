"""Partición por página sin mezcla + CER corpus = suma, no promedio."""
import random


def split_by_page(page_ids, seed=42):
    pages = sorted(set(page_ids))
    rnd = random.Random(seed)
    rnd.shuffle(pages)
    n = len(pages)
    n_test = max(1, n // 5)
    n_val = max(1, n // 5)
    return set(pages[:n_test]), set(pages[n_test:n_test + n_val]), set(pages[n_test + n_val:])


def test_split_sin_mezcla_y_reproducible():
    pages = [f"p{i}" for i in range(10)] * 3  # líneas repetidas por página
    te, va, tr = split_by_page(pages, seed=42)
    assert not (te & va) and not (te & tr) and not (va & tr)
    assert te | va | tr == set(pages)
    assert split_by_page(pages, seed=42) == (te, va, tr)
    assert len(te) == 2 and len(va) == 2 and len(tr) == 6


def test_corpus_cer_suma_no_promedio():
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))
    import kraken_adapter as ka
    pairs = [("hola", "hola"), ("adiós", "adios")]  # 0 + 1 edits
    res = ka.corpus_cer(pairs)
    assert res["edits"] == 1 and res["chars"] == 9
    assert abs(res["cer"] - 1 / 9) < 1e-9
    naive_mean = (ka.cer("hola", "hola") + ka.cer("adiós", "adios")) / 2
    assert abs(naive_mean - res["cer"]) > 1e-9  # el promedio simple difiere


def test_training_run_rechaza_pocos_ejemplos(auth_client, app):
    with app.app_context():
        from app.extensions import db
        from app.models import Document, Page, Line
        doc = Document(title="D")
        db.session.add(doc)
        db.session.flush()
        pg = Page(document_id=doc.id, order_index=0, status="done")
        db.session.add(pg)
        db.session.flush()
        db.session.add(Line(page_id=pg.id, order_index=0, auto_text="x",
                            revised_text="x", state="confirmed"))
        db.session.commit()
        pid = pg.id
    r = auth_client.post("/api/v1/training/runs", json={"page_ids": [pid]})
    assert r.status_code == 422
    assert "líneas" in r.get_json()["error"] or "lines" in r.get_json()


def test_ejemplos_solo_cuenta_textos_revisados(auth_client, app):
    with app.app_context():
        from app.extensions import db
        from app.models import Document, Page, Line
        doc = Document(title="Manuscrito")
        db.session.add(doc); db.session.flush()
        page = Page(document_id=doc.id, order_index=0)
        db.session.add(page); db.session.flush()
        db.session.add_all([
            Line(page_id=page.id, auto_text="original", state="confirmed"),
            Line(page_id=page.id, auto_text="original", revised_text="corregido", state="corrected"),
            Line(page_id=page.id, auto_text="sin revisar", state="auto"),
            Line(page_id=page.id, auto_text="original", revised_text="", state="corrected"),
        ])
        db.session.commit()
        doc_id = doc.id
    response = auth_client.get('/api/v1/training/examples')
    assert response.status_code == 200
    body = response.get_json()
    assert body['training_available'] is False
    item = next(item for item in body['items'] if item['id'] == doc_id)
    assert (item['pages'], item['reviewed_pages'], item['lines']) == (1, 1, 2)


def test_entrenamiento_no_promete_modelos_no_verificados(auth_client, app):
    with app.app_context():
        from app.extensions import db
        from app.models import Document, Page, Line
        doc = Document(title="D")
        db.session.add(doc); db.session.flush()
        page = Page(document_id=doc.id, order_index=0)
        db.session.add(page); db.session.flush()
        db.session.add_all([Line(page_id=page.id, auto_text=f"texto {i}", state="confirmed") for i in range(10)])
        db.session.commit()
        page_id = page.id
    response = auth_client.post('/api/v1/training/runs', json={'page_ids': [page_id]})
    assert response.status_code == 503
    assert 'no está disponible' in response.get_json()['error']


def test_trabajo_antiguo_de_entrenamiento_falla_sin_modelo_falso(app):
    import pytest
    with app.app_context():
        from app.extensions import db
        from app.models import Job, TrainingRun, ModelVersion
        from app.tasks import _train
        run = TrainingRun(name="Anterior", status="QUEUED")
        db.session.add(run); db.session.flush()
        job = Job(kind="train", payload={"training_run_id": run.id})
        db.session.add(job); db.session.commit()
        with pytest.raises(ValueError, match="no está disponible"):
            _train(job)
        assert run.status == "FAILED"
        assert ModelVersion.query.count() == 0
