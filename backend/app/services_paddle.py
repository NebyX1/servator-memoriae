"""Cliente del proceso aislado de PaddleOCR-VL; la UI no accede al motor."""
import os

import requests

try:
    from engine.paddle_assets import REVISION as MODEL_REVISION
except ModuleNotFoundError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from engine.paddle_assets import REVISION as MODEL_REVISION


def url():
    return os.environ.get('PADDLE_URL', 'http://paddle:8080').rstrip('/')


def paddle_status():
    status = {'ready': False, 'files_verified': False, 'model_loaded': False,
              'server_online': False, 'device': None, 'detected_device': None,
              'phase': 'servicio no disponible', 'error': None, 'hardware': {},
              'model': 'PaddleOCR-VL-1.6-0.9B', 'backend': 'transformers'}
    try:
        response = requests.get(url() + '/status', timeout=3)
        response.raise_for_status()
        status.update(response.json())
        status['server_online'] = True
    except (requests.RequestException, ValueError):
        pass
    try:
        from app.models import Job
        job = Job.query.filter_by(kind='prepare_paddle').order_by(Job.created_at.desc()).first()
        status['preparation'] = ({'id': job.id, 'status': job.status, 'done': job.progress_done,
                                  'total': job.progress_total, 'phase': job.phase, 'error': job.error} if job else None)
    except Exception:
        status['preparation'] = None
    return status


def automatic_device(status=None):
    from app.services_device import probe_workers
    status = status or paddle_status()
    if status.get('ready') and status.get('device') == 'cpu' and status.get('fallback_reason'):
        return 'cpu'
    return 'cuda' if status.get('detected_device') == 'cuda' and probe_workers()['cuda']['available'] else 'cpu'


def prepare(device):
    try:
        response = requests.post(url() + '/prepare', json={'device': device}, timeout=(5, 1800))
        if not response.ok:
            raise ValueError((response.json() or {}).get('error', 'No se pudo preparar PaddleOCR-VL.'))
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise ValueError('No se pudo comprobar el lector de documentos: ' + str(exc)[:500]) from exc


def transcribe_image(path, device='cpu', rotation=0):
    try:
        with open(path, 'rb') as image:
            response = requests.post(url() + '/infer', data={'device': device, 'rotation': str(rotation)},
                                     files={'image': ('pagina.png', image, 'image/png')}, timeout=(5, 1800))
        if not response.ok:
            try:
                message = response.json().get('error', '')
            except ValueError:
                message = ''
            raise ValueError(message or 'El lector no pudo procesar esta página.')
        result = response.json()
        if result.get('pipeline_version') != 'v1.6' or result.get('model') != 'PaddleOCR-VL-1.6-0.9B':
            raise ValueError('El servicio devolvió un modelo distinto al configurado.')
        if not isinstance(result.get('text'), str) or not result['text'].strip():
            raise ValueError('El lector devolvió una transcripción vacía.')
        return result
    except (requests.RequestException, OSError, KeyError) as exc:
        raise ValueError('No se pudo comunicar con el lector de documentos: ' + str(exc)[:400]) from exc


def unload():
    try:
        requests.post(url() + '/unload', timeout=(2, 30))
    except requests.RequestException:
        pass
