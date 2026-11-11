"""Prueba manual aislada: OCR real y cola RQ con SQLite y datos temporales.

Requiere QA_IMAGE de solo lectura, MODEL_DIR, Redis de pruebas, PADDLE_URL y GPU.
No usa ni modifica la base de datos ni los documentos de la instalación.
"""
import io
import json
import os
import subprocess
import sys
import time
import zipfile

from PIL import Image


def main():
    # No permitir que una ejecución accidental apunte a datos reales.
    expected = {'DATABASE_URL': 'sqlite:////tmp/servator-test.db',
                'DATA_DIR': '/tmp/servator-test-data',
                'REDIS_URL': 'redis://redis:6379/13',
                'RQ_QUEUE': 'servator-it-cpu', 'RQ_GPU_QUEUE': 'servator-it-gpu',
                'PADDLE_URL': 'http://servator-paddle-vl16-test:8080'}
    if any(os.environ.get(key) != value for key, value in expected.items()):
        raise RuntimeError('Esta prueba requiere su configuración aislada de SQLite, Redis y servicio de prueba.')
    if os.path.exists('/tmp/servator-test.db') or os.path.exists('/tmp/servator-test-data'):
        raise RuntimeError('La prueba requiere directorios temporales nuevos y vacíos.')
    if not os.path.realpath(os.environ.get('QA_IMAGE', '')).startswith('/user-data/'):
        raise RuntimeError('QA_IMAGE debe apuntar a la copia de solo lectura montada en /user-data.')
    from app import create_app
    from app.extensions import db
    from app.services_device import probe_workers
    from app.models import Job

    app = create_app(overrides={'TESTING': True, 'WTF_CSRF_ENABLED': False})
    with app.app_context():
        db.create_all()
        client = app.test_client()
        worker = subprocess.Popen([sys.executable, '/src/worker/run.py', '--queue',
                                   os.environ['RQ_GPU_QUEUE'] + ',' + os.environ['RQ_QUEUE']])
        try:
            for _ in range(90):
                if probe_workers()['cuda']['available']:
                    break
                if worker.poll() is not None:
                    raise RuntimeError('El worker de prueba se detuvo.')
                time.sleep(1)
            else:
                raise RuntimeError('El worker de GPU no se anunció.')

            def post(path, **kwargs):
                result = client.post(path, **kwargs)
                if result.status_code not in (200, 201):
                    raise AssertionError(f'{path}: {result.status_code} {result.get_data(as_text=True)[:400]}')
                return result.get_json()

            def wait(job_id):
                start = time.monotonic()
                while time.monotonic() - start < 900:
                    db.session.expire_all()
                    job = db.session.get(Job, job_id)
                    if job.status in ('COMPLETED', 'FAILED', 'CANCELLED'):
                        print('JOB', job.kind, job.status, job.phase, job.error, flush=True)
                        assert job.status == 'COMPLETED', job.error
                        return
                    time.sleep(2)
                raise TimeoutError(job_id)

            def export(target, fmt):
                job = post('/api/v1/exports', json={**target, 'format': fmt})['job_id']
                wait(job)
                response = client.get(f'/api/v1/exports/{job}/download')
                assert response.status_code == 200 and len(response.data) > 100
                print('EXPORT', fmt, len(response.data), flush=True)
                return response.data

            status = client.put('/api/v1/settings/processing', json={'ocr_mode': 'dual'})
            assert status.status_code == 200, status.get_data(as_text=True)
            assert status.get_json()['paddle']['ready']
            doc = post('/api/v1/documents', json={'title': 'Prueba aislada doble'})['id']
            with open(os.environ['QA_IMAGE'], 'rb') as source:
                image = source.read()
            upload = post(f'/api/v1/documents/{doc}/upload', data={'file': (io.BytesIO(image), 'manuscrito.png')})
            assert not upload['errors'] and len(upload['added']) == 1
            job = post('/api/v1/jobs/transcribe', json={'document_id': doc})
            assert job['ocr_mode'] == 'dual' and job['device'] == 'cuda', job
            wait(job['job_id'])
            page = client.get(f'/api/v1/documents/{doc}').get_json()['pages'][0]['id']
            result = client.get(f'/api/v1/pages/{page}/ocr').get_json()
            assert set(result['engines']) == {'kraken', 'paddleocr_vl'}
            assert all(engine['status'] == 'completed' and engine['text'].strip() for engine in result['engines'].values())
            assert result['comparison'] and result['comparison']['differences'] > 0
            print('DUAL', {name: len(value['text']) for name, value in result['engines'].items()},
                  'differences', result['comparison']['differences'], flush=True)
            text = result['engines']['kraken']['text']
            post(f'/api/v1/pages/{page}/ocr/review', json={'job_id': job['job_id'], 'text': text, 'source': 'kraken', 'version': 0})
            exported = json.loads(export({'document_id': doc}, 'json'))
            assert exported['full_text'] == text and exported['pages'][0]['ocr']['engines'][1]['name'] in ('kraken', 'paddleocr_vl')
            assert export({'document_id': doc}, 'pdf-lectura').startswith(b'%PDF')
            assert export({'document_id': doc}, 'pdf-facsimil').startswith(b'%PDF')
            assert zipfile.is_zipfile(io.BytesIO(export({'document_id': doc}, 'docx')))

            assert client.put('/api/v1/settings/processing', json={'ocr_mode': 'kraken'}).status_code == 200
            assert client.put('/api/v1/settings/processing', json={'device': 'cpu'}).status_code == 200
            collection = post('/api/v1/collections', json={'title': 'Colección aislada'})['id']
            doc2 = post('/api/v1/documents', json={'title': 'Dos páginas', 'collection_id': collection})['id']
            with Image.open(io.BytesIO(image)) as original:
                resized = original.convert('RGB')
                resized.thumbnail((800, 1200))
                one = io.BytesIO(); resized.save(one, 'PNG')
                resized.putpixel((0, 0), (0, 0, 0))
                two = io.BytesIO(); resized.save(two, 'PNG')
            upload = post(f'/api/v1/documents/{doc2}/upload', data={'files': [(io.BytesIO(one.getvalue()), '01.png'), (io.BytesIO(two.getvalue()), '02.png')]})
            assert not upload['errors'] and len(upload['added']) == 2
            pages = client.get(f'/api/v1/documents/{doc2}').get_json()['pages']
            assert len(pages) == 2 and [p['order'] for p in pages] == sorted(p['order'] for p in pages)
            wait(post('/api/v1/jobs/transcribe', json={'document_id': doc2})['job_id'])
            collection_zip = export({'collection_id': collection}, 'json')
            with zipfile.ZipFile(io.BytesIO(collection_zip)) as archive:
                content = json.loads(archive.read(archive.namelist()[0]))
                assert len(content['pages']) == 2
                assert [p['id'] for p in content['pages']] == [p['id'] for p in pages]
            print('COLLECTION two pages and order verified', flush=True)
        finally:
            worker.terminate()
            try:
                worker.wait(timeout=30)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait()


if __name__ == '__main__':
    main()
