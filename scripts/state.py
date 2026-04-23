"""Persistent state for drop detection and price history."""
import json
import os
from datetime import datetime, timezone
from typing import Optional

from scripts.config import HISTORY_FILE, HISTORY_MAX_POINTS, STATE_FILE


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_FILE) or ".", exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def get_last_us_price(state: dict) -> Optional[float]:
    return state.get("last_us_price_usd")


def update_last_us_price(state: dict, price: float) -> None:
    state["last_us_price_usd"] = float(price)
    state["last_updated"] = _utcnow_iso()


def get_last_savings_inr(state: dict) -> Optional[float]:
    """Last observed 'buying-in-US savings' in INR per 10g.
    Positive = US was cheaper; negative = India was cheaper.
    """
    val = state.get("last_savings_inr_per_10g")
    return None if val is None else float(val)


def update_last_savings_inr(state: dict, savings_inr_per_10g: float) -> None:
    state["last_savings_inr_per_10g"] = float(savings_inr_per_10g)
    state["last_updated"] = _utcnow_iso()


def load_history() -> list:
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def append_history(entry: dict) -> None:
    history = load_history()
    history.append(entry)
    history = history[-HISTORY_MAX_POINTS:]
    os.makedirs(os.path.dirname(HISTORY_FILE) or ".", exist_ok=True)
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)
