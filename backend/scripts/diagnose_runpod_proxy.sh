#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-8000}"
POD_ID="${RUNPOD_POD_ID:-${POD_ID:-}}"

echo "service_bindings"
ss -ltnp | awk -v port=":${PORT}" '$4 ~ port {print}'

echo "internal_root"
curl --fail --show-error --silent --max-time 5 \
  --write-out 'status=%{http_code} remote=%{remote_ip}\n' \
  --output /dev/null "http://127.0.0.1:${PORT}/"

echo "internal_liveness"
curl --fail --show-error --silent --max-time 5 \
  --write-out 'status=%{http_code} remote=%{remote_ip}\n' \
  --output /dev/null "http://127.0.0.1:${PORT}/health/live"

if [[ -z "${POD_ID}" ]]; then
  echo "error: RUNPOD_POD_ID is unavailable; public proxy URL cannot be derived" >&2
  exit 2
fi

PUBLIC_URL="https://${POD_ID}-${PORT}.proxy.runpod.net"
echo "public_proxy=${PUBLIC_URL}"
if ! curl --fail --show-error --silent --max-time 15 \
  --write-out 'status=%{http_code} remote=%{remote_ip}\n' \
  --output /dev/null "${PUBLIC_URL}/"; then
  echo "error: application is healthy internally but RunPod HTTP mapping is unreachable" >&2
  echo "required_runpod_port=${PORT}/http" >&2
  exit 3
fi
