#!/bin/sh
# Write credentials from env var to file before starting the app.
# This allows Railway deployments without persistent volumes.

if [ -n "$CREDENTIALS_JSON" ]; then
  mkdir -p /app/secrets
  echo "$CREDENTIALS_JSON" > /app/secrets/credentials.json
  echo "Credentials written from CREDENTIALS_JSON env var"
fi

exec "$@"
