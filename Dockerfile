FROM python:3.12-slim

WORKDIR /app

COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt

COPY src/ src/
COPY frontend/dist/ frontend/dist/
COPY run_server.py .

RUN mkdir -p /app/data

# Store keyring (Google OAuth tokens) on the persistent Docker volume
ENV PYTHONPATH=/app
ENV XDG_DATA_HOME=/app/data
ENV PLANNER_DB_PATH=/app/data/planner.db

EXPOSE 8321

CMD ["gunicorn", "run_server:app", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8321", "--timeout", "300"]
