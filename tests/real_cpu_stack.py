"""Prueba manual del stack CPU, con proyecto y datos temporales aislados.

Ejemplo: python tests/real_cpu_stack.py --image imagen-de-prueba.png
No toca los volúmenes de la instalación; copia únicamente el modelo Kraken.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import uuid

import requests

REPO = Path(__file__).resolve().parents[1]
CORE = ('init', 'backend', 'worker', 'worker-setup', 'dispatcher', 'frontend')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', type=Path, required=True, help='Imagen de prueba que Kraken pueda leer')
    parser.add_argument('--model-container', default='memoria-historica-worker-1')
    args = parser.parse_args()
    if not args.image.is_file():
        raise ValueError('No se encontró la imagen de prueba.')
    root = Path(tempfile.gettempdir()).resolve()
    temp = Path(tempfile.mkdtemp(prefix='servator-cpu-qa-', dir=root)).resolve()
    assert temp.parent == root and temp.name.startswith('servator-cpu-qa-') and not temp.is_symlink()
    project = 'servatorcpuqa' + uuid.uuid4().hex[:8]
    for name in ('pg', 'redis', 'data', 'models'):
        (temp / name).mkdir()
    env = os.environ.copy()
    env.update(DEVICE_MODE='cpu', LOCAL_TEST_MODE='1', FRONT_BIND='127.0.0.1',
               FRONT_PORT='18787', COMPOSE_PARALLEL_LIMIT='1')
    services = {
        'postgres': {'volumes': [f'{(temp / "pg").as_posix()}:/var/lib/postgresql/data']},
        'redis': {'volumes': [f'{(temp / "redis").as_posix()}:/data']},
    }
    for service in ('init', 'backend', 'worker', 'worker-setup', 'paddle'):
        services[service] = {'volumes': [f'{(temp / "data").as_posix()}:/data',
            f'{(temp / "models").as_posix()}:/models' + (':ro' if service == 'paddle' else '')]}
    override = temp / 'override.json'
    override.write_text(json.dumps({'services': services}), encoding='utf-8')
    compose = ['docker', 'compose', '-p', project, '-f', str(REPO / 'docker-compose.yml'), '-f', str(override)]

    def run(command, timeout=600, check=True):
        result = subprocess.run(command, cwd=REPO, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', timeout=timeout)
        if check and result.returncode:
            raise RuntimeError('Falló ' + ' '.join(command[:5]) + '\n' + '\n'.join(result.stdout.splitlines()[-25:]))
        return result

    try:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 18787))
        config = json.loads(run(compose + ['config', '--format', 'json']).stdout)
        expected = {'postgres': {'/var/lib/postgresql/data': temp / 'pg'}, 'redis': {'/data': temp / 'redis'}}
        expected.update({service: {'/data': temp / 'data', '/models': temp / 'models'}
                         for service in ('init', 'backend', 'worker', 'worker-setup', 'paddle')})
        for service, mounts in expected.items():
            actual = {item['target']: item for item in config['services'][service].get('volumes', [])}
            for target, source in mounts.items():
                assert actual[target]['type'] == 'bind' and Path(actual[target]['source']).resolve() == source.resolve()
        assert not run(['docker', 'ps', '-aq', '--filter', f'label=com.docker.compose.project={project}']).stdout.strip()
        print('Aislamiento verificado; copiando el modelo Kraken.', flush=True)
        for filename in ('ppocrv6-medium-v1.safetensors', 'manifest.json'):
            run(['docker', 'cp', f'{args.model_container}:/models/{filename}', str(temp / 'models' / filename)], timeout=120)
        print('Construyendo e iniciando los servicios CPU principales, sin el lector opcional.', flush=True)
        run(compose + ['build', *CORE], timeout=900)
        run(compose + ['up', '-d', *CORE], timeout=300)
        origin = 'http://127.0.0.1:18787'
        session = requests.Session()
        start = time.monotonic()
        while time.monotonic() - start < 150:
            try:
                ready = session.get(origin + '/ready', timeout=3)
                if ready.ok and ready.json().get('db') and ready.json().get('reader') == 'ready':
                    break
            except requests.RequestException:
                pass
            time.sleep(3)
        else:
            raise RuntimeError('El stack CPU no respondió /ready.')
        csrf = session.get(origin + '/api/v1/auth/csrf', timeout=10).json()['csrfToken']
        headers = {'X-CSRFToken': csrf}

        def post(path, **kwargs):
            response = session.post(origin + path, headers=headers, timeout=30, **kwargs)
            if response.status_code not in (200, 201):
                raise RuntimeError(f'{path}: {response.status_code} {response.text[:300]}')
            return response.json()

        def wait(job_id):
            start = time.monotonic()
            while time.monotonic() - start < 420:
                response = session.get(origin + '/api/v1/jobs/' + job_id, timeout=10)
                response.raise_for_status()
                job = response.json()
                if job['status'] in ('COMPLETED', 'FAILED', 'CANCELLED'):
                    if job['status'] != 'COMPLETED':
                        raise RuntimeError(str(job))
                    return
                time.sleep(2)
            raise TimeoutError(job_id)

        print('Salud correcta; leyendo la imagen de prueba con Kraken en CPU.', flush=True)
        doc = post('/api/v1/documents', json={'title': 'Prueba CPU aislada'})['id']
        with args.image.open('rb') as image:
            upload = post(f'/api/v1/documents/{doc}/upload', files={'file': ('prueba.png', image, 'image/png')})
        assert len(upload['added']) == 1 and not upload['errors']
        submitted = post('/api/v1/jobs/transcribe', json={'document_id': doc})
        assert submitted['device'] == 'cpu' and submitted['ocr_mode'] == 'kraken'
        wait(submitted['job_id'])
        pages = session.get(origin + f'/api/v1/documents/{doc}', timeout=10).json()['pages']
        lines = session.get(origin + f"/api/v1/pages/{pages[0]['id']}/lines", timeout=10).json()['items']
        if not any(line['auto_text'].strip() for line in lines):
            raise ValueError('Kraken no detectó texto en la imagen de prueba.')
        exported = post('/api/v1/exports', json={'document_id': doc, 'format': 'json'})
        wait(exported['job_id'])
        payload = session.get(origin + f"/api/v1/exports/{exported['job_id']}/download", timeout=10).json()
        assert payload['pages'] and payload['full_text'].strip()
        print(f'OK: CPU, Kraken, documento y JSON; {len(payload["pages"])} página(s), {len(lines)} renglones.', flush=True)
    finally:
        print('Retirando solo el stack aislado de prueba.', flush=True)
        down = run(compose + ['down', '--remove-orphans'], timeout=180, check=False)
        remaining = run(['docker', 'ps', '-aq', '--filter', f'label=com.docker.compose.project={project}'], check=False).stdout.strip()
        if down.returncode or remaining:
            print(f'No se pudo retirar todo; se conserva {temp}, proyecto {project}.', flush=True)
        else:
            for service in (*CORE, 'paddle'):
                tag = f'{project}-{service}'
                if not run(['docker', 'ps', '-aq', '--filter', 'ancestor=' + tag], check=False).stdout.strip():
                    run(['docker', 'image', 'rm', tag], check=False)
            assert temp.parent == root and temp.name.startswith('servator-cpu-qa-') and not temp.is_symlink()
            shutil.rmtree(temp)
            print('Stack y archivos temporales propios retirados; no se borraron volúmenes.', flush=True)


if __name__ == '__main__':
    main()
