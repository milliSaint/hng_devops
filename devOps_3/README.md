# HNG Stage 3 — Anomaly Detection Engine

A real-time DDoS/anomaly detection daemon built alongside Nextcloud on Docker.

## Live Links
- **Metrics Dashboard:** http://hngmetrics.unicornocean.ai
- **Nextcloud:** http://188.166.161.206
- **Server IP:** `188.166.161.206`

---

## Language Choice

**Python** — rapid iteration on data-structure logic (deques, stats), excellent
stdlib support for file tailing and threading, and psutil/Flask make the
dashboard trivial to wire up. The detection logic is CPU-light (O(1) per
request with deque evictions), so Python's GIL is not a bottleneck here.

---

## How the Sliding Window Works

Each source IP gets its own `collections.deque` storing the Unix timestamps
of every request it made. A separate global deque stores all request timestamps.

On every incoming log line:
1. `now = time.time()` is appended to the IP deque and the global deque.
2. All entries where `now - timestamp > 60` are evicted from the *left* of
   the deque (`popleft()`), because deques are ordered oldest-to-newest.
3. `len(deque)` is then the exact request count for the last 60 seconds —
   no counters, no buckets, no per-minute approximations.

Eviction is O(k) where k is the number of stale entries, which is typically
tiny since entries are evicted as they age out rather than in bulk.

---

## How the Baseline Works

**Window:** 30 minutes of per-second request counts (1800 data points max).

**Structure:** A `deque` of `(timestamp_second, count)` pairs. Every second
that completes, its count is appended and entries older than 1800 seconds are
evicted from the left.

**Per-hour slots:** A `dict[hour, list]` stores the same per-second counts
keyed by hour-of-day (0–23). When the current hour's slot has ≥ 30 data points
it is used in preference to the rolling 30-min window, so the baseline reflects
the actual traffic pattern for this time of day.

**Recalculation:** Every 60 seconds a background thread computes mean and
stddev from whichever source has enough data. Floor values (`baseline_floor_mean=1.0`,
`baseline_floor_stddev=0.5`) prevent division-by-zero and avoid false positives
during low-traffic periods.

**Audit log entry:** every recalculation writes a `BASELINE_RECALC` line so
you can graph mean over time.

---

## How Detection Makes a Decision

For each request the detector:

1. Reads `effective_mean` and `effective_stddev` from the baseline.
2. Computes the IP's rate from its 60-second deque.
3. Computes `z_score = (rate - mean) / stddev`.
4. **Flags** the IP if **either** condition fires first:
   - `z_score > 3.0` (statistically extreme)
   - `rate > 5 × mean` (absolute multiplier, catches bursts during low-stddev periods)
5. **Error surge** check: if the IP's 4xx/5xx fraction in the window exceeds
   `3 × baseline_error_rate`, both thresholds are tightened by 50% for that IP,
   making detection more sensitive.
6. The same check runs on the global deque for global anomalies (Slack alert only, no block).

---

## How iptables Blocks an IP

```bash
iptables -I INPUT -s <ip> -j DROP
```

`-I INPUT` inserts the rule at position 1 (top priority).  
`-j DROP` silently discards the packet — no RST, no ICMP unreachable.  
The rule is verified idempotently before insertion (`iptables -C`).  
Removal on unban: `iptables -D INPUT -s <ip> -j DROP`.

The detector container runs with `cap_add: NET_ADMIN` and `network_mode: host`
so its iptables calls affect the host kernel's netfilter tables directly.

---

## Setup (Fresh VPS → Running Stack)

```bash
# 1. Provision Ubuntu 22.04 VPS (2 vCPU, 4 GB RAM minimum)

# 2. Install Docker
curl -fsSL https://get.docker.com | sh
usermod -aG docker $USER && newgrp docker

# 3. Clone repo
git clone https://github.com/unicornoceanldadev/millisaint.git
cd millisaint/devOps_3

# 4. Configure environment
cp .env.example .env
nano .env          # set SERVER_IP, SLACK_WEBHOOK_URL, passwords

# 5. Launch stack
docker compose up -d

# 6. Follow detector logs
docker compose logs -f detector

# 7. Verify dashboard (on host or via SSH tunnel)
curl http://localhost:8080/health

# 8. Point metrics.<domain> DNS A record → VPS IP
# 9. (Optional) add Nginx vhost on port 443 to proxy :8080 with TLS
```

---

## Screenshots

| File | Contents |
|------|----------|
| `screenshots/Tool-running.png` | Daemon processing log lines |
| `screenshots/Ban-slack.png` | Slack ban notification |
| `screenshots/Unban-slack.png` | Slack unban notification |
| `screenshots/Global-alert-slack.png` | Slack global anomaly alert |
| `screenshots/Iptables-banned.png` | `sudo iptables -L -n` |
| `screenshots/Audit-log.png` | Structured audit log |
| `screenshots/Baseline-graph.png` | Dashboard baseline history graph |
