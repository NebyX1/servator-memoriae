"""Sesiones reales con protección CSRF activa: caducidad y renovación."""
import time

from flask import g

from tests.conftest import make_user


def test_token_caducado_se_puede_renovar_sin_perder_sesion(app, client, monkeypatch):
    app.config.update(WTF_CSRF_ENABLED=True, WTF_CSRF_TIME_LIMIT=1)
    make_user()
    original = client.get('/api/v1/auth/csrf').get_json()['csrfToken']
    logged_in = client.post('/api/v1/auth/login', json={
        'email': 'admin@local.test', 'password': 'una-clave-larga-1234'
    }, headers={'X-CSRFToken': original})
    assert logged_in.status_code == 200

    now = time.time()
    monkeypatch.setattr(time, 'time', lambda: now + 3)
    expired = client.post('/api/v1/documents', json={'title': 'token caducado'},
                          headers={'X-CSRFToken': original})
    assert expired.status_code == 400
    assert expired.get_json()['code'] == 'csrf_invalid'
    assert client.get('/api/v1/auth/me').get_json()['user']['email'] == 'admin@local.test'

    # La fixture mantiene un contexto de aplicación entre peticiones; limpiar
    # el caché por petición que Flask descarta normalmente al terminarla.
    g.pop('csrf_token', None)
    renewed = client.get('/api/v1/auth/csrf').get_json()['csrfToken']
    assert renewed != original
    created = client.post('/api/v1/documents', json={'title': 'token renovado'},
                          headers={'X-CSRFToken': renewed})
    assert created.status_code == 201


def test_cerrar_sesion_impide_escribir_con_token_valido(app, client):
    app.config['WTF_CSRF_ENABLED'] = True
    make_user()
    token = client.get('/api/v1/auth/csrf').get_json()['csrfToken']
    assert client.post('/api/v1/auth/login', json={
        'email': 'admin@local.test', 'password': 'una-clave-larga-1234'
    }, headers={'X-CSRFToken': token}).status_code == 200
    assert client.post('/api/v1/auth/logout', headers={'X-CSRFToken': token}).status_code == 200
    assert client.get('/api/v1/auth/me').get_json()['user'] is None
    assert client.post('/api/v1/documents', json={'title': 'sin sesión'},
                       headers={'X-CSRFToken': token}).status_code == 401
