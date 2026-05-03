"""
Slack notifier.

Sends structured alerts for: ban, unban, global anomaly.
The webhook URL is read from config (overridden by SLACK_WEBHOOK_URL env var).
All sends are attempted with a 5-second timeout; failures are logged only.
"""
import logging
import os
import time

import requests


logger = logging.getLogger(__name__)

_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _ts():
    return time.strftime(_TS_FMT, time.gmtime())


class Notifier:
    def __init__(self, config):
        self._webhook = (
            os.environ.get("SLACK_WEBHOOK_URL") or config.get("slack_webhook_url", "")
        )

    def _post(self, text: str):
        if not self._webhook:
            logger.warning("No Slack webhook configured; skipping alert")
            return
        try:
            resp = requests.post(
                self._webhook,
                json={"text": text},
                timeout=5,
            )
            resp.raise_for_status()
        except Exception as e:
            logger.error("Slack alert failed: %s", e)

    def send_ban(self, ip: str, condition: str, rate: float,
                 baseline: float, duration: int):
        dur_str = "PERMANENT" if duration == 0 else f"{duration}s"
        text = (
            f":rotating_light: *BAN* `{ip}`\n"
            f"Condition: {condition}\n"
            f"Rate: {rate:.1f} req/s | Baseline mean: {baseline:.1f} req/s\n"
            f"Ban duration: {dur_str} | Time: {_ts()}"
        )
        self._post(text)

    def send_unban(self, ip: str, ban_count: int, condition: str,
                   rate: float, baseline: float):
        text = (
            f":white_check_mark: *UNBAN* `{ip}`\n"
            f"Ban #{ban_count} expired\n"
            f"Original condition: {condition}\n"
            f"Original rate: {rate:.1f} req/s | Baseline: {baseline:.1f} req/s\n"
            f"Time: {_ts()}"
        )
        self._post(text)

    def send_global_alert(self, condition: str, rate: float, baseline: float):
        text = (
            f":warning: *GLOBAL ANOMALY DETECTED*\n"
            f"Condition: {condition}\n"
            f"Global rate: {rate:.1f} req/s | Baseline mean: {baseline:.1f} req/s\n"
            f"Time: {_ts()}"
        )
        self._post(text)
