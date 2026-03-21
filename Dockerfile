FROM python:3.12-slim

WORKDIR /app

COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt

COPY src/ src/
COPY frontend/dist/ frontend/dist/
COPY run_server.py .

RUN mkdir -p /app/data

ENV PYTHONPATH=/app

EXPOSE 8321

CMD ["gunicorn", "run_server:app", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8321", "--timeout", "300"]
