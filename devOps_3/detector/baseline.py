"""
Rolling baseline tracker.

State:
  per_second_counts  — deque of (timestamp_second, count) pairs covering the
                       last baseline_window_minutes * 60 seconds. Evicted when
                       the slot is older than the window.
  hourly_slots       — dict keyed by hour-of-day (0-23); each value is a list
                       of per-second counts recorded during that hour. Preferred
                       as baseline source when it has >= min_samples entries.

Recalculated every baseline_recalc_interval seconds by a background thread.
"""
import math
import os
import threading
import time
from collections import defaultdict, deque


class BaselineTracker:
    def __init__(self, config, audit_log_fn=None):
        window_secs = config["baseline_window_minutes"] * 60
        self._window_secs = window_secs
        self._recalc_interval = config["baseline_recalc_interval"]
        self._min_samples = config["baseline_min_samples"]
        self._floor_mean = config["baseline_floor_mean"]
        self._floor_stddev = config["baseline_floor_stddev"]
        self._audit = audit_log_fn or (lambda msg: None)

        # One bucket per second: (second_timestamp, count)
        self._per_second: deque = deque()
        # Current-second accumulator
        self._current_second = int(time.time())
        self._current_count = 0

        # Per-hour historical counts (list of per-second values)
        self._hourly: dict = defaultdict(list)

        # Published baseline (updated every recalc_interval)
        self._lock = threading.Lock()
        self._effective_mean = config["baseline_floor_mean"]
        self._effective_stddev = config["baseline_floor_stddev"]

        # Baseline error rate (fraction of requests that are 4xx/5xx)
        self._error_counts: deque = deque()    # (second_ts, error_count)
        self._current_error_count = 0
        self._baseline_error_rate = 0.0

        # History for dashboard graph: list of (ts, mean) tuples
        self._history: deque = deque(maxlen=120)  # last 2 hours of recalcs

    # ------------------------------------------------------------------ #
    # Called by monitor thread for every log entry                         #
    # ------------------------------------------------------------------ #

    def record(self, entry):
        now_sec = int(time.time())
        is_error = entry["status"] >= 400

        with self._lock:
            if now_sec != self._current_second:
                self._flush_second(self._current_second, self._current_count,
                                   self._current_error_count)
                self._current_second = now_sec
                self._current_count = 0
                self._current_error_count = 0
            self._current_count += 1
            if is_error:
                self._current_error_count += 1

    def _flush_second(self, ts, count, error_count):
        """Move the completed second's count into the rolling deques."""
        cutoff = ts - self._window_secs
        self._per_second.append((ts, count))
        self._error_counts.append((ts, error_count))

        # Evict old entries
        while self._per_second and self._per_second[0][0] < cutoff:
            self._per_second.popleft()
        while self._error_counts and self._error_counts[0][0] < cutoff:
            self._error_counts.popleft()

        # Store in hourly slot (keep last 3600 values per slot = 1 hour)
        hour = int((ts % 86400) / 3600)
        slot = self._hourly[hour]
        slot.append(count)
        if len(slot) > 3600:
            slot.pop(0)

    # ------------------------------------------------------------------ #
    # Background recalculation loop                                        #
    # ------------------------------------------------------------------ #

    def recalc_loop(self):
        while True:
            time.sleep(self._recalc_interval)
            self._recalculate()

    def _recalculate(self):
        with self._lock:
            # Flush the in-progress second before recalculating
            now_sec = int(time.time())
            if now_sec != self._current_second:
                self._flush_second(self._current_second, self._current_count,
                                   self._current_error_count)
                self._current_second = now_sec
                self._current_count = 0
                self._current_error_count = 0

            hour = int((now_sec % 86400) / 3600)
            hourly_counts = self._hourly.get(hour, [])

            # Prefer current hour's data if it has enough samples
            if len(hourly_counts) >= self._min_samples:
                counts = hourly_counts
                source = "hourly"
            else:
                counts = [c for _, c in self._per_second]
                source = "rolling"

            n = len(counts)
            if n < self._min_samples:
                return  # not enough data yet

            mean = sum(counts) / n
            variance = sum((x - mean) ** 2 for x in counts) / n
            stddev = math.sqrt(variance)

            self._effective_mean = max(self._floor_mean, mean)
            self._effective_stddev = max(self._floor_stddev, stddev)

            # Error rate: errors per second / total per second
            total = sum(c for _, c in self._per_second) or 1
            errors = sum(c for _, c in self._error_counts)
            self._baseline_error_rate = errors / total

            self._history.append((now_sec, self._effective_mean))

        self._audit(
            f"BASELINE_RECALC | source={source} | mean={self._effective_mean:.3f} "
            f"| stddev={self._effective_stddev:.3f} | samples={n} | hour={hour}"
        )

    # ------------------------------------------------------------------ #
    # Read-only accessors (safe to call without lock from other threads)   #
    # ------------------------------------------------------------------ #

    @property
    def effective_mean(self):
        with self._lock:
            return self._effective_mean

    @property
    def effective_stddev(self):
        with self._lock:
            return self._effective_stddev

    @property
    def baseline_error_rate(self):
        with self._lock:
            return self._baseline_error_rate

    @property
    def history(self):
        with self._lock:
            return list(self._history)
