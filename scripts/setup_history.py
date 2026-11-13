"""Explicit operator-only provisioning. Never invoked by scheduled jobs."""
import os
from google.cloud import bigquery
from pipeline import Pipeline

if __name__ == "__main__":
    pipeline = Pipeline(bigquery.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT", "fpl-optimizer-511321")))
    pipeline.provision()
