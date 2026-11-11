"""Consulta compartida de propuestas, revisión y texto exportable por página."""
from app.models import OcrResult, OcrReview, Job, Line


def latest_page_ocr(page_id):
    newest = OcrResult.query.filter_by(page_id=page_id).order_by(OcrResult.created_at.desc(), OcrResult.id.desc()).first()
    if not newest:
        return None
    job = Job.query.get(newest.job_id)
    results = OcrResult.query.filter_by(page_id=page_id, job_id=newest.job_id).all()
    review = OcrReview.query.filter_by(page_id=page_id).order_by(OcrReview.version.desc()).first()
    return {'job': job, 'results': results, 'review': review}


def export_page_ocr(page_id, text_source='revised_fallback_auto'):
    data = latest_page_ocr(page_id)
    if not data:
        return None
    job, results, review = data['job'], data['results'], data['review']
    mode = (job.payload or {}).get('ocr_mode', 'kraken')
    text, state = None, 'pending'
    # Una revisión anterior continúa disponible aunque se ejecute otro motor.
    if review and text_source.startswith('revised'):
        text, state = review.text, 'confirmed'
    elif text_source.startswith('revised'):
        lines = Line.query.filter_by(page_id=page_id).order_by(Line.order_index).all()
        if any(line.revised_text is not None for line in lines):
            # Mantener el texto revisado previo incluso si llega una lectura nueva.
            # Los renglones automáticos que acompañan esa revisión se identifican.
            text = '\n'.join((line.revised_text if line.revised_text is not None else line.auto_text) or '' for line in lines)
            state = 'previous_line_review'
    if text is None and mode not in ('dual', 'kraken'):
        proposal = next((r for r in results if r.engine != 'kraken' and r.status == 'completed'), None)
        if proposal:
            text, state = proposal.text, 'automatic'
    return {'ocr_mode': mode, 'review_status': state, 'selected_transcription': text,
            'review': ({'id': review.id, 'version': review.version, 'source': review.source,
                        'user_id': review.user_id, 'job_id': review.job_id,
                        'created_at': review.created_at.isoformat() if review.created_at else None} if review else None),
            'engines': [{'name': r.engine, 'model_version': r.model_version, 'device': r.device,
                         'status': r.status, 'error': r.error, 'text': r.text,
                         'quantization': (r.details or {}).get('quantization'),
                         'fallback_reason': (r.details or {}).get('fallback_reason'),
                         'lines': (r.details or {}).get('lines'),
                         'blocks': (r.details or {}).get('blocks'),
                         'elapsed_seconds': (r.details or {}).get('elapsed_seconds'),
                         'preprocessing': (r.details or {}).get('preprocessing')} for r in results]}
