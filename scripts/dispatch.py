"""Dispatcher: mueve jobs PENDING -> cola RQ. Idempotente, loop con backoff."""
import os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
# Candidatos según entorno: repo host (scripts/../backend), backend image (/app),
# worker image (/app/backend). Se usa el primero que contenga wsgi.py.
_CANDS = [os.path.join(os.path.dirname(HERE), "backend"), HERE, "/app", "/app/backend"]
for _c in _CANDS:
    if _c and os.path.isdir(_c) and _c not in sys.path:
        sys.path.insert(0, _c)
for _c in _CANDS:
    if _c and os.path.isfile(os.path.join(_c, "wsgi.py")):
        os.chdir(_c)
        break


def scan_once(app):
    from app.models import Job
    from app.services_queue import dispatch as rq_dispatch
    from app.extensions import db
    with app.app_context():
        pend = Job.query.filter_by(status="PENDING").order_by(Job.created_at).limit(20).all()
        for j in pend:
            try:
                rq_dispatch(j)
                print(f"[dispatch] {j.id} -> {j.status}", flush=True)
            except Exception as e:
                print(f"[dispatch] {j.id} error: {e}", flush=True)
                db.session.rollback()
        return len(pend)


def main():
    from wsgi import app
    idle = 0
    print("[dispatch] loop iniciado", flush=True)
    while True:
        try:
            n = scan_once(app)
            idle = 0 if n else idle + 1
            time.sleep(2 if n else min(30, 5 + idle))
        except Exception as e:
            print(f"[dispatch] ciclo fallido: {e}", flush=True)
            time.sleep(10)


if __name__ == "__main__":
    main()
