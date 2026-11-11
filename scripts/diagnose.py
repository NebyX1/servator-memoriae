"""Diagnóstico del entorno: OS/arch, docker, CPU/RAM/disco, GPU nvidia-smi,
torch/cuda, inferencia del modelo. Salida texto + JSON (stdout JSON con --json)."""
import argparse, json, os, platform, shutil, subprocess, sys


def configured_device():
    """Refleja .env cuando se ejecuta el diagnóstico fuera del bootstrap."""
    if os.environ.get('DEVICE_MODE'):
        return os.environ['DEVICE_MODE']
    try:
        with open('.env', encoding='utf-8-sig') as stream:
            for line in stream:
                key, separator, value = line.partition('=')
                if separator and key.strip() == 'DEVICE_MODE':
                    return value.strip().strip('\"\'')
    except OSError:
        pass
    return None


def sh(cmd, timeout=15):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=isinstance(cmd, str))
        return {"ok": p.returncode == 0, "out": (p.stdout or "").strip()[:4000], "err": (p.stderr or "").strip()[-1000:], "code": p.returncode}
    except FileNotFoundError as e:
        return {"ok": False, "out": "", "err": str(e)[:500], "code": 127}
    except Exception as e:
        return {"ok": False, "out": "", "err": str(e)[:500], "code": 1}


