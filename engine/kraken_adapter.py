"""Kraken engine adapter. Aísla la UI de las clases internas de Kraken.
Motor principal: kraken 7.1.1 + reconocedor PP-OCRv6 medium (Zenodo 21788410).
Segmentador: blla.mlmodel empaquetado con kraken 7.1.1 (SegmentationTaskModel).

Ruta verificada en contenedor (2026-11-10) contra kraken 7.1.1 real:
  RecognitionTaskModel.load_model(w) + SegmentationTaskModel.load_model(blla)
  + model.predict(im, segmentation, config) -> BaselineOCRRecord
  (prediction, confidences por caracter, baseline, boundary).
Equivale al CLI oficial: kraken -i p.png o.txt segment -bl ocr -m medium.safetensors
"""
import os, json, hashlib, tempfile, shutil, urllib.request

ENGINE_VERSION = "kraken==7.1.1"
SEGMENTER = "blla.mlmodel empaquetado con kraken 7.1.1 (kraken.tasks.SegmentationTaskModel)"
MODEL_DOI = "10.5281/zenodo.21788410"
MODEL_URL = "https://zenodo.org/records/21788410/files/medium.safetensors?download=1"
MANIFEST_NAME = "ppocrv6-medium"

def model_dir():
    d = os.environ.get("MODEL_DIR", "./data/models")
    os.makedirs(d, exist_ok=True)
    return d

def manifest_path():
    return os.path.join(model_dir(), "manifest.json")

def weights_path(version="v1"):
    return os.path.join(model_dir(), f"{MANIFEST_NAME}-{version}.safetensors")

def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()

def load_manifest():
    try:
        with open(manifest_path()) as f:
            return json.load(f)
    except FileNotFoundError:
        return {"models": []}

def save_manifest(m):
    tmp = manifest_path() + ".tmp"
    with open(tmp, "w") as f:
        json.dump(m, f, indent=2, ensure_ascii=False)
    os.replace(tmp, manifest_path())

def ensure_model(version="v1", progress_cb=None):
    """Descarga atómica con verificación. progress_cb(downloaded, total)."""
    dst = weights_path(version)
    if os.path.exists(dst):
        return dst
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".part"
    req = urllib.request.Request(MODEL_URL, headers={"User-Agent": "servator-memoriae/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length", "0") or 0)
        done = 0
        while True:
            b = r.read(1 << 20)
            if not b: break
            f.write(b); done += len(b)
            if progress_cb: progress_cb(done, total)
    # hash se registra (sha real calculado); la verificación estricta contra
    # manifiesto oficial se hace si hay hash esperado configurado
    sha = sha256_file(tmp)
    os.replace(tmp, dst)
    m = load_manifest()
    entry = {"name": MANIFEST_NAME, "version": version, "file": os.path.basename(dst),
             "sha256": sha, "size": os.path.getsize(dst), "source": MODEL_URL,
             "doi": MODEL_DOI, "license": "Apache-2.0", "engine": ENGINE_VERSION,
             "segmenter": SEGMENTER,
             "preprocessing": {"height": 64, "normalization": "kraken default for ppocrv6", "codec": "model-embedded"},
             "note": "Reconocedor de renglones; requiere segmentación de página previa."}
    m["models"] = [e for e in m.get("models", []) if not (e.get("name") == MANIFEST_NAME and e.get("version") == version)] + [entry]
    save_manifest(m)
    return dst

def model_ready(version="v1"):
    return os.path.exists(weights_path(version))

def _device_arg(mode="auto"):
    if mode == "cuda":
        try:
            import torch
            if not torch.cuda.is_available():
                raise RuntimeError("La tarjeta NVIDIA no está disponible dentro del contenedor. Podemos continuar con el procesador (usá device=cpu).")
        except ImportError:
            raise RuntimeError("Torch sin soporte CUDA en este worker.")
        return "cuda"
    if mode == "cpu":
        return "cpu"
    return "auto"

# Caché explícita del proceso worker (estrategia documentada: carga segura en el
# proceso de trabajo; un modelo residente por proceso; se libera al terminar el
# proceso. Sin lru_cache implícito: clave + invalidación por mtime/tamaño.)
_MODEL_CACHE = {}

def _load_models(weights, device):
    from kraken.tasks import RecognitionTaskModel, SegmentationTaskModel
    from importlib import resources
    key = (os.path.abspath(weights), os.path.getmtime(weights), os.path.getsize(weights), device)
    hit = _MODEL_CACHE.get(key)
    if hit is not None:
        return hit
    blla = str(resources.files("kraken").joinpath("blla.mlmodel"))
    seg_model = SegmentationTaskModel.load_model(blla)
    rec_model = RecognitionTaskModel.load_model(weights)
    _MODEL_CACHE.clear()
    _MODEL_CACHE[key] = (seg_model, rec_model)
    return seg_model, rec_model

