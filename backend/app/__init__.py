"""Servator Memoriae Flask app factory."""
import os, uuid
from flask import Flask, jsonify, g, request, current_app
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_cors import CORS

from app.extensions import db, login_manager, csrf, migrate, limiter
from app.config import settings

def create_app(config_name=None, overrides=None):
    s = settings()
    app = Flask(__name__)
    app.config["SECRET_KEY"] = s.SECRET_KEY
    app.config["LOCAL_TEST_MODE"] = s.LOCAL_TEST_MODE
    app.config["SQLALCHEMY_DATABASE_URI"] = s.DATABASE_URL
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["MAX_CONTENT_LENGTH"] = s.MAX_UPLOAD_MB * 1024 * 1024
    if overrides:
        app.config.update(overrides)

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
    CORS(app, resources={r"/api/*": {"origins": s.CORS_ORIGINS.split(","), "supports_credentials": True}})

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    # importar modelos para metadata
    import importlib as _il
    _il.import_module("app.models")  # noqa

    from app.models import User

    @login_manager.user_loader
    def load_user(uid):
        from app.local_test import LOCAL_TEST_USER_ID, local_test_user
        if current_app.config["LOCAL_TEST_MODE"]:
            return local_test_user()
        # La identidad interna nunca sirve como sesión en modo autenticado.
        if uid == LOCAL_TEST_USER_ID:
            return None
        return User.query.get(uid)

    @login_manager.request_loader
    def load_local_test_user(_request):
        if current_app.config["LOCAL_TEST_MODE"]:
            from app.local_test import local_test_user
            return local_test_user()
        return None

    @login_manager.unauthorized_handler
    def unauth():
        return jsonify({"error": "No autenticado", "request_id": g.get("request_id", "")}), 401

    @app.before_request
    def _rid():
        g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]

    @app.after_request
    def _after(resp):
        resp.headers["X-Request-ID"] = g.get("request_id", "")
        resp.headers["Cache-Control"] = "no-store"
        return resp

    # Flask-WTF verifica el token antes de ejecutar las rutas; un código estable
    # permite que la SPA renueve el token sin repetir operaciones ya ejecutadas.
    from flask_wtf.csrf import CSRFError
    from flask_wtf.csrf import generate_csrf

    def _with_csrf_cookie(response):
        # Las versiones anteriores de la SPA leen el token de esta cookie.
        # Sigue siendo el token firmado y asociado a la sesión que valida
        # Flask-WTF; la cookie por sí sola nunca autoriza una operación.
        response.set_cookie("csrftoken", generate_csrf(),
                            secure=bool(request.is_secure), httponly=False,
                            samesite="Lax", path="/")
        return response

    @app.errorhandler(CSRFError)
    def _csrf_error(e):
        response = jsonify({"error": "La sesión de seguridad venció. Volvé a intentarlo.",
                            "code": "csrf_invalid", "request_id": g.get("request_id", "")})
        response.status_code = 400
        return _with_csrf_cookie(response)

    @app.errorhandler(400)
    @app.errorhandler(401)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(409)
    @app.errorhandler(413)
    @app.errorhandler(422)
    @app.errorhandler(500)
    def _err(e):
        code = getattr(e, "code", 500)
        return jsonify({"error": getattr(e, "description", "Error interno"), "request_id": g.get("request_id", "")}), code

    @app.get("/health")
    def health():
        return jsonify({"ok": True, "service": "api"})

    @app.get("/ready")
    def ready():
        # DB check
        try:
            db.session.execute(db.text("SELECT 1"))
            dbo = True
        except Exception:
            dbo = False
        # reader status: modelo listo?
        import os as _os
        md = _os.environ.get("MODEL_DIR", "./data/models")
        reader = "ready" if any(f.endswith(".safetensors") for f in (_os.listdir(md) if _os.path.isdir(md) else [])) else "pending"
        return jsonify({"db": dbo, "reader": reader})

    # CSRF token endpoint (para SPA same-origin)
    @app.get("/api/v1/auth/csrf")
    def _csrf():
        return _with_csrf_cookie(jsonify({"csrfToken": generate_csrf()}))

    # blueprints
    from app.routes.auth import bp as auth_bp
    from app.routes.documents import bp as docs_bp
    from app.routes.jobs import bp as jobs_bp
    from app.routes.models_ep import bp as models_bp
    from app.routes.exports import bp as exports_bp
    from app.routes.training import bp as training_bp
    from app.routes.settings import bp as settings_bp
    for b in (auth_bp, docs_bp, jobs_bp, models_bp, exports_bp, training_bp, settings_bp):
        app.register_blueprint(b, url_prefix="/api/v1")

    # CLI: create-admin (un solo uso local)
    @app.cli.command("create-admin")
    def _mkadmin():
        import click
        from app.utils_security import hash_password
        email = os.environ.get("ADMIN_EMAIL", "admin@local")
        pw = os.environ.get("ADMIN_PASSWORD")
        if not pw:
            raise click.ClickException("Definí ADMIN_PASSWORD en el entorno (no se guarda en el repo)")
        if User.query.filter_by(email=email).first():
            print("ya existe"); return
        u = User(email=email, password_hash=hash_password(pw), role="superadmin")
        db.session.add(u); db.session.commit()
        print(f"admin {email} creado")

    return app
