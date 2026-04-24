"""Persistent state for drop detection, price history, and subscribers.

File layout (all under docs/ so GitHub Pages can't serve what shouldn't be
served — subscribers.json + deny_list.json sit in docs/ only because the
commit pipeline already covers docs/; they contain chat IDs which alone
are not useful without the bot token, but if you later want them hidden
from Pages, move them above docs/ and update SUBSCRIBERS_FILE):
  docs/state.json          — drop-detection state + bot update offset
  docs/history.json        — rolling checkpoints for the sparkline
  docs/subscribers.json    — [{chat_id, username, first_name, joined_at}]
  docs/deny_list.json      — [chat_id, chat_id, ...] (blocked users)
"""
import json
import os
from datetime import datetime, timezone
from typing import List, Optional

from scripts.config import (
    DENY_LIST_FILE,
    HISTORY_FILE,
    HISTORY_MAX_POINTS,
    STATE_FILE,
    SUBSCRIBERS_FILE,
)


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


# ---------------------------------------------------------------------------
# Telegram bot: update-offset tracking (for getUpdates long-polling)
# ---------------------------------------------------------------------------

def get_last_update_id(state: dict) -> Optional[int]:
    val = state.get("last_telegram_update_id")
    return None if val is None else int(val)


def update_last_update_id(state: dict, update_id: int) -> None:
    state["last_telegram_update_id"] = int(update_id)


# ---------------------------------------------------------------------------
# Subscribers + deny list
# ---------------------------------------------------------------------------

def _load_json_list(path: str) -> list:
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_json_list(path: str, data: list) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_subscribers() -> List[dict]:
    """Return a list of subscriber dicts.

    Shape:
      {"chat_id": 123, "username": "foo", "first_name": "Foo",
       "joined_at": "2026-04-23T...", "last_seen_at": "..."}
    """
    return _load_json_list(SUBSCRIBERS_FILE)


def save_subscribers(subscribers: List[dict]) -> None:
    _save_json_list(SUBSCRIBERS_FILE, subscribers)


def find_subscriber(subscribers: List[dict], chat_id: int) -> Optional[dict]:
    for s in subscribers:
        if int(s.get("chat_id", 0)) == int(chat_id):
            return s
    return None


def add_subscriber(subscribers: List[dict], user_info: dict) -> bool:
    """Add a subscriber if not already present. Returns True if newly added."""
    chat_id = int(user_info["chat_id"])
    existing = find_subscriber(subscribers, chat_id)
    if existing:
        existing["last_seen_at"] = _utcnow_iso()
        if user_info.get("username"):
            existing["username"] = user_info["username"]
        if user_info.get("first_name"):
            existing["first_name"] = user_info["first_name"]
        return False
    subscribers.append(
        {
            "chat_id": chat_id,
            "username": user_info.get("username"),
            "first_name": user_info.get("first_name"),
            "joined_at": _utcnow_iso(),
            "last_seen_at": _utcnow_iso(),
        }
    )
    return True


def remove_subscriber(subscribers: List[dict], chat_id: int) -> bool:
    """Remove subscriber by chat_id. Returns True if something was removed."""
    target = int(chat_id)
    before = len(subscribers)
    subscribers[:] = [s for s in subscribers if int(s.get("chat_id", 0)) != target]
    return len(subscribers) < before


def load_deny_list() -> List[int]:
    return [int(x) for x in _load_json_list(DENY_LIST_FILE) if x is not None]


def save_deny_list(deny: List[int]) -> None:
    _save_json_list(DENY_LIST_FILE, sorted(set(int(x) for x in deny)))


def is_denied(deny: List[int], chat_id: int) -> bool:
    return int(chat_id) in set(deny)
