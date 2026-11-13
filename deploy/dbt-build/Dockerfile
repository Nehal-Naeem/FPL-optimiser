FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp \
    DBT_PROFILES_DIR=/app/profiles \
    DBT_LOG_PATH=/tmp/dbt/logs \
    DBT_TARGET_PATH=/tmp/dbt/target \
    DBT_SEND_ANONYMOUS_USAGE_STATS=false
WORKDIR /app/project
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt && pip check
COPY profiles.yml /app/profiles/profiles.yml
COPY project/ ./
COPY pipeline.py history_ingestion.py dbt_publish.py ./
RUN dbt deps && dbt parse --no-partial-parse && rm -rf /tmp/dbt
USER 65532:65532
ENTRYPOINT ["python", "dbt_publish.py"]
