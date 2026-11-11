"""La SPA usa el token JSON de Flask-WTF, también con sesiones existentes."""
from tests.conftest import make_user


def test_csrf_required_and_json_token_authorizes_existing_session(app, client):
    app.config["WTF_CSRF_ENABLED"] = True
    make_user()
    rejected = client.post('/api/v1/auth/login', json={'email': 'admin@local.test', 'password': 'una-clave-larga-1234'})
    assert rejected.status_code == 400
    assert rejected.get_json()['code'] == 'csrf_invalid'
    token = client.get('/api/v1/auth/csrf').get_json()['csrfToken']
    login = client.post('/api/v1/auth/login', json={'email': 'admin@local.test', 'password': 'una-clave-larga-1234'}, headers={'X-CSRFToken': token})
    assert login.status_code == 200
    assert client.get('/api/v1/auth/me').get_json()['user']['email'] == 'admin@local.test'
    token = client.get('/api/v1/auth/csrf').get_json()['csrfToken']
    rejected = client.post('/api/v1/documents', json={'title': 'sin token'})
    assert rejected.status_code == 400
    created = client.post('/api/v1/documents', json={'title': 'con token'}, headers={'X-CSRFToken': token})
    assert created.status_code == 201
    assert created.get_json()['id']


def test_csrf_token_is_bound_to_its_session(app, client):
    app.config['WTF_CSRF_ENABLED'] = True
    token = client.get('/api/v1/auth/csrf').get_json()['csrfToken']
    other = app.test_client()
    response = other.post('/api/v1/auth/login', json={}, headers={'X-CSRFToken': token})
    assert response.status_code == 400
    assert response.get_json()['code'] == 'csrf_invalid'


def test_legacy_client_recovers_after_missing_token_without_bypassing_auth(app, client):
    app.config['WTF_CSRF_ENABLED'] = True
    make_user()
    token = client.get('/api/v1/auth/csrf').get_json()['csrfToken']
    assert client.get_cookie('csrftoken').value == token
    assert client.post('/api/v1/auth/login', json={'email': 'admin@local.test', 'password': 'una-clave-larga-1234'},
                       headers={'X-CSRFToken': token}).status_code == 200

    # La pestaña anterior nunca obtuvo una cookie. El primer intento no debe
    # ejecutarse; al volver a intentar, su interceptor usa el token renovado.
    client.delete_cookie('csrftoken')
    rejected = client.post('/api/v1/documents', json={'title': 'No creado'})
    assert rejected.status_code == 400
    renewed = client.get_cookie('csrftoken').value
    created = client.post('/api/v1/documents', json={'title': 'Creado una vez'},
                          headers={'X-CSRFToken': renewed})
    assert created.status_code == 201
    documents = client.get('/api/v1/documents').get_json()['items']
    assert [item['title'] for item in documents] == ['Creado una vez']

    # Obtener un token no inicia sesión ni habilita escrituras anónimas.
    # La fixture mantiene un app_context compartido, a diferencia del servidor.
    from flask import g
    g.pop('csrf_token', None)
    g.pop('_login_user', None)
    anonymous = app.test_client()
    assert anonymous.post('/api/v1/documents', json={'title': 'No autorizado'}).status_code == 400
    anon_token = anonymous.get_cookie('csrftoken').value
    assert anonymous.post('/api/v1/documents', json={'title': 'No autorizado'},
                          headers={'X-CSRFToken': anon_token}).status_code == 401
    assert anonymous.post('/api/v1/auth/login', json={'email': 'admin@local.test', 'password': 'una-clave-larga-1234'},
                          headers={'X-CSRFToken': anon_token}).status_code == 200
    # Otra pestaña comparte las cookies de la sesión. La página original
    # puede enviar la misma cabecera sin recargarse ni descartar el archivo.
    assert anonymous.post('/api/v1/documents', json={'title': 'Tras iniciar sesión'},
                          headers={'X-CSRFToken': anonymous.get_cookie('csrftoken').value}).status_code == 201
