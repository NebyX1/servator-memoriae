"""Servicio local de PaddleOCR-VL-1.6, una sola instancia y acceso serializado."""
import gc
import io
import json
import os
import platform
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, request
from PIL import Image, ImageDraw, ImageFont, ImageOps

from engine.paddle_assets import REVISION, model_dir, verified_assets

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 550 * 1024 * 1024
guard = threading.RLock()
pipeline = None
state = {'loaded': False, 'device': None, 'phase': 'sin iniciar', 'error': None, 'last_seconds': None}


def proof_path():
    return Path(os.environ.get('DATA_DIR', '/data')) / 'config' / 'paddle-vl16-smoke.json'


def hardware():
    import torch
    result = {'os': platform.system(), 'architecture': platform.machine(),
              'gpu_available': False, 'gpu_name': None, 'compute_capability': None,
              'memory_free_mb': None, 'memory_total_mb': None, 'driver': None,
              'torch': torch.__version__, 'cuda_runtime': torch.version.cuda}
    if os.environ.get('PADDLE_GPU_ENABLED') != '1':
        return result
    try:
        if not torch.cuda.is_available():
            return result
        # Ejecutar una operación real evita anunciar una GPU que solo es visible.
        (torch.ones(1, device='cuda') + 1).cpu()
        torch.cuda.synchronize()
        free, total = torch.cuda.mem_get_info(0)
        result.update(gpu_available=True, gpu_name=torch.cuda.get_device_name(0),
                      compute_capability=list(torch.cuda.get_device_capability(0)),
                      memory_free_mb=int(free / 1048576), memory_total_mb=int(total / 1048576))
        try:
            probe = subprocess.run(['nvidia-smi', '--query-gpu=driver_version', '--format=csv,noheader'],
                                   capture_output=True, text=True, timeout=3, check=True)
            result['driver'] = probe.stdout.strip().splitlines()[0]
        except (OSError, subprocess.SubprocessError, IndexError):
            pass
    except Exception as exc:
        result['gpu_error'] = str(exc)[:300]
    return result


def automatic_device(info):
    # Dejar margen para el análisis de regiones, buffers y otras tareas del host.
    if info['gpu_available'] and state['loaded'] and state['device'] == 'cuda':
        return 'cuda'
    return 'cuda' if info['gpu_available'] and (info['memory_free_mb'] or 0) >= 4500 else 'cpu'


def _unload():
    global pipeline
    if pipeline is not None:
        pipeline = None
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
    state.update(loaded=False, device=None, phase='sin cargar')


def _load(device):
    global pipeline
    if pipeline is not None and state['device'] == device:
        return
    if not verified_assets():
        raise ValueError('Los archivos oficiales todavía no están preparados. Revisá Configuración.')
    _unload()
    state.update(phase='inicializando', error=None)
    from paddleocr import PaddleOCRVL
    root = model_dir()
    # Ambos directorios corresponden a revisiones oficiales verificadas.
    pipeline = PaddleOCRVL(pipeline_version='v1.6', engine='transformers',
        device='gpu:0' if device == 'cuda' else 'cpu',
        vl_rec_model_dir=str(root / 'recognizer'),
        layout_detection_model_dir=str(root / 'layout'),
        use_doc_orientation_classify=False, use_doc_unwarping=False,
        use_layout_detection=True, use_chart_recognition=False,
        use_seal_recognition=False, format_block_content=False, use_queues=False)
    state.update(loaded=True, device=device, phase='modelo cargado')


def _plain(value):
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if hasattr(value, 'tolist'):
        return value.tolist()
    if hasattr(value, 'item'):
        return value.item()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _predict(path, device):
    _load(device)
    started = time.monotonic()
    state['phase'] = 'detectando regiones y reconociendo escritura'
    results = list(pipeline.predict(path, max_new_tokens=2048, format_block_content=False))
    if not results:
        raise ValueError('El lector no devolvió resultados para esta imagen.')
    raw = _plain(results[0].json)
    payload = raw.get('res', raw) if isinstance(raw, dict) else {}
    blocks = payload.get('parsing_res_list') or []
    if not isinstance(blocks, list):
        raise ValueError('El lector devolvió una estructura de regiones inválida.')
    ordered = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        content = block.get('block_content')
        if isinstance(content, str) and content.strip():
            ordered.append({'text': content, 'label': block.get('block_label'),
                            'bbox': block.get('block_bbox'), 'order': block.get('block_order'),
                            'id': block.get('block_id')})
    text = '\n'.join(b['text'] for b in ordered)
    if not text.strip():
        raise ValueError('PaddleOCR-VL no detectó texto legible en esta página; revisá la imagen.')
    elapsed = round(time.monotonic() - started, 3)
    state.update(phase='modelo cargado', last_seconds=elapsed, error=None)
    return {'text': text, 'blocks': ordered, 'device': device, 'elapsed_seconds': elapsed,
            'model': 'PaddleOCR-VL-1.6-0.9B', 'model_revision': REVISION,
            'pipeline_version': 'v1.6', 'backend': 'transformers',
            'preprocessing': {'exif_orientation': True, 'unwarping': False,
                              'orientation_classification': False, 'layout_detection': True}}


