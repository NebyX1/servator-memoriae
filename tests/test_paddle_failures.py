"""El lector falla de forma explícita y puede recuperar el uso de CPU."""
import io


def test_invalid_image_and_missing_upload_are_rejected():
    from paddle_service.server import app
    client = app.test_client()
    assert client.post('/infer').status_code == 422
    response = client.post('/infer', data={'image': (io.BytesIO(b'no es una imagen'), 'invalida.png')})
    assert response.status_code == 422
    assert 'imagen' in response.get_json()['error'].lower()


def test_gpu_memory_failure_falls_back_to_cpu_with_reason(monkeypatch):
    from paddle_service import server
    calls = []
    def predict(path, device):
        calls.append(device)
        if device == 'cuda':
            raise RuntimeError('memoria GPU insuficiente')
        return {'text': 'Prueba', 'device': device}
    monkeypatch.setattr(server, '_predict', predict)
    monkeypatch.setattr(server, '_unload', lambda: None)
    result = server._predict_with_fallback('page.png', 'cuda')
    assert calls == ['cuda', 'cpu']
    assert result['device'] == 'cpu' and 'memoria GPU' in result['fallback_reason']
