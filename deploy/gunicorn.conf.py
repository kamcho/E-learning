"""Gunicorn config: gunicorn process master + uvicorn (ASGI/async) workers.

Run with:  gunicorn -c deploy/gunicorn.conf.py Elearning.asgi:application
"""
import multiprocessing
import os

# Serve over a unix socket that nginx proxies to.
bind = os.environ.get("GUNICORN_BIND", "unix:/run/elearning/elearning.sock")

# Async workers so AI / I/O-bound requests don't block each other.
worker_class = "uvicorn_worker.UvicornWorker"
workers = int(os.environ.get("GUNICORN_WORKERS", (multiprocessing.cpu_count() * 2) + 1))

# AI calls can be slow; give requests room before a worker is killed.
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))
graceful_timeout = 30
keepalive = 5

max_requests = 1000
max_requests_jitter = 100

accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOGLEVEL", "info")
