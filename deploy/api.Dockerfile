# API image: FastAPI + uvicorn over the governed tools.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Requirements first so a code change does not re-run the dependency install.
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend/ /app/backend/
COPY evals/ /app/evals/

# The database and the extraction cache live on a volume so a rebuild does not
# throw away the ingested data.
# CBI_DATA_DIR is the single root: raw data, the extraction cache and the
# SQLite file all derive from it (see backend/app/config.py).
ENV CBI_DATA_DIR=/data
RUN mkdir -p /data

# Run as a non-root user: nothing here needs privileges.
RUN useradd --create-home --uid 10001 cbi && chown -R cbi:cbi /app /data
USER cbi

WORKDIR /app/backend
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=4).status==200 else 1)"

CMD ["python", "-m", "uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
