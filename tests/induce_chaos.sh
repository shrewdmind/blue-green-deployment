
---

## `tests/induce_chaos.sh`
A simple script that uses curl to hit an endpoint that we assume Stage2 app supports to flip into error mode. If your Stage2 app exposes specific chaos endpoints, replace the URL/paths accordingly.

```bash
#!/bin/sh
#
# Simple chaos script that repeatedly hits the primary app endpoint to simulate errors.
# Adjust to your Stage2 app's chaos endpoints if available.

set -eu

# By default we target the blue app (primary)
TARGET_HOST=${NGINX_HOST:-localhost}
TARGET_PORT=${NGINX_PORT:-8080}
REQUESTS=${1:-250}

echo "Sending $REQUESTS requests to http://$TARGET_HOST:$TARGET_PORT/chaos (expecting Stage2 to support chaos)"
i=0
while [ $i -lt $REQUESTS ]; do
  curl -s -o /dev/null -w "%{http_code}\n" "http://$TARGET_HOST:$TARGET_PORT/" || true
  i=$((i+1))
done

echo "Done"
