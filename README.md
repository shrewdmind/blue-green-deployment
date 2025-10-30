# 🚨 Blue/Green Observability & Alerting System
## DevOps Intern — Stage 3 Task

This project extends the Stage 2 Blue/Green deployment by adding observability, monitoring, and alerting.
It introduces a real-time Python log-watcher sidecar that tails Nginx logs, detects failovers or high error rates, and sends formatted alerts to Slack under the name Blueprint.

## 🧭 Overview

When running a Blue/Green setup, visibility into what’s happening behind the Nginx load balancer is crucial.
This stage provides that visibility by:
- Enriching Nginx access logs with detailed upstream metadata.
- Streaming logs to a lightweight watcher container.
- Automatically notifying Slack when failovers occur or when error rates exceed a configured threshold.

The result is a self-observing deployment environment — you know which pool is serving traffic, how healthy it is, and when to take action.

## 🧱 Architecture
                ┌──────────────────────┐
                │   Slack Channel      │
                │  (Blueprint Alerts)  │
                └────────▲─────────────┘
                         │
                         │ Webhook (JSON)
                         │
┌──────────────┐     ┌───┴─────────────┐
│   Nginx      │────▶│ Python Watcher  │
│  (Access Log)│     │  tails log,     │
│              │◀────│  detects events │
└────┬─────────┘     └───┬─────────────┘
     │                   │
     ▼                   │
┌──────────────┐    Shared Volume
│ Blue Service │
│ Green Service│
└──────────────┘

- Nginx writes structured logs (pool, release, status, latency).
- Watcher reads those logs in real time, maintains a rolling window, and evaluates conditions.
- Slack Webhook receives formatted alerts posted as Blueprint.

## ⚙️ Features
Failover Detection:	Detects when traffic flips from one pool (e.g. Blue → Green).
Error-Rate Monitoring:	Watches the last `N` requests for 5xx responses and alerts when they exceed threshold.
Slack Notifications:	Sends clean, structured alerts using Block Kit formatting.
Maintenance Mode:	Suppresses alerts during planned toggles.
Environment-Driven Configuration:	All thresholds and webhook details come from `.env`.

## 📁 Repository Layout
.
├── docker-compose.yml        # Defines Blue, Green, Nginx, and Watcher services
├── nginx/
│   ├── nginx.conf.template   # Structured logging format
│   └── docker-entrypoint.sh  # Generates upstream config dynamically
├── watcher/
│   ├── watcher.py            # Main alert engine
│   └── requirements.txt      # Python dependencies
├── runbook.md                # Operator guide for responding to alerts
├── .env.example              # Config variables and defaults
└── tests/
    └── high_error_rate.sh    # Simple load test to trigger alerts

## ⚙️ Environment Variables

SLACK_WEBHOOK_URL:  Webhook URL for posting alerts	(required)
ACTIVE_POOL	Initial:    active pool (blue or green)
ERROR_RATE_THRESHOLD:   % of 5xx requests to trigger alert	2
WINDOW_SIZE:	Number of recent requests to evaluate	200
ALERT_COOLDOWN_SEC:	Cooldown between repeated alerts (s)	300
MAINTENANCE_MODE:	Suppress alerts when true	false
LOG_PATH:	Path to Nginx access log	/var/log/nginx/access.log

## 🚀 Getting Started

1. Set up Slack Webhook

- Create an [Incoming Webhook](https://api.slack.com/apps)
- Enable it for a channel (e.g., #alerts).
- Copy the generated URL into .env under SLACK_WEBHOOK_URL.

2. Configure Environment
```
cp .env.example .env
# Edit values as needed
```

3. Launch the Stack
```
docker compose up -d
```

4. Verify Components
```
docker compose ps
docker logs -f alert_watcher
docker exec -it nginx tail -n 5 /var/log/nginx/access.log
```

You should see logs being written and the watcher printing updates.

## 🔔 Alert Behavior
### 🚨 Failover Alerts

Triggered when the active pool flips (e.g., Blue → Green).

Slack Message Example

> 🔴 Failover Detected
> • From: `Blue → Green`
> • Time: 2025-10-30 16:03 UTC
> Action: Verify primary container health and traffic routing.

### ⚠️ Error-Rate Alerts

Triggered when 5xx responses exceed the threshold (default 2 %) within the sliding window.

Slack Message Example

> 🟠 High Upstream Error Rate Detected
> • Rate: 6.50 % over 200 requests
> • Threshold: 2 %
> Action: Check upstream logs and investigate errors.

💤 Maintenance Mode

Set `MAINTENANCE_MODE=true` in `.env` to silence alerts during planned releases.

## 🧪 Testing Alerts
**Simulate Failover**

Bring down the currently active container:
```
docker stop app_blue
```

Nginx will failover to the other pool, and the watcher posts a failover alert.

**Simulate High Error-Rate**

Run the included test script to generate many requests:
```
bash tests/high_error_rate.sh
```

If enough requests return 5xx, you’ll receive a “High Error Rate” alert in Slack.

## 📖 Runbook (summary)

See `runbook.md` for detailed operator steps:

- What each alert means
- How to inspect logs and containers
- Recovery and escalation procedures