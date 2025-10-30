#!/usr/bin/env python3
"""
watcher.py - tails nginx access.log, detects pool failovers and high 5xx error rates,
and posts alerts to Slack using SLACK_WEBHOOK_URL from env.
"""

import os
import time
import re
import json
import collections
from datetime import datetime

try:
    import requests
except Exception:
    raise SystemExit("Missing dependency 'requests'. Install with: pip install -r requirements.txt")

# Configuration
LOG_PATH = os.environ.get("LOG_PATH", "/var/log/nginx/access.log")
WINDOW_SIZE = int(os.environ.get("WINDOW_SIZE", "200"))
ERROR_RATE_THRESHOLD = float(os.environ.get("ERROR_RATE_THRESHOLD", "2.0"))
ALERT_COOLDOWN_SEC = int(os.environ.get("ALERT_COOLDOWN_SEC", "300"))
SLACK_WEBHOOK = os.environ.get("SLACK_WEBHOOK_URL")
MAINTENANCE_MODE = os.environ.get("MAINTENANCE_MODE", "false").lower() in ("1", "true", "yes")

if not SLACK_WEBHOOK:
    print("ERROR: SLACK_WEBHOOK_URL is not set. Exiting.")
    raise SystemExit(1)

# Regex to extract key structured bits, fallback to parsing status code from the request-status pattern
# Note: the log format includes '"$request" $status' so we capture status with that pattern.
STATUS_RE = re.compile(r'"\S+\s+\S+\s+\S+"\s+(?P<status>\d{3})\s')
FIELD_RE = re.compile(r'pool="(?P<pool>[^"]*)"|release="(?P<release>[^"]*)"|upstream_status="(?P<upstream_status>[^"]*)"|upstream_addr="(?P<upstream_addr>[^"]*)"')

window = collections.deque(maxlen=WINDOW_SIZE)
last_pool_seen = None
last_failover_alert_ts = None
last_error_alert_ts = None

def post_slack(event_type, details):
    """
    Send a formatted Slack message based on the event type.
    event_type: 'failover' or 'error_rate'
    details: dict with relevant info
    """
    if event_type == "failover":
        color = "#ff0000"  # red
        title = f"🚨 Failover Detected"
        fields = [
            {"type": "mrkdwn", "text": f"*From:* `{details['from_pool']}` → `{details['to_pool']}`"},
            {"type": "mrkdwn", "text": f"*Time:* {details['timestamp']} UTC"},
        ]
        action_text = "_Action:_ Check primary container health and confirm routing."

    elif event_type == "error_rate":
        color = "#ffa500"  # orange
        title = f"⚠️ High Upstream Error Rate Detected"
        fields = [
            {"type": "mrkdwn", "text": f"*Rate:* {details['rate']:.2f}% 5xx over last {details['window']} requests"},
            {"type": "mrkdwn", "text": f"*Threshold:* {details['threshold']}%"},
            {"type": "mrkdwn", "text": f"*Time:* {details['timestamp']} UTC"},
        ]
        action_text = "_Action:_ Check upstream logs and investigate service errors."

    else:
        return  # unknown type

    payload = {
        "username": "Blueprint",
        "attachments": [
            {
                "color": color,
                "blocks": [
                    {"type": "header", "text": {"type": "plain_text", "text": title}},
                    {"type": "section", "fields": fields},
                    {"type": "context", "elements": [{"type": "mrkdwn", "text": action_text}]}
                ]
            }
        ]
    }

    try:
        r = requests.post(SLACK_WEBHOOK, json=payload, timeout=6)
        r.raise_for_status()
        print(f"[{datetime.utcnow().isoformat()}] Slack alert ({event_type}) sent as Blueprints Spy Watch.")
    except Exception as e:
        print(f"[{datetime.utcnow().isoformat()}] Failed to send slack message: {e}")


def parse_line(line):
    fields = {}
    for m in FIELD_RE.finditer(line):
        for k, v in m.groupdict().items():
            if v:
                fields[k] = v
    status_m = STATUS_RE.search(line)
    status = int(status_m.group("status")) if status_m else None
    return {
        "status": status,
        "pool": fields.get("pool"),
        "release": fields.get("release"),
        "upstream_status": fields.get("upstream_status"),
        "upstream_addr": fields.get("upstream_addr"),
        "raw": line.strip()
    }

def evaluate_window():
    global last_error_alert_ts
    if len(window) < 10:
        return
    total = len(window)
    errors = sum(1 for s, _ in window if s is not None and 500 <= s <= 599)
    rate = (errors / total) * 100.0
    if rate >= ERROR_RATE_THRESHOLD:
        now = datetime.utcnow()
        if MAINTENANCE_MODE:
            print(f"[{now.isoformat()}] High error rate {rate:.2f}% suppressed (maintenance mode).")
            return
        if last_error_alert_ts and (now - last_error_alert_ts).total_seconds() < ALERT_COOLDOWN_SEC:
            print(f"[{now.isoformat()}] High error rate {rate:.2f}% but cooldown active.")
            return
        text = f":warning: *High upstream error rate detected* — {rate:.2f}% 5xx in last {total} requests (threshold {ERROR_RATE_THRESHOLD}%)."
        details = f"errors={errors} total={total} window={WINDOW_SIZE}"
        post_slack("error_rate", {
            "rate": rate,
            "window": total,
            "threshold": ERROR_RATE_THRESHOLD,
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S")
        })
        last_error_alert_ts = now
        print(f"[{now.isoformat()}] Posted error-rate alert: {rate:.2f}%")

def handle_failover(new_pool):
    global last_pool_seen, last_failover_alert_ts
    now = datetime.utcnow()
    if not new_pool:
        return
    new_pool = new_pool.lower()
    if last_pool_seen is None:
        last_pool_seen = new_pool
        return
    if new_pool != last_pool_seen:
        if MAINTENANCE_MODE:
            print(f"[{now.isoformat()}] Detected pool flip {last_pool_seen} -> {new_pool} suppressed (maintenance).")
            last_pool_seen = new_pool
            return
        if last_failover_alert_ts and (now - last_failover_alert_ts).total_seconds() < ALERT_COOLDOWN_SEC:
            print(f"[{now.isoformat()}] Detected pool flip {last_pool_seen} -> {new_pool} but cooldown active.")
            last_pool_seen = new_pool
            return
        text = f":rotating_light: *Failover detected* — {last_pool_seen} → {new_pool} at {now.isoformat()} UTC"
        post_slack("failover", {
            "from_pool": last_pool_seen,
            "to_pool": new_pool,
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S")
        })
        last_failover_alert_ts = now
        print(f"[{now.isoformat()}] Posted failover alert: {last_pool_seen} -> {new_pool}")
        last_pool_seen = new_pool

def tail_file(path):
    while not os.path.exists(path):
        print(f"[{datetime.utcnow().isoformat()}] Waiting for log file {path}")
        time.sleep(1)
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        fh.seek(0, 2)
        while True:
            line = fh.readline()
            if not line:
                time.sleep(0.1)
                continue
            obj = parse_line(line)
            status = obj["status"] or 0
            pool = obj["pool"]
            window.append((status, pool))
            if pool:
                handle_failover(pool)
            evaluate_window()

def main():
    print(f"[{datetime.utcnow().isoformat()}] watcher starting; tailing {LOG_PATH}")
    tail_file(LOG_PATH)

if __name__ == "__main__":
    main()
