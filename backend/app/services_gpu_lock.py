"""Exclusión entre lectores que comparten la GPU, renovable ante trabajos largos."""
from contextlib import contextmanager
import threading


@contextmanager
def resource_guard(name, enabled=True):
    if not enabled:
        yield
        return
    import redis
    from app.config import settings
    conn = redis.Redis.from_url(settings().REDIS_URL, socket_connect_timeout=5, socket_timeout=5)
    lock = conn.lock('servator:' + name, timeout=120, blocking_timeout=600, thread_local=False)
    if not lock.acquire():
        raise ValueError('El componente de lectura está ocupado. Volvé a intentarlo.')
    stop = threading.Event()
    def renew():
        while not stop.wait(30):
            try:
                lock.extend(120, replace_ttl=True)
            except Exception:
                break
    thread = threading.Thread(target=renew, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=5)
        try:
            lock.release()
        except Exception:
            pass


def gpu_guard(enabled):
    return resource_guard('gpu-inference', enabled)


def paddle_guard():
    return resource_guard('paddle-inference')
