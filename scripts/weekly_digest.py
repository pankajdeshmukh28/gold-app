"""Weekly gold-savings digest. Runs once a week (Sunday 09:00 PT cron).

Reads docs/history.json + docs/data.json, rolls up the last 7 days of
savings-per-10g observations, formats a single Telegram message, sends.

Design choices:
  * Savings-first framing. US-cheaper is assumed background; the number
    is the story.
  * Handles "warm-up" gracefully: if we have fewer than ~24h of usable
    data points, send a short "not enough data yet" note instead of a
    half-empty digest.
  * Backward-compatible with legacy history entries (pre-v2) that lack
    `savings_inr_per_10g` — we synthesize from `us_per_g`/`in_per_g`
    if `usd_inr` is available, else skip that row.

Env vars:
  DRY_RUN=true  → print the message to stdout, do NOT send Telegram.
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID → required unless DRY_RUN=true.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(THIS_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts.config import DASHBOARD_URL, DATA_FILE, HISTORY_FILE  # noqa: E402
from scripts.notifier import (  # noqa: E402
    NotifierNotConfigured,
    get_broadcast_notifier,
)

# Digest publishes on Sun 16:00 UTC — 09:00 PDT (summer) / 08:00 PST (winter).
# We render local times in the message using this offset. DST drift of ±1h
# is irrelevant for a "Sunday morning" pulse.
LOCAL_TZ_HOURS = -7

MIN_ROWS_FOR_FULL_DIGEST = 3


def _parse_ts(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _load_json(path: str, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _savings_for_entry(entry: dict, fx_fallback: Optional[float] = None) -> Optional[float]:
    """Return savings_inr_per_10g for a history row, synthesizing if missing.

    `fx_fallback` is used for pre-v2 history rows that don't carry their own
    USD/INR rate. It's an approximation — the USD/INR of 7 days ago wasn't
    necessarily what it is today — but it's accurate to ~1% over a week,
    which is well within the noise floor of a "savings rollup" digest.
    """
    if "savings_inr_per_10g" in entry and entry["savings_inr_per_10g"] is not None:
        try:
            return float(entry["savings_inr_per_10g"])
        except (TypeError, ValueError):
            pass

    us_per_g = entry.get("us_per_g")
    in_per_g = entry.get("in_per_g")
    usd_inr = entry.get("usd_inr") or fx_fallback
    if usd_inr and us_per_g is not None and in_per_g is not None:
        try:
            return (float(in_per_g) - float(us_per_g)) * 10.0 * float(usd_inr)
        except (TypeError, ValueError):
            return None
    return None


def _friendly_day(dt: datetime, tz_offset_hours: int) -> str:
    return (dt + timedelta(hours=tz_offset_hours)).strftime("%a")


def _friendly_date(dt: datetime, tz_offset_hours: int) -> str:
    # %-d is Linux-only; GH Actions runs Linux so that's fine.
    return (dt + timedelta(hours=tz_offset_hours)).strftime("%b %-d")


def _collect_week(
    history: List[dict],
    now_utc: datetime,
    fx_fallback: Optional[float] = None,
) -> List[Tuple[datetime, float]]:
    """Return [(ts, savings_inr_per_10g), ...] for entries in the past 7 days,
    sorted ascending by timestamp."""
    cutoff = now_utc - timedelta(days=7)
    rows: List[Tuple[datetime, float]] = []
    for e in history:
        ts = _parse_ts(e.get("t", ""))
        if ts is None or ts < cutoff or ts > now_utc:
            continue
        sav = _savings_for_entry(e, fx_fallback=fx_fallback)
        if sav is None:
            continue
        rows.append((ts, sav))
    rows.sort(key=lambda r: r[0])
    return rows


def _warmup_message(now_utc: datetime, row_count: int) -> str:
    end_local = _friendly_date(now_utc, LOCAL_TZ_HOURS)
    qualifier = "no data points" if row_count == 0 else f"only {row_count} data point(s)"
    return (
        f"📅 <b>Weekly gold pulse — {end_local}</b>\n\n"
        f"Tracker is still warming up — {qualifier} in the past 7 days. "
        "Next Sunday's digest will have a full week of savings data to roll up.\n\n"
        f'🔗 <a href="{DASHBOARD_URL}">View live dashboard →</a>'
    )


def build_message(data: Optional[dict], history: List[dict], now_utc: Optional[datetime] = None) -> str:
    now_utc = now_utc or datetime.now(timezone.utc)
    fx_fallback = ((data or {}).get("inputs") or {}).get("usd_inr")
    rows = _collect_week(history, now_utc, fx_fallback=fx_fallback)

    if len(rows) < MIN_ROWS_FOR_FULL_DIGEST:
        return _warmup_message(now_utc, len(rows))

    savings_values = [v for _, v in rows]
    current = savings_values[-1]
    baseline_ts, baseline = rows[0]
    trend = current - baseline
    lo_ts, lo = min(rows, key=lambda r: r[1])
    hi_ts, hi = max(rows, key=lambda r: r[1])
    avg = sum(savings_values) / len(savings_values)

    # Date range for the headline — uses the actual baseline, not "now - 7d",
    # so early weeks (when we have <7d of history) read honestly.
    date_range = f"{_friendly_date(baseline_ts, LOCAL_TZ_HOURS)} – {_friendly_date(now_utc, LOCAL_TZ_HOURS)}"

    # Trend phrasing — if baseline is <6 days ago, say "vs {day}"; otherwise
    # "vs last Sunday" is accurate enough.
    span_days = (now_utc - baseline_ts).total_seconds() / 86_400
    if span_days >= 6:
        trend_vs = "vs last Sunday"
    else:
        trend_vs = f"vs {_friendly_day(baseline_ts, LOCAL_TZ_HOURS)}"

    lines = [
        f"📅 <b>Weekly gold pulse — {date_range}</b>",
        "",
        f"💰 <b>₹{current:,.0f}/10g</b> saved buying in US right now",
    ]
    if abs(trend) >= 50:  # ignore sub-₹50 noise
        arrow = "↑" if trend > 0 else "↓"
        lines.append(f"   <i>{arrow} ₹{abs(trend):,.0f} {trend_vs}</i>")
    else:
        lines.append(f"   <i>≈ flat {trend_vs}</i>")

    lines += [
        "",
        "<b>This week:</b>",
        f" • Low:  ₹{lo:,.0f}  ({_friendly_day(lo_ts, LOCAL_TZ_HOURS)})",
        f" • High: ₹{hi:,.0f}  ({_friendly_day(hi_ts, LOCAL_TZ_HOURS)})  ← best moment",
        f" • Avg:  ₹{avg:,.0f}",
    ]

    # If the lowest was actually *negative* (India was briefly cheaper),
    # call that out subtly — otherwise the "Low" line reads oddly.
    if lo < 0:
        lines.append(
            f"   <i>(India was ₹{-lo:,.0f}/10g cheaper at the week low — rare)</i>"
        )

    # Snapshot block from the latest data.json (if present)
    verdict = ((data or {}).get("verdict") or {})
    inputs = ((data or {}).get("inputs") or {})
    us_inr = verdict.get("us_inr_per_10g")
    us_usd = verdict.get("us_usd_per_10g")
    in_inr = verdict.get("india_inr_per_10g")
    in_usd = verdict.get("india_usd_per_10g")
    us_src = (inputs.get("us_source") or "").upper()
    in_src = (inputs.get("india_source") or "").upper()
    in_sess = inputs.get("india_session") or ""
    usd_inr = inputs.get("usd_inr")

    if us_inr and in_inr:
        us_bits = [f"₹{us_inr:,.0f}"]
        if us_usd:
            us_bits.append(f"(${us_usd:,.2f})")
        if us_src:
            us_bits.append(f"· {us_src}")
        in_bits = [f"₹{in_inr:,.0f}"]
        if in_usd:
            in_bits.append(f"(${in_usd:,.2f}, incl. 3% GST)")
        if in_src:
            ibja_tag = in_src + (f" {in_sess}" if in_sess else "")
            in_bits.append(f"· {ibja_tag}")
        lines += [
            "",
            "<b>Snapshot right now:</b>",
            f" • US: {' '.join(us_bits)}",
            f" • India: {' '.join(in_bits)}",
        ]
        if usd_inr:
            lines.append(f" • USD→INR: ₹{usd_inr:.2f}")

    lines += [
        "",
        f"<i>{len(rows)} checkpoints this week.</i>",
        "",
        f'🔗 <a href="{DASHBOARD_URL}">View live dashboard →</a>',
    ]
    return "\n".join(lines)


def main() -> int:
    dry = os.environ.get("DRY_RUN", "").lower() == "true"

    data = _load_json(DATA_FILE, None)
    history = _load_json(HISTORY_FILE, [])
    if not isinstance(history, list):
        history = []

    msg = build_message(data, history)

    print("--- digest message ---")
    print(msg)
    print("--- end ---")

    if dry:
        print("[digest] DRY_RUN=true — not sending")
        return 0

    try:
        notifier = get_broadcast_notifier()
        result = notifier.send(msg)
        print(
            f"[digest] sent={result['sent']} failed={result['failed']} "
            f"pruned={result['pruned']} of {result['targets']} targets"
        )
        return 0
    except NotifierNotConfigured as e:
        print(f"[digest] skipped — {e}")
        return 2
    except Exception as e:
        print(f"[digest] failed: {e}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
