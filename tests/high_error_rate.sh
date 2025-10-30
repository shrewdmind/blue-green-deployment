#!/usr/bin/env bash
set -euo pipefail

# Simple hammerer script hitting Nginx root to collect status codes.
NGINX_URL=${NGINX_URL:-http://localhost:8080/}
REQS=${REQS:-400}

echo "Sending $REQS requests to $NGINX_URL"
for i in $(seq 1 $REQS); do
  printf "%s " "$(curl -s -o /dev/null -w "%{http_code}" "$NGINX_URL")"
done
echo
echo "done"
