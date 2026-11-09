# Multi-stage lightweight Python container
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and data
COPY backend/ ./backend/

# Expose port (Cloud Run sets $PORT dynamically)
EXPOSE 8080

# Start Uvicorn server
# CMD exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}
# JSON args format with sh -c exec for dynamic $PORT expansion & clean signal handling
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}"]
