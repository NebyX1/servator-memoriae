"""Descarga verificable y reanudable de PaddleOCR-VL-1.6 y su modelo de layout."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import shutil
import time

import requests

MANIFEST = json.loads((Path(__file__).parent / 'paddle_asset_manifest.json').read_text(encoding='utf-8'))
REVISION = MANIFEST[0]['revision']
TOTAL_BYTES = sum(item['size'] for repo in MANIFEST for item in repo['files'])


def model_dir():
    return Path(os.environ.get('MODEL_DIR', './data/models')) / 'paddleocr-vl-1.6'


def _check(path, item):
    if not path.is_file() or path.is_symlink() or path.stat().st_size != item['size']:
        return False
    digest = hashlib.sha256() if item['sha256'] else hashlib.sha1()
    if not item['sha256']:
        digest.update(f"blob {item['size']}\0".encode())
    with path.open('rb') as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest() == (item['sha256'] or item['git_sha1'])


def verified_assets(directory=None):
    root = Path(directory or model_dir())
    try:
        metadata = json.loads((root / 'servator-manifest.json').read_text(encoding='utf-8'))
        if metadata != MANIFEST:
            return False
        for repo in MANIFEST:
            for item in repo['files']:
                path = root / repo['directory'] / item['name']
                if path.is_symlink() or not path.is_file() or path.stat().st_size != item['size']:
                    return False
        return True
    except (OSError, ValueError, TypeError):
        return False


def _fetch(url, dest, item, done, total, progress):
    """Descarga cada rango por separado y comprueba el archivo antes de activarlo."""
    size = item['size']
    chunk_size = 16 * 1024 * 1024
    ranges = [(start, min(size - 1, start + chunk_size - 1)) for start in range(0, size, chunk_size)]
    if not ranges:  # los repositorios actuales no tienen archivos vacíos
        dest.write_bytes(b'')
        return
    def fetch(span):
        start, end = span
        part = dest.with_name(dest.name + f'.part-{start}')
        if part.is_file() and not part.is_symlink() and part.stat().st_size == end - start + 1:
            return part, end - start + 1
        for attempt in range(5):
            try:
                with requests.get(url, headers={'Range': f'bytes={start}-{end}'}, stream=True,
                                  timeout=(30, 120)) as response:
                    response.raise_for_status()
                    expected = f'bytes {start}-{end}/'
                    if response.status_code == 200 and start == 0 and end == size - 1:
                        pass
                    elif response.status_code != 206 or not response.headers.get('Content-Range', '').startswith(expected):
                        raise IOError('El servidor devolvió un rango inesperado.')
                    with part.open('wb') as out:
                        for block in response.iter_content(1024 * 1024):
                            if block:
                                out.write(block)
                if part.stat().st_size != end - start + 1:
                    raise IOError('La descarga de un fragmento quedó incompleta.')
                return part, end - start + 1
            except (requests.RequestException, OSError) as exc:
                if attempt == 4:
                    raise RuntimeError('No se pudo completar la descarga: ' + str(exc)[:220]) from exc
                time.sleep(2 * (attempt + 1))
    paths = {}
    with ThreadPoolExecutor(max_workers=min(8, len(ranges))) as pool:
        futures = {pool.submit(fetch, span): span for span in ranges}
        for future in as_completed(futures):
            path, count = future.result()
            paths[futures[future][0]] = path
            done += count
            if progress:
                progress(done, total, f"Descargando {item['name']}")
    tmp = dest.with_name(dest.name + '.assembling')
    with tmp.open('wb') as out:
        for start, _ in ranges:
            with paths[start].open('rb') as source:
                shutil.copyfileobj(source, out, 4 * 1024 * 1024)
    if not _check(tmp, item):
        raise ValueError(f"{item['name']} no pasó la verificación de integridad.")
    os.replace(tmp, dest)
    for part in paths.values():
        part.unlink()


def ensure_assets(directory=None, progress=None):
    root = Path(directory or model_dir())
    root.mkdir(parents=True, exist_ok=True)
    if verified_assets(root):
        if progress:
            progress(TOTAL_BYTES, TOTAL_BYTES, 'Archivos verificados')
        return root
    missing = [item['size'] for repo in MANIFEST for item in repo['files']
               if not (root / repo['directory'] / item['name']).exists()]
    required = sum(missing)
    # El archivo mayor coexiste un momento con sus fragmentos durante el ensamblado.
    if shutil.disk_usage(root).free < required + max(missing, default=0) + 256 * 1024 * 1024:
        raise OSError('No hay espacio suficiente para preparar PaddleOCR-VL y sus archivos temporales.')
    completed = 0
    for repo in MANIFEST:
        target = root / repo['directory']
        target.mkdir(exist_ok=True)
        for item in repo['files']:
            dest = target / item['name']
            if dest.exists():
                if not _check(dest, item):
                    raise ValueError(f"El archivo existente {item['name']} no coincide con la versión oficial; se conservó.")
            else:
                url = f"https://huggingface.co/{repo['repository']}/resolve/{repo['revision']}/{item['name']}?download=true"
                _fetch(url, dest, item, completed, TOTAL_BYTES, progress)
            completed += item['size']
            if progress:
                progress(completed, TOTAL_BYTES, 'Verificando archivos oficiales')
    marker = root / 'servator-manifest.json'
    tmp = marker.with_suffix('.part')
    tmp.write_text(json.dumps(MANIFEST, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, marker)
    return root


if __name__ == '__main__':
    last = [0]
    def report(done, total, phase):
        if done == total or done - last[0] >= 128 * 1024 * 1024:
            print(f'{phase}: {done // 1048576} / {total // 1048576} MiB', flush=True)
            last[0] = done
    print('Archivos listos:', ensure_assets(progress=report), flush=True)
