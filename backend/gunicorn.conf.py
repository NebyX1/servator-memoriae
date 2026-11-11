import multiprocessing, os

bind = "0.0.0.0:5000"
workers = int(os.environ.get("GUNICORN_WORKERS", "2"))
worker_class = "sync"
timeout = 300
graceful_timeout = 60
keepalive = 30
max_requests = 500
max_requests_jitter = 50
loglevel = os.environ.get("GUNICORN_LOGLEVEL", "info")
accesslog = "-"
errorlog = "-"
preload_app = False
