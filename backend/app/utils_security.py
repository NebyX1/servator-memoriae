from argon2 import PasswordHasher
from functools import wraps
from flask import abort, g, request
from flask_login import current_user

_ph = PasswordHasher()

CAPABILITIES = {
    "viewer": {"read"},
    "reviewer": {"read", "review"},
    "analyst": {"read", "review", "upload", "transcribe", "export"},
    "admin": {"read", "review", "upload", "transcribe", "export", "train", "activate_model", "admin"},
    "superadmin": {"read", "review", "upload", "transcribe", "export", "train", "activate_model", "admin"},
}

def hash_password(pw: str) -> str:
    return _ph.hash(pw)

def verify_password(h: str, pw: str) -> bool:
    try:
        return _ph.verify(h, pw)
    except Exception:
        return False

def require(cap: str):
    def deco(fn):
        @wraps(fn)
        def inner(*a, **kw):
            if not current_user.is_authenticated:
                abort(401, description="No autenticado")
            role = getattr(current_user, "role", "viewer")
            if cap not in CAPABILITIES.get(role, set()):
                abort(403, description="Sin permiso")
            return fn(*a, **kw)
        return inner
    return deco

def audit(action, entity_id="", details=None):
    from app.extensions import db
    from app.models import AuditLog
    try:
        uid = current_user.get_id() if current_user.is_authenticated else None
        db.session.add(AuditLog(user_id=uid, action=action, entity_id=entity_id, details=details or {}))
        db.session.commit()
    except Exception:
        db.session.rollback()
