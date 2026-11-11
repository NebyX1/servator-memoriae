"""Local + S3-compatible storage with safe keys, streaming and quota."""
import os, hashlib
from pathlib import PurePosixPath

def safe_key(key: str) -> str:
    p = PurePosixPath(key)
    if p.is_absolute() or ".." in p.parts or "\\" in key:
        raise ValueError("Clave de objeto no válida")
    return str(p)

class ObjectStorage:
    def __init__(self, settings):
        self.s = settings
        self.root = os.path.abspath(os.environ.get("LOCAL_STORAGE_DIR", os.path.join(settings.DATA_DIR, "objects")))
        os.makedirs(self.root, exist_ok=True)
        self._s3 = None
        if not settings.S3_USE_LOCAL and settings.S3_ENDPOINT:
            import boto3
            self._s3 = boto3.client("s3", endpoint_url=settings.S3_ENDPOINT,
                aws_access_key_id=settings.S3_ACCESS_KEY, aws_secret_access_key=settings.S3_SECRET_KEY,
                region_name=settings.S3_REGION)

    def _local_path(self, key):
        key = safe_key(key)
        fp = os.path.join(self.root, *key.split("/"))
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        return fp

    def put_file(self, key, src_path):
        key = safe_key(key)
        if self._s3:
            self._s3.upload_file(src_path, self.s.S3_BUCKET, key)
            return key
        import shutil
        dst = self._local_path(key)
        shutil.copyfile(src_path, dst)
        return key

    def put_bytes(self, key, data: bytes):
        key = safe_key(key)
        if self._s3:
            import io
            import boto3
            self._s3.put_object(Bucket=self.s.S3_BUCKET, Key=key, Body=data)
            return key
        dst = self._local_path(key)
        with open(dst, "wb") as f:
            f.write(data)
        return key

    def get_path(self, key, tmp_path=None):
        """Return a local filesystem path for key (download if S3). Caller must not assume persistence of tmp."""
        key = safe_key(key)
        if self._s3:
            import tempfile
            dst = tmp_path or tempfile.mktemp()
            self._s3.download_file(self.s.S3_BUCKET, key, dst)
            return dst
        return self._local_path(key)

    def open_read(self, key):
        if self._s3:
            r = self._s3.get_object(Bucket=self.s.S3_BUCKET, Key=key)
            return r["Body"]
        return open(self._local_path(key), "rb")

    def delete(self, key):
        key = safe_key(key)
        if self._s3:
            self._s3.delete_object(Bucket=self.s.S3_BUCKET, Key=key)
            return
        try:
            os.remove(self._local_path(key))
        except FileNotFoundError:
            pass
