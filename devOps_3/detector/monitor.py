import json
import os
import time


def tail_log(path, callback):
    """
    Continuously tail a JSON-per-line Nginx access log and call callback(entry)
    for each parsed line. Waits for the file to exist, then seeks to the end
    so we only process new lines written after startup.
    """
    while not os.path.exists(path):
        time.sleep(1)

    with open(path, "r") as f:
        f.seek(0, 2)  # start at end — ignore historical lines
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.05)
                continue
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                _normalise(entry)
                callback(entry)
            except (json.JSONDecodeError, KeyError):
                pass


def _normalise(entry):
    """
    Ensure required fields exist and have correct types.
    Fills in safe defaults when Nginx omits or logs '-' for a field.
    """
    entry.setdefault("source_ip", "0.0.0.0")
    entry.setdefault("method", "UNKNOWN")
    entry.setdefault("path", "/")
    entry.setdefault("http_host", "")
    entry.setdefault("user_agent", "")

    # status may be logged as int or string
    try:
        entry["status"] = int(entry.get("status", 0))
    except (ValueError, TypeError):
        entry["status"] = 0

    try:
        entry["response_size"] = int(entry.get("response_size", 0))
    except (ValueError, TypeError):
        entry["response_size"] = 0

    # Strip X-Forwarded-For chain — take the first (leftmost) IP
    ip = entry["source_ip"]
    if "," in ip:
        ip = ip.split(",")[0].strip()
    entry["source_ip"] = ip
