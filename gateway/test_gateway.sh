#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 https://<gateway-domain> [client-token]" >&2
  exit 2
fi

GATEWAY_URL="${1%/}"
CLIENT_TOKEN="${2:-${CLIENT_TOKEN:-}}"

echo "Health check: ${GATEWAY_URL}/health"
curl -fsS "${GATEWAY_URL}/health"
echo

AUTH_ARGS=()
if [[ -n "${CLIENT_TOKEN}" ]]; then
  AUTH_ARGS=(-H "Authorization: Bearer ${CLIENT_TOKEN}")
fi

echo "Small LLM call: ${GATEWAY_URL}/v1/chat/completions"
curl -fsS "${GATEWAY_URL}/v1/chat/completions" \
  "${AUTH_ARGS[@]}" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {
        "role": "user",
        "content": "Sadece su JSON nesnesini dondur: {\"ok\": true}"
      }
    ],
    "temperature": 0,
    "max_tokens": 64
  }'
echo
