"""Domain models for Servator Memoriae."""
import uuid, datetime
from flask_login import UserMixin
from app.extensions import db
from sqlalchemy import String, Text, Integer, Float, Boolean, DateTime, ForeignKey, JSON

def _uid():
    return str(uuid.uuid4())

class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.String(36), primary_key=True, default=_uid)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(512), nullable=False)
    role = db.Column(db.String(32), default="admin", nullable=False)
    is_active_ = db.Column("is_active", db.Boolean, default=True)
    session_version = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def get_id(self): return self.id
    @property
    def is_active(self): return bool(self.is_active_)

class Collection(db.Model):
    __tablename__ = "collections"
    id = db.Column(db.String(36), primary_key=True, default=_uid)
    title = db.Column(db.String(512), nullable=False)
    description = db.Column(db.Text, default="")
    owner_id = db.Column(db.String(36), db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class Document(db.Model):
    __tablename__ = "documents"
    id = db.Column(db.String(36), primary_key=True, default=_uid)
    title = db.Column(db.String(512), nullable=False)
    collection_id = db.Column(db.String(36), db.ForeignKey("collections.id"), nullable=True, index=True)
    doc_type = db.Column(db.String(128), default="libro")
    year_start = db.Column(db.Integer, nullable=True)
    year_end = db.Column(db.Integer, nullable=True)
    signature = db.Column(db.String(512), default="")
    description = db.Column(db.Text, default="")
    tags = db.Column(db.JSON, default=list)
    owner_id = db.Column(db.String(36), db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class SourceFile(db.Model):
    __tablename__ = "source_files"
    id = db.Column(db.String(36), primary_key=True, default=_uid)
    document_id = db.Column(db.String(36), db.ForeignKey("documents.id"), index=True)
    filename = db.Column(db.String(1024), nullable=False)
    sha256 = db.Column(db.String(64), nullable=False, index=True)
    size_bytes = db.Column(db.Integer, default=0)
    mime = db.Column(db.String(128), default="")
    storage_key = db.Column(db.String(2048), nullable=False)
    pages_detected = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class Page(db.Model):
    __tablename__ = "pages"
    id = db.Column(db.String(36), primary_key=True, default=_uid)
    document_id = db.Column(db.String(36), db.ForeignKey("documents.id"), index=True)
    source_file_id = db.Column(db.String(36), db.ForeignKey("source_files.id"), nullable=True)
    order_index = db.Column(db.Integer, nullable=False, default=0)
    folio = db.Column(db.String(64), default="")
    rotation = db.Column(db.Integer, default=0)
    crop = db.Column(db.JSON, nullable=True)
    width = db.Column(db.Integer, default=0)
    height = db.Column(db.Integer, default=0)
    image_key = db.Column(db.String(2048), default="")
    thumb_key = db.Column(db.String(2048), default="")
    status = db.Column(db.String(32), default="imported")  # imported|queued|processing|done|failed|needs_review
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class Line(db.Model):
    __tablename__ = "lines"
    id = db.Column(db.String(36), primary_key=True, default=_uid)
    page_id = db.Column(db.String(36), db.ForeignKey("pages.id"), index=True)
    order_index = db.Column(db.Integer, default=0)
    baseline = db.Column(db.JSON, default=list)
    polygon = db.Column(db.JSON, default=list)
    auto_text = db.Column(db.Text, default="")
    revised_text = db.Column(db.Text, nullable=True)
    confidence = db.Column(db.Float, default=0.0)
    state = db.Column(db.String(32), default="auto")  # auto|confirmed|corrected|illegible|bad_cut|skipped
    note = db.Column(db.Text, default="")
    version = db.Column(db.Integer, default=1)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class TranscriptionVersion(db.Model):
    __tablename__ = "transcription_versions"
    id = db.Column(db.String(36), primary_key=True, default=_uid)
    page_id = db.Column(db.String(36), db.ForeignKey("pages.id"), index=True)
    version = db.Column(db.Integer, default=1)
    engine = db.Column(db.String(128), default="")
    model_version = db.Column(db.String(128), default="")
    payload = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class OcrResult(db.Model):
    """Una propuesta inmutable por página, trabajo y motor."""
    __tablename__ = "ocr_results"
    id = db.Column(db.String(36), primary_key=True, default=_uid)
    page_id = db.Column(db.String(36), db.ForeignKey("pages.id"), nullable=False, index=True)
    job_id = db.Column(db.String(36), db.ForeignKey("jobs.id"), nullable=False, index=True)
    engine = db.Column(db.String(32), nullable=False)
    model_version = db.Column(db.String(128), nullable=False)
    device = db.Column(db.String(16), nullable=False)
    status = db.Column(db.String(16), nullable=False)
    text = db.Column(db.Text, nullable=True)
    details = db.Column(db.JSON, default=dict)
    error = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("page_id", "job_id", "engine", name="uq_ocr_result_page_job_engine"),)

class OcrReview(db.Model):
    """Historial de decisiones explícitas; nunca sobrescribe las propuestas."""
    __tablename__ = "ocr_reviews"
    id = db.Column(db.String(36), primary_key=True, default=_uid)
    page_id = db.Column(db.String(36), db.ForeignKey("pages.id"), nullable=False, index=True)
    job_id = db.Column(db.String(36), db.ForeignKey("jobs.id"), nullable=False)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    version = db.Column(db.Integer, nullable=False)
    source = db.Column(db.String(32), nullable=False)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("page_id", "version", name="uq_ocr_review_page_version"),)

