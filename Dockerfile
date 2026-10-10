# TouchSight engine (FastAPI). The Next.js app in ./frontend is deployed separately.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app.py ./
COPY touchsight ./touchsight
COPY samples ./samples
COPY cache ./cache

RUN useradd --create-home --uid 10001 app && chown -R app /app
USER app

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
