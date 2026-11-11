"""Persistencia, selección explícita y recuperación de lecturas independientes."""
import io
from PIL import Image


def seed(client):
    doc = client.post('/api/v1/documents', json={'title': 'Prueba doble'}).get_json()['id']
    image = io.BytesIO()
    Image.new('RGB', (120, 100), 'white').save(image, 'PNG')
    image.seek(0)
    assert client.post(f'/api/v1/documents/{doc}/upload', data={'files': (image, 'pagina.png')}).status_code == 200
    page = client.get(f'/api/v1/documents/{doc}').get_json()['pages'][0]['id']
    return doc, page


def test_modes_preserve_device_and_snapshot(auth_client, app, monkeypatch):
    from app.services_device import save_preference, get_preference
    from app.models import Job
    monkeypatch.setattr('app.services_device.probe_workers', lambda: {'cpu': {'available': True}, 'cuda': {'available': False, 'name': None}, 'redis_ok': True})
    monkeypatch.setattr('app.services_paddle.paddle_status', lambda: {'ready': True, 'device': 'cpu', 'detected_device': 'cpu', 'files_verified': True, 'server_online': True, 'preparation': None})
    monkeypatch.setattr('app.routes.jobs.dispatch', lambda job: None)
    save_preference('cpu')
    doc, _ = seed(auth_client)
    assert auth_client.put('/api/v1/settings/processing', json={'ocr_mode': 'dual'}).status_code == 200
    assert auth_client.put('/api/v1/settings/processing', json={'device': 'auto'}).status_code == 409
    job_id = auth_client.post('/api/v1/jobs/transcribe', json={'document_id': doc}).get_json()['job_id']
    assert auth_client.put('/api/v1/settings/processing', json={'ocr_mode': 'kraken'}).status_code == 200
    assert get_preference() == 'cpu'
    assert Job.query.get(job_id).payload['ocr_mode'] == 'dual'
    assert Job.query.get(job_id).payload['kraken_device'] == 'cpu'


def test_dual_review_and_exports_require_explicit_choice(auth_client, app, tmp_path):
    from app.extensions import db
    from app.models import Job, OcrResult, OcrReview
    from app.tasks import _build_json
    from app.services_export_docx import build_docx
    from app.services_export_pdf import build_pdf
    from app.services_storage import ObjectStorage
    from app.config import settings
    from docx import Document as WordDocument
    import pypdfium2
    doc, page = seed(auth_client)
    job = Job(kind='transcribe', payload={'ocr_mode': 'dual'}, status='COMPLETED')
    db.session.add(job); db.session.flush()
    db.session.add_all([OcrResult(job_id=job.id, page_id=page, engine='kraken', model_version='v1', device='cpu', status='completed', text='nació el 3 de mayo'),
                        OcrResult(job_id=job.id, page_id=page, engine='paddleocr_vl', model_version='rev', device='cpu', status='completed', text='nació el 8 de mayo')])
    db.session.commit()
    comparison = auth_client.get(f'/api/v1/pages/{page}/ocr').get_json()
    assert comparison['comparison']['differences'] == 1
    before = _build_json(doc, 'revised_fallback_auto')
    assert before['full_text'] == ''
    assert before['pages'][0]['ocr']['review_status'] == 'pending'
    reviewed = auth_client.post(f'/api/v1/pages/{page}/ocr/review', json={'job_id': job.id, 'text': 'nació el 3 de [ilegible]', 'source': 'manual', 'version': 0})
    assert reviewed.status_code == 200
    assert auth_client.post(f'/api/v1/pages/{page}/ocr/review', json={'job_id': job.id, 'text': 'otra versión', 'source': 'manual', 'version': 0}).status_code == 409
    assert OcrReview.query.count() == 1
    assert _build_json(doc, 'revised_fallback_auto')['full_text'] == 'nació el 3 de [ilegible]'
    out = tmp_path / 'revisado.docx'
    build_docx(doc, str(out))
    assert 'nació el 3 de [ilegible]' in [p.text for p in WordDocument(out).paragraphs]
    for mode in ('pdf-lectura', 'pdf-facsimil'):
        pdf = tmp_path / (mode + '.pdf')
        build_pdf(doc, str(pdf), mode=mode, storage=ObjectStorage(settings()))
        extracted = pypdfium2.PdfDocument(str(pdf))[0].get_textpage().get_text_range()
        assert '[ilegible]' in extracted
    assert {r.text for r in OcrResult.query.all()} == {'nació el 3 de mayo', 'nació el 8 de mayo'}


