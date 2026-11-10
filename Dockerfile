FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY backend/ ./backend/

# Run as non-root
RUN useradd --create-home appuser
USER appuser

EXPOSE 8080

# Cloud Run injects $PORT; exec keeps uvicorn as PID 1 for clean SIGTERM handling.
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}"]
