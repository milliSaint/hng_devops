"""
Entry point for the HNG anomaly detection daemon.

Starts four threads:
  1. Baseline recalculation loop (every 60s)
  2. Unban scheduler (polls every 10s)
  3. Dashboard web server (Flask, port 8080)
  4. Main thread: tails the Nginx log and processes every entry

All components share references to baseline, detector, unbanner, and notifier.
"""
import logging
import os
import sys
import threading
import time

import yaml

from baseline import BaselineTracker
from blocker import block_ip, unblock_ip
from dashboard import start_dashboard
from detector import AnomalyDetector
from monitor import tail_log
from notifier import Notifier
from unbanner import UnbanScheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("main")

_AUDIT_FMT = "[{ts}] {action} {ip} | {condition} | rate={rate:.2f} | baseline={baseline:.2f} | {extra}"


def _load_config():
    cfg_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    return cfg


def _setup_audit_log(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    def write(msg: str):
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        line = f"[{ts}] {msg}\n"
        logger.info("AUDIT: %s", msg)
        try:
            with open(path, "a") as f:
                f.write(line)
        except OSError as e:
            logger.warning("Could not write audit log: %s", e)

    return write


def main():
    config = _load_config()
    audit = _setup_audit_log(config["audit_log"])

    baseline = BaselineTracker(config, audit_log_fn=audit)
    notifier = Notifier(config)
    unbanner = UnbanScheduler(config, blocker_fn=unblock_ip, notifier=notifier)
    detector = AnomalyDetector(config, baseline)

    # Tracks which IPs are currently banned to avoid duplicate ban actions
    active_bans: set = set()
    ban_lock = threading.Lock()

    def on_entry(entry):
        baseline.record(entry)
        result = detector.check(entry)
        ip = result.ip

        with ban_lock:
            already_banned = ip in active_bans

        # --- Per-IP anomaly: block + Slack ---
        if result.ip_anomalous and not already_banned and not unbanner.is_banned(ip):
            duration = unbanner.ban(
                ip=ip,
                condition=result.ip_condition,
                rate=result.ip_rate,
                baseline=result.mean,
            )
            block_ip(ip)
            dur_label = "PERMANENT" if duration == 0 else f"{duration}s"
            audit(
                f"BAN {ip} | {result.ip_condition} | "
                f"rate={result.ip_rate:.2f} | baseline={result.mean:.2f} | "
                f"duration={dur_label}"
            )
            notifier.send_ban(
                ip=ip,
                condition=result.ip_condition,
                rate=result.ip_rate,
                baseline=result.mean,
                duration=duration,
            )
            with ban_lock:
                active_bans.add(ip)
            logger.warning("BANNED %s | %s", ip, result.ip_condition)

        # When unbanner clears an IP, also remove from active_bans
        # (unbanner calls unblock_ip directly; we just sync the set here)
        if not unbanner.is_banned(ip):
            with ban_lock:
                active_bans.discard(ip)

        # --- Global anomaly: Slack only ---
        if result.global_anomalous:
            notifier.send_global_alert(
                condition=result.global_condition,
                rate=result.global_rate,
                baseline=result.mean,
            )
            audit(
                f"GLOBAL_ANOMALY | {result.global_condition} | "
                f"rate={result.global_rate:.2f} | baseline={result.mean:.2f} | duration=N/A"
            )
            logger.warning("GLOBAL ANOMALY | %s", result.global_condition)

    # Start background threads
    threading.Thread(target=baseline.recalc_loop, daemon=True,
                     name="baseline-recalc").start()
    threading.Thread(target=unbanner.run, daemon=True,
                     name="unban-scheduler").start()
    threading.Thread(
        target=start_dashboard,
        args=(config, baseline, detector, unbanner),
        daemon=True,
        name="dashboard",
    ).start()

    logger.info("Daemon started. Watching %s", config["log_path"])
    audit("DAEMON_START | | rate=0.00 | baseline=0.00 | pid=%d" % os.getpid())

    tail_log(config["log_path"], on_entry)


if __name__ == "__main__":
    main()
