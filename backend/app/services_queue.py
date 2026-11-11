"""Transactional outbox + RQ dispatch."""
import uuid, datetime
from flask import current_app


def queue_for_job(job, settings):
    """Send inference to the configured device; ordinary work stays on CPU."""
    if job.kind == 'prepare_paddle':
        return 'servator-setup'
    if job.kind in ("transcribe", "prepare_model"):
        requested = (job.payload or {}).get("device", "auto")
        device = settings.DEVICE_MODE if requested == "auto" else requested
        if device == "cuda" and (job.kind == "transcribe" or settings.DEVICE_MODE == "cuda"):
            import os
            return os.environ.get("RQ_GPU_QUEUE", "servator-gpu")
    return settings.RQ_QUEUE

def new_job(kind, user_id, payload, idem_key="", total=0):
    from app.extensions import db
    from app.models import Job
    job = Job(id=str(uuid.uuid4()), kind=kind, user_id=user_id, payload=payload or {},
              status="PENDING", idempotency_key=idem_key or str(uuid.uuid4()),
              progress_total=total, phase="en cola")
    # idempotency: return existing if same user/kind/key
    ex = Job.query.filter_by(user_id=user_id, kind=kind, idempotency_key=job.idempotency_key).first()
    if ex:
        if ex.payload != job.payload:
            raise ValueError("Conflicto de idempotencia")
        return ex
    db.session.add(job)
    db.session.commit()
    return job

def dispatch(job):
    """Enqueue to Redis RQ; on Redis failure keep PENDING for dispatcher."""
    from app.extensions import db
    try:
        import redis
        from rq import Queue, Retry
        from app.config import settings
        s = settings()
        r = redis.Redis.from_url(s.REDIS_URL, socket_timeout=5)
        q = Queue(queue_for_job(job, s), connection=r)
        q.enqueue("app.tasks.execute_job", job.id, job_timeout=6*3600, retry=Retry(max=1, interval=30),
                  on_failure="app.rq_callbacks.failed")
        job.status = "QUEUED"
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        job.status = "PENDING"
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
        current_app.logger.warning(f"Redis no disponible, job {job.id} queda PENDING: {e}")

def emit(job_id, kind, data):
    from app.extensions import db
    from app.models import JobEvent, Job
    import datetime
    job = Job.query.get(job_id)
    if not job: return
    n = JobEvent.query.filter_by(job_id=job_id).count()
    db.session.add(JobEvent(id=__import__("uuid").uuid4().hex, job_id=job_id, seq=n, kind=kind, data=data or {}))
    job.heartbeat_at = datetime.datetime.utcnow()
    db.session.commit()

def progress(job_id, done, total=None, phase=None):
    from app.extensions import db
    from app.models import Job
    job = Job.query.get(job_id)
    if not job: return
    if job.cancel_requested:
        raise Cancelled()
    job.progress_done = done
    if total is not None: job.progress_total = total
    if phase: job.phase = phase
    import datetime
    job.heartbeat_at = datetime.datetime.utcnow()
    db.session.commit()
    emit(job_id, "progress", {"done": done, "total": job.progress_total, "phase": job.phase})

class Cancelled(Exception):
    pass