def test_partial_failure_keeps_success_and_retry_is_idempotent(auth_client, app, monkeypatch):
    from app.extensions import db
    from app.models import Job, OcrResult
    from app.tasks import _transcribe_multimodal
    import kraken_adapter
    import pytest
    doc, page = seed(auth_client)
    job = Job(kind='transcribe', status='RUNNING', payload={'ocr_mode': 'dual', 'device': 'cpu', 'kraken_device': 'cpu', 'model_version': 'v1', 'paddle_revision': 'rev', 'page_ids': [page]})
    db.session.add(job); db.session.commit()
    monkeypatch.setattr(kraken_adapter, 'transcribe_image', lambda *a, **k: [{'order': 0, 'text': 'resultado Kraken', 'baseline': [], 'polygon': [], 'confidence': 0.5}])
    def fail(*args, **kwargs): raise ValueError('Fallo del lector visual')
    monkeypatch.setattr('app.services_paddle.transcribe_image', fail)
    with pytest.raises(ValueError, match='parcial'):
        _transcribe_multimodal(job)
    assert {r.engine: r.status for r in OcrResult.query.all()} == {'kraken': 'completed', 'paddleocr_vl': 'failed'}
    monkeypatch.setattr('app.services_paddle.transcribe_image', lambda *a, **k: {'text': 'resultado Paddle', 'device': 'cpu', 'blocks': []})
    _transcribe_multimodal(job)
    assert OcrResult.query.count() == 2
    assert {r.engine: r.text for r in OcrResult.query.all()} == {'kraken': 'resultado Kraken', 'paddleocr_vl': 'resultado Paddle'}


def test_new_dual_reading_preserves_previous_human_line_review(auth_client):
    from app.extensions import db
    from app.models import Job, Line, OcrResult
    from app.tasks import _build_json
    doc, page = seed(auth_client)
    db.session.add(Line(page_id=page, order_index=0, auto_text='original automático', revised_text='corrección humana', state='corrected'))
    job = Job(kind='transcribe', payload={'ocr_mode': 'dual'}, status='COMPLETED')
    db.session.add(job); db.session.flush()
    db.session.add_all([OcrResult(job_id=job.id, page_id=page, engine='kraken', model_version='v1', device='cpu', status='completed', text='nueva propuesta Kraken'),
                        OcrResult(job_id=job.id, page_id=page, engine='paddleocr_vl', model_version='rev', device='cuda', status='completed', text='nueva propuesta Paddle')])
    db.session.commit()
    exported = _build_json(doc, 'revised_fallback_auto')
    assert exported['full_text'] == 'corrección humana'
    assert exported['pages'][0]['ocr']['review_status'] == 'previous_line_review'
    assert len(exported['pages'][0]['ocr']['engines']) == 2


def test_pdf_facs_indicates_automatic_or_pending_text(auth_client, tmp_path):
    import pypdfium2
    from app.extensions import db
    from app.models import Job, OcrResult
    from app.services_export_pdf import build_pdf
    from app.services_storage import ObjectStorage
    from app.config import settings
    doc, page = seed(auth_client)
    job = Job(kind='transcribe', payload={'ocr_mode': 'paddleocr_vl'}, status='COMPLETED')
    db.session.add(job); db.session.flush()
    db.session.add(OcrResult(job_id=job.id, page_id=page, engine='paddleocr_vl', model_version='rev', device='cpu', status='completed', text='texto automático'))
    db.session.commit()
    pdf = tmp_path / 'automatico.pdf'
    build_pdf(doc, str(pdf), mode='pdf-facsimil', storage=ObjectStorage(settings()))
    extracted = pypdfium2.PdfDocument(str(pdf))[0].get_textpage().get_text_range()
    assert 'texto automático' in extracted
    assert 'pendiente de revisión' in extracted


