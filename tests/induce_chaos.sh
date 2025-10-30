#!/bin/bash
set -eo pipefail

BLUE_HOST=http://localhost:8081

if [ "$1" = "start" ]; then
  echo "Triggering chaos start on blue..."
  curl -s -X POST "${BLUE_HOST}/chaos/start?mode=error" -o /dev/null
  echo "Started chaos (mode=error) on blue."
elif [ "$1" = "stop" ]; then
  echo "Stopping chaos on blue..."
  curl -s -X POST "${BLUE_HOST}/chaos/stop" -o /dev/null
  echo "Stopped chaos on blue."
else
  echo "Usage: $0 start|stop"
  exit 2
fi