def diagnose():
    rep = {}
    rep["os"] = {"system": platform.system(), "release": platform.release(), "version": platform.version(), "arch": platform.machine(), "python": sys.version.split()[0]}
    try:
        import psutil
        rep["cpu"] = {"count_logical": psutil.cpu_count(), "count_physical": psutil.cpu_count(logical=False)}
        vm = psutil.virtual_memory()
        rep["ram"] = {"total_gb": round(vm.total / 1e9, 2), "available_gb": round(vm.available / 1e9, 2)}
        du = psutil.disk_usage(os.getcwd())
        rep["disk"] = {"total_gb": round(du.total / 1e9, 2), "free_gb": round(du.free / 1e9, 2)}
    except ImportError:
        import multiprocessing
        rep["cpu"] = {"count_logical": multiprocessing.cpu_count()}
        rep["ram"] = {"note": "psutil no instalado"}
        rep["disk"] = {"note": "psutil no instalado"}
    rep["docker"] = sh(["docker", "version", "--format", "{{.Server.Version}}"] if shutil.which("docker") else ["docker", "--version"])
    rep["compose"] = sh(["docker", "compose", "version"])
    rep["nvidia_smi"] = sh(["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv"])
    rep["nvcc"] = sh(["nvcc", "--version"]) if shutil.which("nvcc") else {"ok": False, "out": "", "err": "nvcc no encontrado", "code": 127}
    try:
        import torch
        rep["torch"] = {"version": torch.__version__, "cuda_available": torch.cuda.is_available(),
                        "cuda_version": getattr(torch.version, "cuda", None),
                        "devices": torch.cuda.device_count() if torch.cuda.is_available() else 0,
                        "names": [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())] if torch.cuda.is_available() else []}
    except ImportError as e:
        rep["torch"] = {"ok": False, "err": f"torch no instalado: {e}"}
    except Exception as e:
        rep["torch"] = {"ok": False, "err": str(e)[:500]}
    # inferencia: smoke del adaptador si hay pesos
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
        import kraken_adapter
        md = os.environ.get("MODEL_DIR", "./data/models")
        w = kraken_adapter.weights_path("v1")
        if os.path.isfile(w):
            try:
                r = kraken_adapter.smoke_test("v1")
                rep["inference"] = {"model": w, "smoke": r}
            except Exception as e:
                rep["inference"] = {"model": w, "ok": False, "err": str(e)[:500]}
        else:
            rep["inference"] = {"model": w, "ok": False, "err": "pesos no descargados (job prepare_model pendiente)"}
    except Exception as e:
        rep["inference"] = {"ok": False, "err": str(e)[:500]}
    # El modelo y sus dependencias suelen vivir dentro del worker, no en el host.
    # Conservar ambos resultados evita interpretar un host sin torch como fallo Docker.
    if rep["docker"]["ok"]:
        cmd = ["docker", "compose", "exec", "-T", "worker", "python", "-c",
               "import json,kraken_adapter; print('SERVATOR_SMOKE='+json.dumps(kraken_adapter.smoke_test('v1'))) "]
        result = sh(cmd, timeout=180)
        smoke_line = next((line for line in result["out"].splitlines() if line.startswith("SERVATOR_SMOKE=")), None)
        if result["ok"] and smoke_line:
            try:
                rep["inference"] = {"environment": "docker worker", "smoke": json.loads(smoke_line.split("=", 1)[1])}
            except ValueError:
                rep["inference"] = {"environment": "docker worker", "ok": False, "err": "respuesta de inferencia inválida"}
        else:
            rep["inference"] = {"environment": "docker worker", "ok": False,
                                "err": result["err"][-1000:] or result["out"][-1000:] or "worker no disponible"}
        gpu_compose = ["docker", "compose", "-f", "docker-compose.yml", "-f", "docker-compose.gpu.yml"]
        gpu_running = sh(gpu_compose + ["ps", "-q", "worker-gpu"])
        if gpu_running["ok"] and gpu_running["out"]:
            probe = sh(gpu_compose + ["exec", "-T", "worker-gpu", "python", "-c",
                "import json,torch; ok=torch.cuda.is_available(); print('SERVATOR_GPU='+json.dumps({'cuda_available':ok,'torch':torch.__version__,'cuda_version':torch.version.cuda,'name':torch.cuda.get_device_name(0) if ok else None}))"], timeout=40)
            line = next((item for item in probe["out"].splitlines() if item.startswith("SERVATOR_GPU=")), None)
            if probe["ok"] and line:
                try:
                    rep["gpu_worker"] = json.loads(line.split("=", 1)[1])
                except ValueError:
                    rep["gpu_worker"] = {"cuda_available": False, "err": "respuesta de GPU inválida"}
            else:
                rep["gpu_worker"] = {"cuda_available": False, "err": probe["err"] or "worker GPU no disponible"}
        else:
            rep["gpu_worker"] = {"cuda_available": False, "note": "worker GPU no iniciado"}
        paddle_probe = sh(["docker", "compose", "exec", "-T", "backend", "python", "-c",
            "import json; from wsgi import app; from app.services_paddle import paddle_status; "
            "ctx=app.app_context(); ctx.push(); print('SERVATOR_PADDLE='+json.dumps(paddle_status()))"], timeout=20)
        paddle_line = next((line for line in paddle_probe['out'].splitlines() if line.startswith('SERVATOR_PADDLE=')), None)
        if paddle_probe['ok'] and paddle_line:
            try:
                rep['paddle'] = json.loads(paddle_line.split('=', 1)[1])
            except ValueError:
                rep['paddle'] = {'ready': False, 'err': 'Respuesta inválida'}
        else:
            rep['paddle'] = {'ready': False, 'err': paddle_probe['err'] or 'No se pudo consultar el backend'}
    rep["env"] = {"device_file": open(".device").read().strip() if os.path.isfile(".device") else None,
                  "DEVICE_MODE": configured_device()}
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    rep = diagnose()
    txt = json.dumps(rep, indent=2, ensure_ascii=False)
    if a.json:
        print(txt)
    else:
        print("== Servator Memoriae: diagnóstico ==")
        print(f"OS: {rep['os']['system']} {rep['os']['release']} ({rep['os']['arch']}) py={rep['os']['python']}")
        print(f"CPU: {rep.get('cpu')}  RAM: {rep.get('ram')}  DISCO: {rep.get('disk')}")
        print(f"docker: {rep['docker'].get('out') or rep['docker'].get('err')}")
        print(f"compose: {rep['compose'].get('out') or rep['compose'].get('err')}")
        print(f"nvidia-smi ok={rep['nvidia_smi']['ok']}: {(rep['nvidia_smi'].get('out') or rep['nvidia_smi'].get('err'))[:300]}")
        print(f"torch: {json.dumps(rep.get('torch'), ensure_ascii=False)[:400]}")
        print(f"worker GPU: {json.dumps(rep.get('gpu_worker'), ensure_ascii=False)[:400]}")
        print(f"PaddleOCR-VL: {json.dumps(rep.get('paddle'), ensure_ascii=False)[:600]}")
        print(f"inferencia: {json.dumps(rep.get('inference'), ensure_ascii=False)[:600]}")
        print(f"device: {rep.get('env')}")
        print("---- JSON ----")
        print(txt)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(txt)


if __name__ == "__main__":
    main()
