# Backend image: FastAPI + ML/backtesting stack on Python 3.12.
# Hardened per audit HIGH-8: explicit COPY, pinned deps, non-root, healthcheck.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Pinned dependency layer first for caching; falls back to pyproject ranges
# only if the lock is ever absent.
COPY requirements.lock pyproject.toml ./
RUN pip install --upgrade pip && pip install -r requirements.lock

# Application code (explicit paths - never COPY . with local state around).
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
RUN pip install --no-deps .

# Non-root runtime user.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/live', timeout=4).status==200 else 1)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
