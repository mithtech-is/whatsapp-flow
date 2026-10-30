"""Token-bucket rate limiter backed by Redis (frappe.cache()).

Used by the send guard to throttle outbound sends per WhatsApp Account, protecting the
number's Meta throughput tier / quality rating. Defaults are overridable via
WhatsApp Settings.wd_rate_limits (JSON: {"<account>": {"rate": N_per_sec, "burst": M}}).
"""

from __future__ import annotations

import time

import frappe

_DEFAULT_RATE = 20  # messages/sec
_DEFAULT_BURST = 40


def _config(account: str) -> tuple[float, float]:
    try:
        raw = frappe.db.get_single_value("WhatsApp Settings", "wd_rate_limits")
        cfg = frappe.parse_json(raw) if raw else {}
        acc = cfg.get(account, {})
        return float(acc.get("rate", _DEFAULT_RATE)), float(acc.get("burst", _DEFAULT_BURST))
    except Exception:
        return float(_DEFAULT_RATE), float(_DEFAULT_BURST)


def take(account: str, tokens: float = 1.0) -> bool:
    """Try to consume `tokens` for `account`. Returns False if the bucket is empty."""
    if not account:
        return True
    rate, burst = _config(account)
    key = f"wd:ratelimit:{account}"
    cache = frappe.cache()
    now = time.time()

    data = cache.get_value(key) or {}
    level = float(data.get("level", burst))
    last = float(data.get("ts", now))

    # Refill since last check, capped at burst.
    level = min(burst, level + (now - last) * rate)
    if level < tokens:
        cache.set_value(key, {"level": level, "ts": now}, expires_in_sec=60)
        return False

    level -= tokens
    cache.set_value(key, {"level": level, "ts": now}, expires_in_sec=60)
    return True
