"""
Live metrics dashboard served on dashboard_port (default 8080).

Refreshes every 3 seconds via meta-refresh. Shows:
  - Uptime
  - Global req/s (last 60s window)
  - Top 10 source IPs
  - Banned IPs with countdown
  - Effective mean / stddev
  - CPU and memory usage
  - Baseline graph (mean over time)
"""
import time

import psutil
from flask import Flask, Response

_app = Flask(__name__)
_state = {}  # populated by start_dashboard()

_START = time.time()

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="3">
  <title>HNG Anomaly Detector</title>
  <style>
    body {{ font-family: monospace; background: #0d1117; color: #c9d1d9; padding: 20px; }}
    h1 {{ color: #58a6ff; }}
    h2 {{ color: #79c0ff; border-bottom: 1px solid #30363d; padding-bottom: 4px; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
    th, td {{ border: 1px solid #30363d; padding: 6px 12px; text-align: left; }}
    th {{ background: #161b22; color: #79c0ff; }}
    tr:nth-child(even) {{ background: #161b22; }}
    .banned {{ color: #f85149; font-weight: bold; }}
    .stat {{ display: inline-block; background: #161b22; border: 1px solid #30363d;
             padding: 10px 20px; margin: 6px; border-radius: 6px; }}
    .stat-value {{ font-size: 2em; color: #58a6ff; }}
    .stat-label {{ font-size: 0.8em; color: #8b949e; }}
    .graph {{ background: #161b22; border: 1px solid #30363d; padding: 10px; margin: 10px 0; }}
  </style>
</head>
<body>
<h1>HNG Anomaly Detection Engine</h1>

<div>
  <div class="stat">
    <div class="stat-value">{uptime}</div>
    <div class="stat-label">Uptime</div>
  </div>
  <div class="stat">
    <div class="stat-value">{global_rate}</div>
    <div class="stat-label">Global req/s (60s window)</div>
  </div>
  <div class="stat">
    <div class="stat-value">{mean:.2f}</div>
    <div class="stat-label">Baseline mean (req/s)</div>
  </div>
  <div class="stat">
    <div class="stat-value">{stddev:.2f}</div>
    <div class="stat-label">Baseline stddev</div>
  </div>
  <div class="stat">
    <div class="stat-value">{cpu:.1f}%</div>
    <div class="stat-label">CPU usage</div>
  </div>
  <div class="stat">
    <div class="stat-value">{mem:.1f}%</div>
    <div class="stat-label">Memory usage</div>
  </div>
</div>

<h2>Banned IPs ({ban_count})</h2>
<table>
  <tr><th>IP</th><th>Ban #</th><th>Condition</th><th>Status</th></tr>
  {banned_rows}
</table>

<h2>Top 10 Source IPs (last 60s)</h2>
<table>
  <tr><th>IP</th><th>Requests</th></tr>
  {top_rows}
</table>

<h2>Baseline History (mean req/s per recalculation)</h2>
<div class="graph">
  <table>
    <tr><th>Time</th><th>Effective Mean (req/s)</th><th>Bar</th></tr>
    {history_rows}
  </table>
</div>

<p style="color:#8b949e; font-size:0.8em;">
  Last refreshed: {now} | Auto-refresh every 3s
</p>
</body>
</html>"""


@_app.route("/")
def index():
    baseline = _state["baseline"]
    detector = _state["detector"]
    unbanner = _state["unbanner"]

    uptime_secs = int(time.time() - _START)
    h, rem = divmod(uptime_secs, 3600)
    m, s = divmod(rem, 60)
    uptime_str = f"{h:02d}:{m:02d}:{s:02d}"

    banned = unbanner.banned_ips()
    banned_rows = ""
    for b in banned:
        if b["permanent"]:
            status = "PERMANENT"
        else:
            remaining = int(b["unban_in"] or 0)
            status = f"unban in {remaining}s"
        banned_rows += (
            f'<tr class="banned"><td>{b["ip"]}</td><td>{b["count"]}</td>'
            f'<td>{b["condition"]}</td><td>{status}</td></tr>'
        )
    if not banned_rows:
        banned_rows = '<tr><td colspan="4">No banned IPs</td></tr>'

    top = detector.top_ips(10)
    top_rows = "".join(
        f"<tr><td>{ip}</td><td>{count}</td></tr>" for ip, count in top
    ) or '<tr><td colspan="2">No traffic yet</td></tr>'

    history = baseline.history
    max_mean = max((m for _, m in history), default=1.0)
    history_rows = ""
    for ts, mean_val in history[-20:]:  # show last 20 recalcs
        bar_len = int((mean_val / max_mean) * 40) if max_mean > 0 else 0
        bar = "█" * bar_len
        t = time.strftime("%H:%M:%S", time.gmtime(ts))
        history_rows += f"<tr><td>{t}</td><td>{mean_val:.2f}</td><td>{bar}</td></tr>"
    if not history_rows:
        history_rows = '<tr><td colspan="3">Collecting data...</td></tr>'

    html = HTML_TEMPLATE.format(
        uptime=uptime_str,
        global_rate=detector.global_rate(),
        mean=baseline.effective_mean,
        stddev=baseline.effective_stddev,
        cpu=psutil.cpu_percent(interval=None),
        mem=psutil.virtual_memory().percent,
        ban_count=len(banned),
        banned_rows=banned_rows,
        top_rows=top_rows,
        history_rows=history_rows,
        now=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )
    return Response(html, mimetype="text/html")


@_app.route("/health")
def health():
    return {"status": "ok", "uptime": int(time.time() - _START)}


def start_dashboard(config, baseline, detector, unbanner):
    _state["baseline"] = baseline
    _state["detector"] = detector
    _state["unbanner"] = unbanner
    port = config.get("dashboard_port", 8080)
    _app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
