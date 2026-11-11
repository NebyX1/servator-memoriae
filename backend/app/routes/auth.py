from flask import Blueprint, request, jsonify, g, current_app
from flask_login import login_user, logout_user, current_user, login_required
from app.extensions import db, limiter
from app.models import User
from app.utils_security import hash_password, verify_password

bp = Blueprint("auth", __name__)

@bp.get("/auth/me")
def me():
    if not current_user.is_authenticated:
        return jsonify({"user": None})
    return jsonify({"user": {"id": current_user.id, "email": current_user.email, "role": current_user.role,
                             "local_test_mode": current_app.config["LOCAL_TEST_MODE"]}})

@bp.post("/auth/login")
@limiter.limit("10 per minute")
def login():
    data = request.get_json(force=True, silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    pw = data.get("password") or ""
    u = User.query.filter_by(email=email).first()
    # anti-enumeración: hash dummy
    if not u or not verify_password(u.password_hash, pw):
        return jsonify({"error": "Credenciales inválidas", "request_id": g.request_id}), 401
    if not u.is_active:
        return jsonify({"error": "Usuario inactivo"}), 403
    login_user(u, remember=False)
    return jsonify({"user": {"id": u.id, "email": u.email, "role": u.role}})

@bp.post("/auth/logout")
@login_required
def logout():
    logout_user()
    return jsonify({"ok": True})

@bp.post("/auth/register_first")
def register_first():
    """Creación inicial de un solo uso: solo si no hay usuarios. Sin correo."""
    from app.local_test import LOCAL_TEST_USER_ID
    if User.query.filter(User.id != LOCAL_TEST_USER_ID).count() > 0:
        return jsonify({"error": "Ya existe un administrador"}), 403
    data = request.get_json(force=True, silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    pw = data.get("password") or ""
    if "@" not in email or len(pw) < 12:
        return jsonify({"error": "Email válido y contraseña de 12+ caracteres"}), 422
    u = User(email=email, password_hash=hash_password(pw), role="superadmin")
    db.session.add(u); db.session.commit()
    login_user(u)
    return jsonify({"user": {"id": u.id, "email": u.email, "role": u.role}})
