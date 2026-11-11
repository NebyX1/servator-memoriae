"""La instalación local funciona sin login, con CSRF y con salida segura a producción."""
import io
import sys
from pathlib import Path

import pytest
from PIL import Image


@pytest.fixture()
def local_app(tmp_path, monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setenv("LOCAL_TEST_MODE", "1")
    monkeypatch.setenv("FRONT_BIND", "127.0.0.1")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'local.db').as_posix()}")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LOCAL_STORAGE_DIR", str(tmp_path / "objects"))
    monkeypatch.setenv("MODEL_DIR", str(tmp_path / "models"))
    monkeypatch.setenv("S3_USE_LOCAL", "1")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    from app import create_app
    from app.extensions import db

    application = create_app(overrides={"TESTING": True, "WTF_CSRF_ENABLED": True})
    with application.app_context():
        db.create_all()
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


def test_local_mode_creates_and_uploads_without_login(local_app):
    client = local_app.test_client()
    current = client.get("/api/v1/auth/me").get_json()["user"]
    assert current["local_test_mode"] is True
    assert current["role"] == "superadmin"
    with client.session_transaction() as session:
        assert "_user_id" not in session  # La identidad local no crea una sesión persistente.
    assert client.post("/api/v1/documents", json={"title": "sin token"}).status_code == 400
    token = client.get("/api/v1/auth/csrf").get_json()["csrfToken"]
    headers = {"X-CSRFToken": token}
    created = client.post("/api/v1/documents", json={"title": "Prueba local"}, headers=headers)
    assert created.status_code == 201
    image = io.BytesIO()
    Image.new("RGB", (100, 50), "white").save(image, format="PNG")
    image.seek(0)
    uploaded = client.post(f"/api/v1/documents/{created.get_json()['id']}/upload",
                           data={"file": (image, "pagina.png")}, headers=headers)
    assert uploaded.status_code == 200
    assert len(uploaded.get_json()["added"]) == 1
    assert not uploaded.get_json()["errors"]


def test_local_mode_overrides_old_cookie_but_not_production(local_app):
    from app.local_test import LOCAL_TEST_USER_ID

    client = local_app.test_client()
    # La cookie anterior puede representar una sesión caducada o de otro rol.
    with client.session_transaction() as session:
        session["_user_id"] = "usuario-anterior"
        session["_fresh"] = True
    assert client.get("/api/v1/auth/me").get_json()["user"]["id"] == LOCAL_TEST_USER_ID

    local_app.config["LOCAL_TEST_MODE"] = False
    assert client.get("/api/v1/auth/me").get_json()["user"] is None
    assert client.get("/api/v1/documents").status_code == 401
    # Aunque alguien conservara una cookie de esta identidad, no sirve fuera del modo local.
    with client.session_transaction() as session:
        session["_user_id"] = LOCAL_TEST_USER_ID
        session["_fresh"] = True
    assert client.get("/api/v1/auth/me").get_json()["user"] is None


def test_local_identity_does_not_block_first_real_admin(local_app):
    client = local_app.test_client()
    assert client.get("/api/v1/auth/me").get_json()["user"]["local_test_mode"] is True
    local_app.config["LOCAL_TEST_MODE"] = False
    token = client.get("/api/v1/auth/csrf").get_json()["csrfToken"]
    response = client.post("/api/v1/auth/register_first",
                           json={"email": "responsable@example.test", "password": "una-clave-larga-123"},
                           headers={"X-CSRFToken": token})
    assert response.status_code == 200
    assert response.get_json()["user"]["role"] == "superadmin"


def test_local_mode_is_rejected_for_production_or_nonlocal_binding(monkeypatch):
    from app.config import settings

    monkeypatch.setenv("LOCAL_TEST_MODE", "1")
    monkeypatch.setenv("FLASK_ENV", "production")
    with pytest.raises(RuntimeError, match="FLASK_ENV"):
        settings()
    monkeypatch.setenv("FLASK_ENV", "development")
    monkeypatch.setenv("FRONT_BIND", "0.0.0.0")
    with pytest.raises(RuntimeError, match="FRONT_BIND"):
        settings()