def test_legacy_preferences_migrate_without_losing_other_settings(app):
    import json
    from pathlib import Path
    from app.config import settings
    from app.services_device import get_ocr_mode
    path = Path(settings().DATA_DIR) / 'config' / 'processing.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    for old_mode in ('qwen', 'dual'):
        path.write_text(json.dumps({'device': 'cuda', 'ocr_mode': old_mode, 'other': 'preservado'}), encoding='utf-8')
        assert get_ocr_mode() == 'kraken'
        migrated = json.loads(path.read_text(encoding='utf-8'))
        assert migrated['device'] == 'cuda' and migrated['other'] == 'preservado'
        assert migrated['ocr_mode'] == 'kraken' and migrated['ocr_schema_version'] == 2


def test_historical_result_remains_reviewable_and_retains_provenance(auth_client):
    from app.extensions import db
    from app.models import Job, OcrResult, OcrReview
    doc, page = seed(auth_client)
    job = Job(kind='transcribe', payload={'ocr_mode': 'dual'}, status='COMPLETED')
    db.session.add(job); db.session.flush()
    db.session.add_all([
        OcrResult(job_id=job.id, page_id=page, engine='kraken', model_version='v1', device='cpu', status='completed', text='Lectura anterior'),
        OcrResult(job_id=job.id, page_id=page, engine='qwen3_vl', model_version='old', device='cpu', status='completed', text='Otra lectura anterior'),
    ])
    db.session.commit()
    data = auth_client.get(f'/api/v1/pages/{page}/ocr').get_json()
    assert set(data['engines']) == {'kraken', 'historical'} and data['comparison']['differences'] > 0
    response = auth_client.post(f'/api/v1/pages/{page}/ocr/review', json={'job_id': job.id, 'text': 'Otra lectura anterior', 'source': 'historical', 'version': 0})
    assert response.status_code == 200
    assert OcrReview.query.one().source == 'qwen3_vl'
    assert OcrResult.query.filter_by(engine='qwen3_vl').one().text == 'Otra lectura anterior'


def test_cancelled_between_engines_keeps_completed_proposal(auth_client, monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace
    import sys
    from app.extensions import db
    from app.models import Job, OcrResult
    from app.services_queue import Cancelled
    from app.tasks import execute_job
    from app import tasks
    doc, page = seed(auth_client)
    job = Job(kind='transcribe', status='QUEUED', payload={'ocr_mode': 'dual', 'device': 'cpu',
              'kraken_device': 'cpu', 'model_version': 'v1', 'paddle_revision': 'rev', 'page_ids': [page]})
    db.session.add(job); db.session.commit()
    monkeypatch.setitem(sys.modules, 'kraken_adapter', SimpleNamespace(transcribe_image=lambda *a, **k: [{'text': 'texto conservado'}]))
    monkeypatch.setattr('app.services_gpu_lock.paddle_guard', lambda: nullcontext())
    def checkpoint(job, done, total=None, phase=None):
        if phase and phase.startswith('PaddleOCR-VL:'):
            raise Cancelled()
    monkeypatch.setattr(tasks, '_ckpt', checkpoint)
    execute_job(job.id)
    db.session.expire_all()
    assert db.session.get(Job, job.id).status == 'CANCELLED'
    assert [(r.engine, r.text) for r in OcrResult.query.all()] == [('kraken', 'texto conservado')]


def test_dual_engines_receive_same_page_rotation(auth_client, monkeypatch):
    from app.extensions import db
    from app.models import Job, Page, OcrResult
    from app.tasks import _transcribe_multimodal
    import kraken_adapter
    doc, page = seed(auth_client)
    db.session.get(Page, page).rotation = 90
    job = Job(kind='transcribe', status='RUNNING', payload={'ocr_mode': 'dual', 'device': 'cpu',
              'kraken_device': 'cpu', 'paddle_revision': 'rev', 'page_ids': [page]})
    db.session.add(job); db.session.commit()
    def read_kraken(path, **kwargs):
        with Image.open(path) as image:
            assert image.size == (100, 120)
        return [{'text': 'lectura'}]
    def read_paddle(path, **kwargs):
        with Image.open(path) as image:
            assert image.size == (120, 100)
        assert kwargs['rotation'] == 90
        return {'text': 'lectura', 'device': 'cpu', 'preprocessing': {'rotation': 90}}
    monkeypatch.setattr(kraken_adapter, 'transcribe_image', read_kraken)
    monkeypatch.setattr('app.services_paddle.transcribe_image', read_paddle)
    _transcribe_multimodal(job)
    assert all(r.details['preprocessing']['rotation'] == 90 for r in OcrResult.query.all())
