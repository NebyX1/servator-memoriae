"""Isolated API for browser regression tests; never uses the user's database."""
import os
import sys
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
root = Path(os.environ["SERVATOR_E2E_DIR"]).resolve()
os.environ.update({
    "FLASK_ENV": "testing",
    "LOCAL_TEST_MODE": os.environ.get("SERVATOR_E2E_LOCAL_MODE", "0"),
    "FRONT_BIND": "127.0.0.1",
    "DATABASE_URL": "sqlite:///" + (root / "test.db").as_posix(),
    "DATA_DIR": str(root / "data"),
    "LOCAL_STORAGE_DIR": str(root / "objects"),
    "MODEL_DIR": str(root / "models"),
    "S3_USE_LOCAL": "1",
    "REDIS_URL": "redis://127.0.0.1:1/0",
    "PADDLE_URL": "http://127.0.0.1:1",
    "DEVICE_MODE": "cpu",
    "SECRET_KEY": "browser-regression-only-secret-0000000000000000",
})
sys.path.insert(0, str(repo / "backend"))
from app import create_app
from app.extensions import db
from app.models import User
from app.utils_security import hash_password

app = create_app()

@app.get("/__e2e_ready")
def test_readiness():
    return os.environ["SERVATOR_E2E_NONCE"]

with app.app_context():
    db.create_all()
    db.session.add(User(email="prueba@example.com", password_hash=hash_password("clave-de-prueba-123"), role="superadmin"))
    db.session.commit()
app.run(host="127.0.0.1", port=18547, use_reloader=False)
