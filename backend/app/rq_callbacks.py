def failed(job, connection, type, value, traceback):
    try:
        from app import create_app
        app = create_app()
        with app.app_context():
            from app.extensions import db
            from app.models import Job
            j = Job.query.get(job.args[0] if job.args else "")
            if j and j.status not in ("COMPLETED", "CANCELLED"):
                j.status = "FAILED"
                j.error = str(value)[:2000]
                db.session.commit()
    except Exception:
        pass
