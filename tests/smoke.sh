#!/bin/sh
set -eu
echo "Tail last 5 nginx access.log lines..."
tail -n 5 logs/access.log || true
echo "Watcher logs (last 50 lines):"
docker logs --tail 50 alert_watcher || true