class Job(db.Model):
    __tablename__ = "jobs"
    id = db.Column(db.String(36), primary_key=True, default=_uid)
    kind = db.Column(db.String(64), nullable=False)  # transcribe|export|train|prepare_model
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"))
    status = db.Column(db.String(32), default="PENDING")  # PENDING|QUEUED|RUNNING|COMPLETED|FAILED|CANCELLED
    payload = db.Column(db.JSON, default=dict)
    progress_done = db.Column(db.Integer, default=0)
    progress_total = db.Column(db.Integer, default=0)
    phase = db.Column(db.String(128), default="")
    error = db.Column(db.Text, default="")
    idempotency_key = db.Column(db.String(256), default="")
    cancel_requested = db.Column(db.Boolean, default=False)
    heartbeat_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("user_id", "kind", "idempotency_key", name="uq_job_idem"),)

class JobEvent(db.Model):
    __tablename__ = "job_events"
    id = db.Column(db.String(36), primary_key=True, default=_uid)
    job_id = db.Column(db.String(36), db.ForeignKey("jobs.id"), index=True)
    seq = db.Column(db.Integer, default=0)
    kind = db.Column(db.String(64), default="log")
    data = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class ModelVersion(db.Model):
    __tablename__ = "model_versions"
    id = db.Column(db.String(36), primary_key=True, default=_uid)
    name = db.Column(db.String(128), default="ppocrv6-medium")
    version = db.Column(db.String(64), nullable=False)
    kind = db.Column(db.String(32), default="recognizer")  # recognizer|segmenter
    weights_key = db.Column(db.String(2048), default="")
    sha256 = db.Column(db.String(64), default="")
    size_bytes = db.Column(db.Integer, default=0)
    source = db.Column(db.String(1024), default="")
    license = db.Column(db.String(128), default="")
    engine_version = db.Column(db.String(64), default="")
    active_for_collection = db.Column(db.String(36), nullable=True)
    is_active_global = db.Column(db.Boolean, default=False)
    metrics = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class TrainingRun(db.Model):
    __tablename__ = "training_runs"
    id = db.Column(db.String(36), primary_key=True, default=_uid)
    name = db.Column(db.String(512), default="")
    scope = db.Column(db.JSON, default=dict)
    status = db.Column(db.String(32), default="PENDING")
    config = db.Column(db.JSON, default=dict)
    snapshot = db.Column(db.JSON, default=dict)
    result_model_id = db.Column(db.String(36), nullable=True)
    metrics = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class Export(db.Model):
    __tablename__ = "exports"
    id = db.Column(db.String(36), primary_key=True, default=_uid)
    document_id = db.Column(db.String(36), nullable=True)
    collection_id = db.Column(db.String(36), nullable=True)
    format = db.Column(db.String(32), default="json")
    options = db.Column(db.JSON, default=dict)
    status = db.Column(db.String(32), default="PENDING")
    file_key = db.Column(db.String(2048), default="")
    summary = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class AuditLog(db.Model):
    __tablename__ = "audit_log"
    id = db.Column(db.String(36), primary_key=True, default=_uid)
    user_id = db.Column(db.String(36), nullable=True)
    action = db.Column(db.String(128), nullable=False)
    entity_id = db.Column(db.String(128), default="")
    details = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
