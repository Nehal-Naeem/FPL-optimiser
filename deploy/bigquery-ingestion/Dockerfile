FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bigquery_ingestion.py history_ingestion.py pipeline.py ./
USER 65532:65532
CMD ["python", "bigquery_ingestion.py"]
