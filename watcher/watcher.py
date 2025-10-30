#!/usr/bin/env python3
"""
alert watcher - tails nginx JSON access.log and posts alerts to Slack.

Features:
 - Detects pool failovers (blue <-> green) by observing "pool" field in log lines
 - Computes rolling 5xx error-rate over WINDOW_SIZE requests and alerts if threshold exceeded
 - Uses cooldown (ALERT_COOLDOWN_SEC) to avoid alert spam
 - Maintenance mode via presence of a file at MAINTENANCE_FLAG_PATH

Usage:
  python watcher.py /var/log/nginx/access.log
"""
import os
import sys
import time
import json
import logging
import re
from collections import deque
from datetime import datetime, timedelta
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
ERROR_RATE_THRESHOLD = float(os.environ.get("ERROR_RATE_THRESHOLD", "2.0"))
WINDOW_SIZE = int(os.environ.get("WINDOW_SIZE", "200"))
ALERT_COOLDOWN_SEC = int(os.environ.get("ALERT_COOLDOWN_SEC", "300"))
MAINTENANCE_FLAG_PATH = os.environ.get("MAINTENANCE_FLAG_PATH", "/run/maintenance.flag")
INITIAL_ACTIVE_POOL = os.environ.get("ACTIVE_POOL", "").lower()

def is_maintenance():
    try:
        return os.path.exists(MAINTENANCE_FLAG_PATH)
    except Exception:
        return False

def post_slack(payload):
    if not SLACK_WEBHOOK_URL:
        logging.info("SLACK_WEBHOOK_URL not set - dry run: %s", payload)
        return
    try:
        r = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=6)
        if r.status_code >= 400:
            logging.error("Slack webhook failed %s: %s", r.status_code, r.text)
        else:
            logging.info("Slack alert posted")
    except Exception as e:
        logging.exception("Failed to post Slack: %s", e)

def slack_message(text, blocks=None):
    payload = {"text": text}
    if blocks:
        payload["blocks"] = blocks
    return payload

def tail_f(path):
    with open(path, "r") as fh:
        fh.seek(0, os.SEEK_END)
        while True:
            line = fh.readline()
            if not line:
                time.sleep(0.2)
                continue
            yield line

def parse_json_line(line):
    try:
        return json.loads(line)
    except Exception:
        # fallback simple regex extraction
        try:
            pool = re.search(r'"pool"\s*:\s*"([^"]*)"', line)
            status = re.search(r'"status"\s*:\s*"([^"]*)"', line)
            return {
                "pool": pool.group(1) if pool else None,
                "status": status.group(1) if status else None,
                "raw": line.strip()
            }
        except Exception:
            return {"raw": line.strip()}

def main(log_path):
    logging.info("Watcher starting; tailing %s", log_path)
    last_seen_pool = None
    if INITIAL_ACTIVE_POOL:
        last_seen_pool = INITIAL_ACTIVE_POOL
        logging.info("Initial active pool from env: %s", last_seen_pool)

    window = deque(maxlen=WINDOW_SIZE)
    last_error_alert_time = None
    last_failover_alert_time = None
    last_failover_direction = None

    for line in tail_f(log_path):
        if is_maintenance():
            logging.debug("Maintenance flag present - suppressing alerts")
            continue

        entry = parse_json_line(line)
        pool = (entry.get("pool") or "").lower() if entry.get("pool") else None
        status = entry.get("status") or entry.get("upstream_status") or None
        try:
            status_code = int(status) if status else None
        except Exception:
            status_code = None

        is_5xx = status_code is not None and 500 <= status_code <= 599
        window.append(1 if is_5xx else 0)

        # Evaluate error rate
        if len(window) >= max(5, int(WINDOW_SIZE * 0.1)):
            error_count = sum(window)
            window_len = len(window)
            error_rate = (error_count / window_len) * 100.0
            logging.debug("Error rate: %.2f%% (errors=%d/%d)", error_rate, error_count, window_len)
            now = datetime.utcnow()
            if error_rate >= ERROR_RATE_THRESHOLD:
                if last_error_alert_time is None or (now - last_error_alert_time).total_seconds() > ALERT_COOLDOWN_SEC:
                    text = f":warning: High upstream error rate: *{error_rate:.2f}%* 5xx over last {window_len} requests (threshold {ERROR_RATE_THRESHOLD}%)"
                    blocks = [
                        {"type":"section", "text":{"type":"mrkdwn","text":text}},
                        {"type":"context", "elements":[{"type":"mrkdwn","text":f"Errors: {error_count} — Window: {window_len}"}]}
                    ]
                    post_slack(slack_message(text, blocks))
                    last_error_alert_time = now
                else:
                    logging.debug("Error alert suppressed by cooldown")

        # Failover detection
        if pool:
            if last_seen_pool is None:
                last_seen_pool = pool
            elif pool != last_seen_pool:
                direction = f"{last_seen_pool}→{pool}"
                now = datetime.utcnow()
                if (last_failover_direction != direction) and (last_failover_alert_time is None or (now - last_failover_alert_time).total_seconds() > ALERT_COOLDOWN_SEC):
                    text = f":rotating_light: Failover detected: *{direction}* — observed change in 'pool' header."
                    blocks = [
                        {"type":"section", "text":{"type":"mrkdwn","text":text}},
                        {"type":"context", "elements":[{"type":"mrkdwn","text":f"Sample raw: {entry.get('raw', '')[:200]}"}]}
                    ]
                    post_slack(slack_message(text, blocks))
                    last_failover_alert_time = now
                    last_failover_direction = direction
                    logging.info("Failover alert: %s", direction)
                else:
                    logging.debug("Failover alert suppressed (dedupe/cooldown)")
                last_seen_pool = pool

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: watcher.py /path/to/access.log", file=sys.stderr)
        sys.exit(2)
    log_path = sys.argv[1]
    try:
        main(log_path)
    except KeyboardInterrupt:
        logging.info("Watcher stopped")
