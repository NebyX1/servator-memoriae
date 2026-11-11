"""Fixture Flask con SQLite temporal para tests."""
import os
import tempfile
import pytest

os.environ.setdefault("FLASK_ENV", "testing")


@pytest.fixture()
def app():
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "test.db")
    data_dir = os.path.join(tmp, "data")
    os.makedirs(data_dir, exist_ok=True)
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["DATA_DIR"] = data_dir
    os.environ["MODEL_DIR"] = os.path.join(tmp, "models")
    os.environ["S3_USE_LOCAL"] = "1"

    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from app import create_app
    from app.extensions import db

    application = create_app(overrides={
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
    })
    application.config["DATA_DIR_TMP"] = tmp
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def make_user(email="admin@local.test", password="una-clave-larga-1234", role="superadmin"):
    from app.extensions import db
    from app.models import User
    from app.utils_security import hash_password
    u = User(email=email, password_hash=hash_password(password), role=role)
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture()
def auth_client(client):
    make_user()
    client.post("/api/v1/auth/login", json={"email": "admin@local.test", "password": "una-clave-larga-1234"})
    return client
