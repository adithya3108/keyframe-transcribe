#!/bin/sh
# Write GCP credentials from env var to a file if provided
if [ -n "$GCP_SERVICE_ACCOUNT_JSON" ]; then
    echo "$GCP_SERVICE_ACCOUNT_JSON" > /app/gcp-service-account.json
    export GOOGLE_APPLICATION_CREDENTIALS=/app/gcp-service-account.json
fi

exec uvicorn api.main:app --host 0.0.0.0 --port "${PORT:-8000}"
