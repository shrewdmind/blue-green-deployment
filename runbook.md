# Runbook — Observability & Alerts (Stage 3)

This runbook explains watcher alerts and operator actions.

## Failover detected
**What it means**
- The watcher observed the X-App-Pool value change (e.g., `blue` → `green`). This indicates Nginx started routing to the other pool, often because the primary failed health or returned errors.

**Operator actions**
1. Check Slack alert for timestamp and quick details.
2. Inspect Nginx logs:
   - `docker logs nginx`
   - `docker exec -it nginx sh -c "tail -n 200 /var/log/nginx/access.log"`
3. Inspect the previously primary container logs:
   - `docker logs app_blue` or `docker logs app_green`
4. Test the primary directly:
   - `curl -I http://localhost:${BLUE_HOST_PORT}/` (or green port) and inspect headers `X-App-Pool` / `X-Release-Id`.
5. If unplanned, restart or investigate the app. If planned maintenance, set `MAINTENANCE_MODE=true` to suppress alerts while making changes.

## High Error Rate
**What it means**
- A ≥ `ERROR_RATE_THRESHOLD`% of requests in the last `WINDOW_SIZE` requests were 5xx.

**Operator actions**
1. Inspect access logs to find which upstream address and release are returning 5xx.
2. Inspect app logs for that release.
3. If a single release is failing, consider rolling back or switching ACTIVE_POOL.
4. If distributed, escalate to on-call and attach logs and times to the incident.

## Recovery
- When the primary recovers, verify by:
  - `curl -I http://localhost:${NGINX_PORT}/` and confirm `X-App-Pool`.
  - Confirm traffic returns to the intended pool or that failover remains intentional.

## Suppressing alerts (maintenance)
- To suppress alerts temporarily, set `MAINTENANCE_MODE=true` in `.env` (or via the environment injected to the watcher). Set back to `false` when done.

## Contacts / escalation
- Slack channel: #devops-stage3-alerts
- On-call: bluprint
