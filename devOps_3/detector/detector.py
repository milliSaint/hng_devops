"""
Anomaly detector.

Maintains two deque-based sliding windows over the last 60 seconds:
  - one per source IP
  - one global (all traffic)

On each request it:
1. Appends to the relevant deques and evicts stale entries.
2. Computes z-score = (rate - mean) / stddev.
3. Flags anomaly if z-score > threshold OR rate > multiplier * mean.
4. Checks error surge: if an IP's 4xx/5xx fraction > error_rate_multiplier *
   baseline_error_rate, tightens that IP's thresholds by surge_factor.
"""
import math
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field


@dataclass
class DetectionResult:
    ip: str
    ip_anomalous: bool = False
    global_anomalous: bool = False
    ip_condition: str = ""
    global_condition: str = ""
    ip_rate: float = 0.0
    global_rate: float = 0.0
    mean: float = 0.0
    stddev: float = 0.0


class AnomalyDetector:
    def __init__(self, config, baseline):
        self._window = config["sliding_window_seconds"]
        self._zscore_threshold = config["zscore_threshold"]
        self._multiplier = config["multiplier_threshold"]
        self._error_multiplier = config["error_rate_multiplier"]
        self._surge_factor = config["error_surge_tighten_factor"]
        self._baseline = baseline

        self._lock = threading.Lock()

        # Per-IP deques: ip -> deque of timestamps
        self._ip_windows: dict = defaultdict(deque)
        # Per-IP error deques: ip -> deque of timestamps for 4xx/5xx
        self._ip_error_windows: dict = defaultdict(deque)

        # Global deque: all request timestamps
        self._global_window: deque = deque()

        # Top-10 tracker: ip -> total count (in current window)
        self._ip_counts: dict = defaultdict(int)

    def check(self, entry) -> DetectionResult:
        ip = entry["source_ip"]
        now = time.time()
        cutoff = now - self._window
        is_error = entry["status"] >= 400

        with self._lock:
            # --- Update per-IP window ---
            ip_dq = self._ip_windows[ip]
            ip_dq.append(now)
            while ip_dq and ip_dq[0] < cutoff:
                ip_dq.popleft()
            ip_rate = len(ip_dq)

            # --- Update per-IP error window ---
            if is_error:
                ip_err_dq = self._ip_error_windows[ip]
                ip_err_dq.append(now)
                while ip_err_dq and ip_err_dq[0] < cutoff:
                    ip_err_dq.popleft()

            # --- Update global window ---
            self._global_window.append(now)
            while self._global_window and self._global_window[0] < cutoff:
                self._global_window.popleft()
            global_rate = len(self._global_window)

            # Update top-10 counter
            self._ip_counts[ip] += 1

            mean = self._baseline.effective_mean
            stddev = self._baseline.effective_stddev
            baseline_error_rate = self._baseline.baseline_error_rate

            # --- Error surge check: tighten thresholds if needed ---
            tighten = 1.0
            ip_total = ip_rate or 1
            ip_errors = len(self._ip_error_windows.get(ip, []))
            ip_error_fraction = ip_errors / ip_total
            if ip_error_fraction > self._error_multiplier * max(baseline_error_rate, 0.01):
                tighten = self._surge_factor

            effective_z = self._zscore_threshold * tighten
            effective_m = self._multiplier * tighten

            result = DetectionResult(ip=ip, mean=mean, stddev=stddev,
                                     ip_rate=ip_rate, global_rate=global_rate)

            # --- Per-IP anomaly ---
            if stddev > 0:
                ip_z = (ip_rate - mean) / stddev
            else:
                ip_z = 0.0

            if ip_z > effective_z:
                result.ip_anomalous = True
                result.ip_condition = f"zscore={ip_z:.2f} > {effective_z:.2f}"
            elif mean > 0 and ip_rate > effective_m * mean:
                result.ip_anomalous = True
                result.ip_condition = (
                    f"rate={ip_rate} > {effective_m:.1f}x mean={mean:.2f}"
                )

            # --- Global anomaly ---
            if stddev > 0:
                global_z = (global_rate - mean) / stddev
            else:
                global_z = 0.0

            if global_z > self._zscore_threshold:
                result.global_anomalous = True
                result.global_condition = (
                    f"global_zscore={global_z:.2f} > {self._zscore_threshold}"
                )
            elif mean > 0 and global_rate > self._multiplier * mean:
                result.global_anomalous = True
                result.global_condition = (
                    f"global_rate={global_rate} > {self._multiplier}x mean={mean:.2f}"
                )

        return result

    def top_ips(self, n=10):
        """Return top-n IPs by window count, as [(ip, count), ...]."""
        with self._lock:
            cutoff = time.time() - self._window
            # Recount from live windows for accuracy
            counts = {
                ip: len([ts for ts in dq if ts >= cutoff])
                for ip, dq in self._ip_windows.items()
            }
        return sorted(counts.items(), key=lambda x: x[1], reverse=True)[:n]

    def global_rate(self):
        with self._lock:
            cutoff = time.time() - self._window
            return sum(1 for ts in self._global_window if ts >= cutoff)
