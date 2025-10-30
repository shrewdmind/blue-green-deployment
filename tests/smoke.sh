#!/bin/bash
set -eo pipefail

NGINX_URL=http://localhost:8080/version
BLUE_HOST=http://localhost:8081
GREEN_HOST=http://localhost:8082

echo "Checking nginx endpoint (should be 200)..."
curl -s -D - "$NGINX_URL" -o /dev/null | sed -n '1,6p'

echo "Direct blue /version:"
curl -s -D - "${BLUE_HOST}/version" -o /dev/null | sed -n '1,6p'

echo "Direct green /version:"
curl -s -D - "${GREEN_HOST}/version" -o /dev/null | sed -n '1,6p'
