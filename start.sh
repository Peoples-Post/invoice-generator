#!/bin/sh
echo "PORT value: $PORT"
echo "All env vars:"
env
exec gunicorn app:app --bind 0.0.0.0:${PORT:-5001} --workers 1 --timeout 120