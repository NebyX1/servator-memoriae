"""Servator Memoriae settings. Fail-closed in production."""
import os
from dataclasses import dataclass

def _req(name: str, default: str | None = None) -> str:
    v = os.environ.get(name, default)
    if v is None or v == "":
        raise RuntimeError(f"Missing required env {name}")
    return v

@dataclass
class Settings:
    ENV: str
    LOCAL_TEST_MODE: bool
    SECRET_KEY: str
    DATABASE_URL: str
    REDIS_URL: str
    S3_ENDPOINT: str
    S3_ACCESS_KEY: str
    S3_SECRET_KEY: str
    S3_BUCKET: str
    S3_REGION: str
    S3_USE_LOCAL: bool
    DATA_DIR: str
    MODEL_DIR: str
    MODEL_CACHE_DIR: str
    MAX_UPLOAD_MB: int
    MAX_PAGES_PER_FILE: int
    DEVICE_MODE: str  # auto|cpu|cuda
    RQ_QUEUE: str
    CORS_ORIGINS: str

def settings() -> Settings:
    env = os.environ.get("FLASK_ENV", "development")
    local_test_mode = os.environ.get("LOCAL_TEST_MODE", "0") == "1"
    if local_test_mode and env not in ("development", "testing"):
        raise RuntimeError("LOCAL_TEST_MODE requiere FLASK_ENV=development o testing")
    if local_test_mode and os.environ.get("FRONT_BIND", "127.0.0.1") != "127.0.0.1":
        raise RuntimeError("LOCAL_TEST_MODE requiere FRONT_BIND=127.0.0.1")
    secret = os.environ.get("SECRET_KEY", "dev-only-" + "x" * 32)
    if env == "production":
        if os.environ.get("DEV_AUTH_BYPASS"):
            raise RuntimeError("DEV_AUTH_BYPASS forbidden in production")
        if len(secret) < 32:
            raise RuntimeError("SECRET_KEY must be >=32 chars in production")
        db = _req("DATABASE_URL")
    else:
        db = os.environ.get("DATABASE_URL", "sqlite:///dev.db")
    return Settings(
        ENV=env,
        LOCAL_TEST_MODE=local_test_mode,
        SECRET_KEY=secret,
        DATABASE_URL=db,
        REDIS_URL=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        S3_ENDPOINT=os.environ.get("S3_ENDPOINT", ""),
        S3_ACCESS_KEY=os.environ.get("S3_ACCESS_KEY", "minioadmin"),
        S3_SECRET_KEY=os.environ.get("S3_SECRET_KEY", "minioadmin"),
        S3_BUCKET=os.environ.get("S3_BUCKET", "servator"),
        S3_REGION=os.environ.get("S3_REGION", "us-east-1"),
        S3_USE_LOCAL=os.environ.get("S3_USE_LOCAL", "1") == "1",
        DATA_DIR=os.environ.get("DATA_DIR", "./data"),
        MODEL_DIR=os.environ.get("MODEL_DIR", "./data/models"),
        MODEL_CACHE_DIR=os.environ.get("MODEL_CACHE_DIR", "./data/models/cache"),
        MAX_UPLOAD_MB=int(os.environ.get("MAX_UPLOAD_MB", "512")),
        MAX_PAGES_PER_FILE=int(os.environ.get("MAX_PAGES_PER_FILE", "500")),
        DEVICE_MODE=os.environ.get("DEVICE_MODE", "auto"),
        RQ_QUEUE=os.environ.get("RQ_QUEUE", "servator"),
        CORS_ORIGINS=os.environ.get("CORS_ORIGINS", "http://localhost:8787,http://localhost:5173"),
    )
