FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DB_PATH="/app/flight_booking.db" \
    MCP_HOST="0.0.0.0" \
    MCP_PORT="8080"

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy server source (src/) only — no tests, no agent, no scripts
COPY src ./src

# Non-root user for security
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app

USER appuser

# Pre-seed SQLite database at build time
RUN python -c "from src.db.session import init_db; init_db('/app/flight_booking.db')"

EXPOSE 8080

# Production healthcheck
HEALTHCHECK --interval=20s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health').getcode() == 200 else 1)"

CMD ["uvicorn", "src.server:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips=*", "--workers", "1"]
