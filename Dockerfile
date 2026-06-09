# Fleet Insight — FastAPI app image
FROM python:3.12-slim

# System deps kept minimal; mysql-connector-python is pure-Python so no build tools needed.
WORKDIR /app

# Install dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code, scripts, sql, and (generated) data
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY sql/ ./sql/
COPY data/ ./data/

EXPOSE 8000

# Default: serve the API. Override the command to run loaders, e.g.:
#   docker compose run --rm app python scripts/load_mysql.py
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
