"""
Backoff unban scheduler.

Ban durations per IP (from config): [600, 1800, 7200] seconds.
After three bans the IP is permanently blocked (no further unban).

A background thread polls every 10 seconds and releases expired bans.
"""
import logging
import threading
import time


logger = logging.getLogger(__name__)


class UnbanScheduler:
    def __init__(self, config, blocker_fn, notifier=None):
        """
        blocker_fn: callable(ip) — removes the iptables rule
        notifier:   optional Notifier instance for Slack alerts
        """
        self._durations = config["ban_durations"]
        self._unblock = blocker_fn
        self._notifier = notifier

        self._lock = threading.Lock()
        # ip -> {"count": int, "unban_at": float|None, "condition": str,
        #        "rate": float, "baseline": float}
        self._records: dict = {}

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def is_banned(self, ip: str) -> bool:
        with self._lock:
            rec = self._records.get(ip)
            if not rec:
                return False
            # Permanent ban: count exhausted all durations and unban_at is None
            if rec["unban_at"] is None and rec["count"] > 0:
                return True
            return rec["unban_at"] is not None

    def ban(self, ip: str, condition: str, rate: float, baseline: float):
        """Record a new ban and return the duration in seconds (0 = permanent)."""
        with self._lock:
            rec = self._records.setdefault(
                ip, {"count": 0, "unban_at": None,
                     "condition": "", "rate": 0.0, "baseline": 0.0}
            )
            rec["condition"] = condition
            rec["rate"] = rate
            rec["baseline"] = baseline

            idx = rec["count"]
            if idx >= len(self._durations):
                # Permanent: leave unban_at as None
                rec["count"] = len(self._durations)  # cap, don't increment further
                return 0  # 0 signals permanent

            duration = self._durations[idx]
            rec["unban_at"] = time.time() + duration
            rec["count"] += 1
            return duration

    def next_duration(self, ip: str) -> int:
        """Peek at what the next ban duration would be without recording it."""
        with self._lock:
            rec = self._records.get(ip, {"count": 0})
            idx = rec["count"]
            if idx >= len(self._durations):
                return 0
            return self._durations[idx]

    # ------------------------------------------------------------------ #
    # Background loop                                                      #
    # ------------------------------------------------------------------ #

    def run(self):
        while True:
            time.sleep(10)
            self._check_unbans()

    def _check_unbans(self):
        now = time.time()
        to_unban = []
        with self._lock:
            for ip, rec in self._records.items():
                if rec["unban_at"] is not None and now >= rec["unban_at"]:
                    to_unban.append((ip, dict(rec)))
                    rec["unban_at"] = None  # cleared; next ban will be permanent

        for ip, rec in to_unban:
            self._unblock(ip)
            logger.info("Unbanned %s (ban #%d)", ip, rec["count"])
            if self._notifier:
                self._notifier.send_unban(
                    ip=ip,
                    ban_count=rec["count"],
                    condition=rec["condition"],
                    rate=rec["rate"],
                    baseline=rec["baseline"],
                )

    # ------------------------------------------------------------------ #
    # Dashboard data                                                       #
    # ------------------------------------------------------------------ #

    def banned_ips(self):
        """Return list of dicts with ip, count, unban_at, condition."""
        now = time.time()
        result = []
        with self._lock:
            for ip, rec in self._records.items():
                if rec["unban_at"] is not None or (
                    rec["count"] >= len(self._durations) and rec["count"] > 0
                ):
                    result.append({
                        "ip": ip,
                        "count": rec["count"],
                        "permanent": rec["unban_at"] is None,
                        "unban_in": max(0, rec["unban_at"] - now)
                        if rec["unban_at"] else None,
                        "condition": rec["condition"],
                    })
        return result
