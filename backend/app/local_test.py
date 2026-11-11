"""Identidad interna de la instalación local, sin contraseña utilizable."""
import secrets

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import User
from app.utils_security import hash_password

# Se conserva en la base porque documentos y trabajos registran un responsable.
# No es una cuenta de acceso y no puede iniciar sesión con una contraseña conocida.
LOCAL_TEST_USER_ID = "00000000-0000-4000-8000-0000000000fe"
LOCAL_TEST_EMAIL = "modo-prueba@local.invalid"


def local_test_user():
    user = db.session.get(User, LOCAL_TEST_USER_ID)
    if user is not None:
        if user.email != LOCAL_TEST_EMAIL or not user.is_active or user.role != "superadmin":
            raise RuntimeError("La identidad interna de prueba no es válida")
        return user
    user = User(id=LOCAL_TEST_USER_ID, email=LOCAL_TEST_EMAIL,
                password_hash=hash_password(secrets.token_urlsafe(48)), role="superadmin")
    db.session.add(user)
    try:
        db.session.commit()
        return user
    except IntegrityError:
        # Dos primeras solicitudes pueden intentar crear la identidad a la vez.
        db.session.rollback()
        user = db.session.get(User, LOCAL_TEST_USER_ID)
        if user is None or user.email != LOCAL_TEST_EMAIL or not user.is_active or user.role != "superadmin":
            raise
        return user
