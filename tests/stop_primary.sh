#!/bin/sh
set -eu
. .env

ACTIVE_POOL=${ACTIVE_POOL:-blue}

if [ "$ACTIVE_POOL" = "blue" ]; then
  echo "Stopping app_blue to trigger failover to green..."
  docker stop app_blue
else
  echo "Stopping app_green to trigger failover to blue..."
  docker stop app_green
fi