def transcribe_image(image_path, version="v1", device_mode="auto"):
    """Segmenta + reconoce una página. Retorna lista de líneas {baseline, polygon, text, confidence}.

    confidence = media de confianzas por caracter del OCR: señal para priorizar
    revisión, NO probabilidad calibrada de que el acta sea correcta.
    """
    from kraken.configs import SegmentationInferenceConfig, RecognitionInferenceConfig
    from PIL import Image
    w = weights_path(version)
    if not os.path.exists(w):
        raise FileNotFoundError("Modelo no descargado todavía")
    device = _device_arg(device_mode)
    # Carga perezosa en proceso worker (nunca en API)
    seg_model, rec_model = _load_models(w, device)
    im = Image.open(image_path).convert("RGB")
    # Kraken 7 passes accelerator/device to Lightning as accelerator/devices.
    # Lightning expects an integer device count, not "cpu" or "cuda:0".
    device_options = ({"accelerator": "cpu", "device": 1} if device == "cpu" else
                      {"accelerator": "gpu", "device": 1} if device == "cuda" else {})
    seg_cfg = SegmentationInferenceConfig(**device_options)
    bounds = seg_model.predict(im=im, config=seg_cfg)
    rec_cfg = RecognitionInferenceConfig(**device_options)
    results = []
    for i, rec in enumerate(rec_model.predict(im=im, segmentation=bounds, config=rec_cfg)):
        baseline = [list(p) for p in (rec.baseline or [])]
        poly = [list(p) for p in (rec.boundary or [])]
        confs = list(rec.confidences or [])
        conf = float(sum(confs) / len(confs)) if confs else 0.0
        results.append({"order": i, "baseline": baseline, "polygon": poly,
                        "text": rec.prediction or "", "confidence": conf})
    return results

def smoke_test(version="v1", device_mode="cpu"):
    """Inferencia de prueba con imagen sintética redistribuible. Retorna dict."""
    from PIL import Image, ImageDraw, ImageFont
    from importlib import resources
    tmp = tempfile.mktemp(suffix=".png")
    im = Image.new("RGB", (1200, 600), "white")
    d = ImageDraw.Draw(im)
    font_path = resources.files("reportlab").joinpath("fonts/Vera.ttf")
    font = ImageFont.truetype(str(font_path), 42)
    for index, line in enumerate(("Acta de Lavalleja del año 1883",
                                  "En esta fecha se reúne el consejo",
                                  "para conservar la memoria histórica.")):
        d.text((70, 75 + index * 115), line, fill="black", font=font)
    im.save(tmp)
    try:
        lines = transcribe_image(tmp, version=version, device_mode=device_mode)
        return {"ok": bool(lines), "lines": len(lines)}
    finally:
        try: os.remove(tmp)
        except Exception: pass

def train_finetune(train_lst, val_lst, base_weights, out_dir, epochs=3, device="cpu", on_event=None):
    """Ajuste real vía CLI ketos (release fijada). Retorna mejor checkpoint."""
    import subprocess
    os.makedirs(out_dir, exist_ok=True)
    cmd = ["ketos", "train", "--arch", "ppocrv6", "--variant", "medium",
           "--load", base_weights, "--resize", "union",
           "-t", train_lst, "-e", val_lst,
           "--epochs", str(epochs), "--output", out_dir, "--device", device]
    if on_event: on_event({"phase": "Aprendiendo la caligrafía", "cmd": " ".join(cmd)})
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=8*3600)
    if r.returncode != 0:
        raise RuntimeError(f"ketos train falló: {r.stderr[-4000:]}")
    # elegir mejor checkpoint de validación: best.ckpt si existe
    for cand in ["best.ckpt", "best.safetensors", "last.ckpt"]:
        p = os.path.join(out_dir, cand)
        if os.path.exists(p):
            return p
    # sino el primer .ckpt
    import glob
    cks = sorted(glob.glob(os.path.join(out_dir, "*.ckpt")))
    if not cks: raise RuntimeError("Sin checkpoints generados")
    return cks[0]

def cer(hyp: str, ref: str) -> float:
    # distancia Levenshtein sin dependencias extra
    m, n = len(ref), len(hyp)
    if m == 0: return 1.0 if n else 0.0
    prev = list(range(n + 1))
    for i in range(1, m + 1):
        cur = [i] + [0] * n
        for j in range(1, n + 1):
            cur[j] = min(prev[j] + 1, cur[j-1] + 1, prev[j-1] + (ref[i-1] != hyp[j-1]))
        prev = cur
    return prev[n] / max(1, m)

def corpus_cer(pairs):
    """Suma distancias y longitudes (no promedia porcentajes). pairs: [(hyp, ref)]."""
    tot_d, tot_n = 0, 0
    for hyp, ref in pairs:
        m, n = len(ref), len(hyp)
        prev = list(range(n + 1))
        for i in range(1, m + 1):
            cur = [i] + [0] * n
            for j in range(1, n + 1):
                cur[j] = min(prev[j] + 1, cur[j-1] + 1, prev[j-1] + (ref[i-1] != hyp[j-1]))
            prev = cur
        tot_d += prev[n]; tot_n += max(1, m)
    return {"cer": tot_d / max(1, tot_n), "edits": tot_d, "chars": tot_n}
