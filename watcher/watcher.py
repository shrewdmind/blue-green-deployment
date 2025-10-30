#!/usr/bin/env python3
"""
watcher.py - tail nginx JSON access log and post alerts to Slack.

Relies on upstream_addr field to map to pool: checks for 'app_blue' or 'app_green' in upstream_addr.
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
ACTIVE_POOL = os.environ.get("ACTIVE_POOL", "").lower()

def is_maintenance():
    return os.path.exists(MAINTENANCE_FLAG_PATH)

def post_slack(payload):
    if not SLACK_WEBHOOK_URL:
        logging.info("SLACK_WEBHOOK_URL not set: dry-run payload: %s", payload)
        return
    try:
        r = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=6)
        if r.status_code >= 400:
            logging.error("Slack post failed %s: %s", r.status_code, r.text)
        else:
            logging.info("Slack alert posted")
    except Exception as e:
        logging.exception("Failed to post to Slack: %s", e)

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

def parse_line_json(line):
    try:
        return json.loads(line)
    except Exception:
        return {"raw": line.strip()}

def pool_from_upstream_addr(upstream_addr):
    if not upstream_addr:
        return None
    # common patterns: "app_blue:3000", "172.18.0.5:3000", etc.
    s = upstream_addr.lower()
    if "app_blue" in s:
        return "blue"
    if "app_green" in s:
        return "green"
    # fallback: if ACTIVE_POOL known, but upstream contains different IP, try heuristics
    # If neither hostnames present, return None
    return None

def main(log_path):
    logging.info("Starting watcher; tailing %s", log_path)
    last_seen_pool = ACTIVE_POOL if ACTIVE_POOL else None
    window = deque(maxlen=WINDOW_SIZE)
    last_error_alert_time = None
    last_failover_alert_time = None
    last_failover_direction = None

    for line in tail_f(log_path):
        if is_maintenance():
            logging.debug("Maintenance flag present; suppressing alerts.")
            continue

        entry = parse_line_json(line)
        upstream_addr = entry.get("upstream_addr") or entry.get("upstream_addr_host") or ""
        status = entry.get("status") or entry.get("upstream_status") or ""
        # sometimes upstream_status can be comma separated "502, 200" -> take last numeric
        try:
            # get last numeric status in string
            status_nums = re.findall(r"\d{3}", str(status))
            status_code = int(status_nums[-1]) if status_nums else None
        except Exception:
            status_code = None

        pool = pool_from_upstream_addr(upstream_addr)

        is_5xx = status_code is not None and 500 <= status_code <= 599
        window.append(1 if is_5xx else 0)

        # error-rate evaluation
        if len(window) >= max(5, int(WINDOW_SIZE * 0.1)):
            errors = sum(window)
            total = len(window)
            error_rate = (errors / total) * 100.0
            logging.debug("window %d errors=%d rate=%.2f%%", total, errors, error_rate)
            now = datetime.utcnow = __import__("datetime").datetime.utcnow()
            if error_rate >= ERROR_RATE_THRESHOLD:
                if (last_error_alert_time is None) or ((now - last_error_alert_time).total_seconds() > ALERT_COOLDOWN_SEC):
                    text = f":warning: High upstream error rate detected — *{error_rate:.2f}%* 5xx over last {total} requests (threshold {ERROR_RATE_THRESHOLD}%)."
                    blocks = [
                        {"type":"section", "text":{"type":"mrkdwn","text":text}},
                        {"type":"context", "elements":[{"type":"mrkdwn","text":f"Errors: {errors} — Window size: {total}"}]}
                    ]
                    post_slack(slack_message(text, blocks))
                    last_error_alert_time = now
                else:
                    logging.debug("Error alert suppressed by cooldown")

        # failover detection
        if pool:
            if last_seen_pool is None:
                last_seen_pool = pool
            elif pool != last_seen_pool:
                direction = f"{last_seen_pool}→{pool}"
                now = datetime.utcnow = __import__("datetime").datetime.utcnow()
                if (last_failover_direction != direction) and ((last_failover_alert_time is None) or ((now - last_failover_alert_time).total_seconds() > ALERT_COOLDOWN_SEC)):
                    text = f":rotating_light: Failover detected — *{direction}* (observed change in upstream serving pool)."
                    blocks = [
                        {"type":"section", "text":{"type":"mrkdwn","text":text}},
                        {"type":"context", "elements":[{"type":"mrkdwn","text":f"Sample upstream_addr: {upstream_addr}, status: {status}"}]}
                    ]
                    post_slack(slack_message(text, blocks))
                    last_failover_alert_time = now
                    last_failover_direction = direction
                    logging.info("Failover alert: %s", direction)
                else:
                    logging.debug("Failover alert suppressed (dedupe/cooldown).")
                last_seen_pool = pool

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: watcher.py /path/to/access.log", file=sys.stderr)
        sys.exit(2)
    log_path = sys.argv[1]
    try:
        main(log_path)
    except KeyboardInterrupt:
        logging.info("Watcher exiting")
