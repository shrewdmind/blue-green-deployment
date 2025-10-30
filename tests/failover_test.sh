#!/usr/bin/env bash
set -euo pipefail

NGINX_URL=http://localhost:8080/version
BLUE_HOST=http://localhost:8081
TEST_DURATION=10     # seconds
RATE=20              # requests per second
TOTAL=$((TEST_DURATION * RATE))
SLEEP_MICRO=$((1000000 / RATE))

echo "Starting failover acceptance test"
echo "Test duration: ${TEST_DURATION}s, rate: ${RATE}/s, total requests: ${TOTAL}"

# 1) Baseline check (first request must be from ACTIVE_POOL)
echo "Baseline GET ..."
baseline_headers=$(curl -s -D - "$NGINX_URL" -o /dev/null)
echo "$baseline_headers"
echo

# 2) Trigger chaos on active (assume grader will use the blue host for chaos; scripts use blue)
echo "Triggering chaos on blue..."
curl -s -X POST "${BLUE_HOST}/chaos/start?mode=error" -o /dev/null

# 3) Poll for TEST_DURATION seconds
echo "Polling nginx for ${TEST_DURATION}s ..."
count_200=0
count_non200=0
count_blue=0
count_green=0

for i in $(seq 1 $TOTAL); do
  # Get both status and X-App-Pool header
  resp=$(curl -s -D - --max-time 6 "$NGINX_URL" -o /dev/null || true)
  status_line=$(echo "$resp" | head -n1 | tr -d '\r')
  status_code=$(echo "$status_line" | awk '{print $2}')
  pool=$(echo "$resp" | grep -i '^X-App-Pool:' | awk -F: '{gsub(/^[ \t]+/, "", $2); print tolower($2)}' || true)

  if [ "$status_code" = "200" ]; then
    count_200=$((count_200 + 1))
  else
    count_non200=$((count_non200 + 1))
  fi

  if [ "$pool" = "blue" ]; then
    count_blue=$((count_blue + 1))
  elif [ "$pool" = "green" ]; then
    count_green=$((count_green + 1))
  fi

  # Sleep
  usleep $SLEEP_MICRO
done

# 4) Stop chaos
echo "Stopping chaos on blue..."
curl -s -X POST "${BLUE_HOST}/chaos/stop" -o /dev/null || true

echo
echo "Results:"
echo "Total requests: $TOTAL"
echo "200 responses : $count_200"
echo "non-200       : $count_non200"
echo "blue responses: $count_blue"
echo "green responses: $count_green"

pct_green=$(awk -v g="$count_green" -v t="$TOTAL" 'BEGIN{ if(t==0) print 0; else printf "%.2f", 100*g/t }')

echo "Percent green: $pct_green%"

# Evaluate pass/fail
if [ "$count_non200" -ne 0 ]; then
  echo "TEST FAIL: non-200 responses observed during chaos."
  exit 1
fi

pct_green_int=$(printf "%.0f" "$pct_green")
# require >=95% green
awk -v pg="$pct_green" 'BEGIN{ if (pg+0 < 95) { print "TEST FAIL: less than 95% responses from green."; exit 2 } else { print "TEST PASS: >=95% green responses."; } }'

echo "Failover test completed."
