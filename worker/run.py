"""RQ worker con scheduler (idempotente, re-ejecución segura)."""
import argparse, json, os, subprocess, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))


def device_metadata():
    """Comprueba CUDA en otro proceso para no inicializarlo antes del fork de RQ."""
    if os.environ.get("DEVICE_MODE", "cpu") != "cuda":
        return {"servator_device": "cpu"}
    script = (
        "import json,torch; "
        "assert torch.cuda.is_available(), 'CUDA no está disponible'; "
        "x=torch.zeros(1,device='cuda'); x.add_(1); torch.cuda.synchronize(); "
        "print(json.dumps({'name':torch.cuda.get_device_name(0),'cuda':torch.version.cuda}))"
    )
    try:
        probe = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=120, check=True)
        info = json.loads(probe.stdout.strip().splitlines()[-1])
    except (OSError, subprocess.SubprocessError, IndexError, ValueError) as exc:
        raise RuntimeError("No se pudo inicializar la GPU NVIDIA en este worker.") from exc
    return {"servator_device": "cuda", "servator_cuda_ready": "1", "servator_gpu_name": info["name"],
            "servator_cuda_version": info.get("cuda") or ""}


def main():
    ap = argparse.ArgumentParser(description="Servator RQ worker")
    ap.add_argument("--queue", default=os.environ.get("RQ_QUEUE", "servator"))
    ap.add_argument("--burst", action="store_true")
    args = ap.parse_args()

    os.chdir(os.path.join(os.path.dirname(__file__), "..", "backend"))
    sys.path.insert(0, os.getcwd())

    import redis
    from rq import Queue, Worker

    metadata = device_metadata()

    class DeviceWorker(Worker):
        def bootstrap(self, *args, **kwargs):
            super().bootstrap(*args, **kwargs)
            self.connection.hset(self.key, mapping=metadata)

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    conn = redis.Redis.from_url(redis_url)
    conn.ping()

    queues = [Queue(q.strip(), connection=conn) for q in args.queue.split(",") if q.strip()]
    print(f"[worker] escuchando {args.queue} ({metadata['servator_device']})", flush=True)
    w = DeviceWorker(queues, connection=conn, default_worker_ttl=90, job_monitoring_interval=20)
    # rq>=1.16: scheduler incorporado vía parámetro
    try:
        w.work(with_scheduler=True, burst=args.burst)
    except TypeError:
        # rq antiguo: with_scheduler no soportado
        w.work(burst=args.burst)


if __name__ == "__main__":
    main()