def _predict_with_fallback(path, requested):
    try:
        return _predict(path, requested)
    except Exception as exc:
        _unload()
        if requested != 'cuda':
            raise
        reason = str(exc)[:350]
        state['phase'] = 'GPU no disponible; intentando CPU'
        try:
            result = _predict(path, 'cpu')
        except Exception as fallback:
            raise ValueError(f'No se pudo leer en GPU ({reason}) ni en CPU ({str(fallback)[:350]}).') from fallback
        result['fallback_reason'] = reason
        return result


@app.get('/health')
def health():
    return jsonify({'ok': True})


@app.get('/status')
def status():
    info = hardware()
    chosen = automatic_device(info)
    proof = None
    try:
        proof = json.loads(proof_path().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        pass
    files = verified_assets()
    ready = bool(files and proof and proof.get('revision') == REVISION and proof.get('image_inference'))
    return jsonify({'ready': ready, 'files_verified': files, 'model_loaded': state['loaded'],
        'phase': state['phase'], 'error': state['error'], 'device': proof.get('device') if ready else None,
        'detected_device': chosen, 'hardware': info, 'model': 'PaddleOCR-VL-1.6-0.9B',
        'revision': REVISION, 'backend': 'transformers', 'last_seconds': state['last_seconds'],
        'checked_at': proof.get('checked_at') if ready else None,
        'fallback_reason': proof.get('fallback_reason') if ready else None})


@app.post('/unload')
def unload():
    with guard:
        _unload()
    return jsonify({'ok': True})


@app.post('/prepare')
def prepare():
    with guard:
        try:
            info = hardware()
            requested = (request.get_json(silent=True) or {}).get('device', 'cpu')
            if requested not in ('cpu', 'cuda'):
                return jsonify({'error': 'Dispositivo inválido.'}), 422
            device = 'cuda' if requested == 'cuda' and automatic_device(info) == 'cuda' else 'cpu'
            image = Image.new('RGB', (1200, 400), 'white')
            draw = ImageDraw.Draw(image)
            try:
                from reportlab import __file__ as reportlab_init
                font = ImageFont.truetype(str(Path(reportlab_init).parent / 'fonts' / 'Vera.ttf'), 54)
            except (OSError, ImportError):
                font = ImageFont.load_default()
            draw.text((50, 140), 'Archivo de prueba 1923', fill='black', font=font)
            with tempfile.TemporaryDirectory(prefix='servator-paddle-smoke-') as temp:
                path = str(Path(temp) / 'smoke.png')
                image.save(path)
                result = _predict_with_fallback(path, device)
            if requested == 'cuda' and device == 'cpu' and not result.get('fallback_reason'):
                result['fallback_reason'] = 'GPU no disponible o sin memoria suficiente.'
            if '1923' not in result['text'] and 'archivo' not in result['text'].lower():
                raise ValueError('La comprobación visual no reconoció el texto de prueba.')
            import datetime
            proof = {'revision': REVISION, 'device': result['device'], 'image_inference': True,
                     'fallback_reason': result.get('fallback_reason'),
                     'checked_at': datetime.datetime.utcnow().isoformat() + 'Z'}
            path = proof_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix('.tmp')
            tmp.write_text(json.dumps(proof, ensure_ascii=False), encoding='utf-8')
            os.replace(tmp, path)
            return jsonify({'ok': True, 'device': result['device'], 'elapsed_seconds': result['elapsed_seconds'],
                            'fallback_reason': result.get('fallback_reason')})
        except Exception as exc:
            _unload()
            state.update(phase='error', error=str(exc)[:1000])
            return jsonify({'error': str(exc)[:1000]}), 503


@app.post('/infer')
def infer():
    file = request.files.get('image')
    if not file:
        return jsonify({'error': 'Falta la imagen para procesar.'}), 422
    requested = request.form.get('device', 'cpu')
    if requested not in ('cpu', 'cuda'):
        return jsonify({'error': 'Dispositivo inválido.'}), 422
    try:
        rotation = int(request.form.get('rotation', '0')) % 360
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(file.read()))).convert('RGB')
        if rotation:
            image = image.rotate(-rotation, expand=True)
    except Exception:
        return jsonify({'error': 'No se pudo abrir la imagen. Revisá el archivo.'}), 422
    with guard:
        try:
            fallback_reason = None
            if requested == 'cuda' and automatic_device(hardware()) != 'cuda':
                requested = 'cpu'
                fallback_reason = 'GPU no disponible o sin memoria suficiente.'
            with tempfile.TemporaryDirectory(prefix='servator-paddle-page-') as temp:
                path = str(Path(temp) / 'page.png')
                image.save(path)
                result = _predict_with_fallback(path, requested)
                if fallback_reason:
                    result['fallback_reason'] = fallback_reason
                result['preprocessing']['rotation'] = rotation
            return jsonify(result)
        except Exception as exc:
            _unload()
            state.update(phase='error', error=str(exc)[:1000])
            return jsonify({'error': str(exc)[:1000]}), 503
