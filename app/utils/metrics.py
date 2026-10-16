"""PhantomAPI — Request metrics (thread-safe).

Tracks load: total requests, in-flight, outcomes, latency.
Exposed via GET /v1/stats.
"""

import threading
import time

_lock = threading.Lock()
_started_at = time.time()
_stats = {
    "total": 0,
    "ok": 0,
    "errors": 0,
    "busy_rejected": 0,
    "active": 0,
    "total_latency_s": 0.0,
}


def record_start() -> float:
    """Mark a request start. Returns the start timestamp."""
    with _lock:
        _stats["total"] += 1
        _stats["active"] += 1
    return time.time()


def record_end(started: float, ok: bool) -> None:
    """Mark a request end."""
    with _lock:
        _stats["active"] -= 1
        if ok:
            _stats["ok"] += 1
        else:
            _stats["errors"] += 1
        _stats["total_latency_s"] += time.time() - started


def record_busy() -> None:
    """Mark a request rejected because all chat slots were busy."""
    with _lock:
        _stats["busy_rejected"] += 1


def snapshot() -> dict:
    """Return a point-in-time copy of the stats."""
    with _lock:
        s = dict(_stats)
    done = s["ok"] + s["errors"]
    s["avg_latency_s"] = round(s["total_latency_s"] / done, 2) if done else 0.0
    s["uptime_s"] = int(time.time() - _started_at)
    return s
