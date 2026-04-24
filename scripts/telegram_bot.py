"""Telegram bot command processor.

Runs on a cron (every 5 min via .github/workflows/bot-poller.yml),
calls getUpdates with an offset persisted in state.json, routes each
private-chat update to a handler, and commits updated
subscribers.json / deny_list.json / state.json back to the repo.

Commands
--------
Public:
  /start      Subscribe to alerts + weekly digest
  /stop       Unsubscribe
  /help       Show help text
  /status     Current savings snapshot from docs/data.json

Admin-only:
  /list                   List all subscribers
  /kick <id_or_@user>     Remove a subscriber (they can re-subscribe)
  /block <id_or_@user>    Remove + add to deny list (cannot re-subscribe)
  /unblock <id>           Lift a block
  /stats                  Overview — totals + subs this week
  /broadcast <msg>        Send a one-off message to all subscribers

Admin identity is established by TELEGRAM_CHAT_ID + the optional
ADMIN_CHAT_IDS (comma-separated) env vars. See scripts/config.py.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import requests

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(THIS_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts.config import (  # noqa: E402
    ADMIN_CHAT_IDS,
    DATA_FILE,
    MAX_SUBSCRIBERS,
    REQUEST_TIMEOUT,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_UPDATES_LIMIT,
)
from scripts.notifier import send_telegram_message  # noqa: E402
from scripts.state import (  # noqa: E402
    add_subscriber,
    find_subscriber,
    get_last_update_id,
    is_denied,
    load_deny_list,
    load_state,
    load_subscribers,
    remove_subscriber,
    save_deny_list,
    save_state,
    save_subscribers,
    update_last_update_id,
)

DASHBOARD_URL = os.environ.get(
    "DASHBOARD_URL", "https://pankajdeshmukh28.github.io/gold-app/"
)

# Short friendly name used in bot replies. Override via env if you want.
ADMIN_NAME = os.environ.get("ADMIN_NAME", "the admin")


# ---------------------------------------------------------------------------
# Telegram API helpers
# ---------------------------------------------------------------------------

def _get_updates(offset: Optional[int]) -> List[dict]:
    """Fetch pending updates. Uses `offset` to acknowledge prior updates."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    params = {"limit": TELEGRAM_UPDATES_LIMIT, "timeout": 0}
    if offset is not None:
        params["offset"] = offset + 1  # Telegram: offset = last_id + 1
    r = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    payload = r.json()
    if not payload.get("ok"):
        raise RuntimeError(f"getUpdates failed: {payload!r}")
    return payload.get("result", [])


def _reply(chat_id: int, text: str, disable_preview: bool = True) -> None:
    try:
        ok, data = send_telegram_message(
            chat_id=chat_id, message=text, disable_preview=disable_preview
        )
        if not ok:
            print(f"[bot] reply failed chat_id={chat_id}: {data!r}")
    except Exception as e:
        print(f"[bot] reply exception chat_id={chat_id}: {e}")


# ---------------------------------------------------------------------------
# Admin + parsing
# ---------------------------------------------------------------------------

def _is_admin(chat_id: int) -> bool:
    return int(chat_id) in set(ADMIN_CHAT_IDS)


def _parse_command(text: str) -> Tuple[str, str]:
    """Return (command, args_string). Handles '/cmd@botname arg1 arg2'."""
    text = (text or "").strip()
    if not text.startswith("/"):
        return "", ""
    head, _, rest = text.partition(" ")
    # Strip bot-mention suffix: /cmd@mybot → /cmd
    cmd = head.split("@", 1)[0].lower()
    return cmd, rest.strip()


def _resolve_target_chat_id(token: str, subscribers: List[dict]) -> Optional[int]:
    """Given a string from the admin (either a chat_id or @username),
    resolve it against subscribers.json. Returns None if not found."""
    token = (token or "").strip()
    if not token:
        return None
    if token.startswith("@"):
        uname = token[1:].lower()
        for s in subscribers:
            if (s.get("username") or "").lower() == uname:
                return int(s["chat_id"])
        return None
    try:
        return int(token)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Message templates
# ---------------------------------------------------------------------------

WELCOME = (
    "🪙 <b>Welcome to Gold Pulse!</b>\n\n"
    "This bot tracks Costco gold prices vs India's IBJA rate (incl. 3% GST) "
    "and pings you when buying in the US saves meaningfully more than last time.\n\n"
    "<b>What you'll get:</b>\n"
    "• Alerts when savings jump by ≥₹500/10g (usually a few times/month)\n"
    "• A weekly summary every Sunday ~9am PT (low/high/avg for the week)\n\n"
    "<b>Commands:</b>\n"
    "/status — current savings snapshot\n"
    "/help — show this help\n"
    "/stop — unsubscribe anytime\n\n"
    f"Live dashboard: {DASHBOARD_URL}"
)

ALREADY_SUBSCRIBED = (
    "You're already subscribed — you'll keep getting alerts. "
    "Reply /status for the current snapshot or /stop to unsubscribe."
)

GOODBYE = (
    "You're unsubscribed. No more pings. "
    "Reply /start anytime to re-subscribe."
)

NOT_SUBSCRIBED = "You weren't subscribed. Reply /start to subscribe."

HELP = (
    "🪙 <b>Gold Pulse — help</b>\n\n"
    "<b>Commands:</b>\n"
    "/start — subscribe\n"
    "/stop — unsubscribe\n"
    "/status — current savings snapshot\n"
    "/help — this message\n\n"
    f"Dashboard: {DASHBOARD_URL}"
)

CAPPED_FULL = (
    "Subscriptions are temporarily closed (capacity reached). "
    f"Ping {ADMIN_NAME} if you'd like access."
)

DENIED = (
    "You can't subscribe to this bot. "
    f"Contact {ADMIN_NAME} if you think this is a mistake."
)

UNAUTHORIZED = "This command is admin-only."

UNKNOWN_COMMAND = (
    "Unknown command. Try /help for the list of things I can do."
)

NON_PRIVATE_HINT = (
    "Hi! This bot only works in a private (1:1) chat, not in groups. "
    "Tap my name, then send me /start."
)


# ---------------------------------------------------------------------------
# Command handlers
# Each handler returns (reply_text_or_None, dirty_flags_dict)
# dirty_flags: {'subscribers': bool, 'deny': bool, 'state': bool}
# ---------------------------------------------------------------------------

def _dirty() -> Dict[str, bool]:
    return {"subscribers": False, "deny": False, "state": False}


def handle_start(
    chat_id: int,
    user_info: dict,
    subscribers: List[dict],
    deny: List[int],
    state: dict,
) -> Tuple[Optional[str], Dict[str, bool]]:
    d = _dirty()
    if is_denied(deny, chat_id):
        return DENIED, d

    if find_subscriber(subscribers, chat_id):
        return ALREADY_SUBSCRIBED, d

    if MAX_SUBSCRIBERS and len(subscribers) >= MAX_SUBSCRIBERS:
        return CAPPED_FULL, d

    add_subscriber(subscribers, {"chat_id": chat_id, **user_info})
    d["subscribers"] = True
    return WELCOME, d


def handle_stop(
    chat_id: int,
    subscribers: List[dict],
) -> Tuple[Optional[str], Dict[str, bool]]:
    d = _dirty()
    if remove_subscriber(subscribers, chat_id):
        d["subscribers"] = True
        return GOODBYE, d
    return NOT_SUBSCRIBED, d


def handle_help() -> Tuple[str, Dict[str, bool]]:
    return HELP, _dirty()


def handle_status() -> Tuple[str, Dict[str, bool]]:
    try:
        with open(DATA_FILE) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return ("Snapshot isn't available right now. Try again in a bit.", _dirty())

    if data.get("status") == "error":
        return (
            f"Snapshot isn't available right now ({', '.join(data.get('errors', []))[:120]}). "
            "Try again in a bit."
        ), _dirty()

    v = data.get("verdict") or {}
    inputs = data.get("inputs") or {}
    us_inr = v.get("us_inr_per_10g")
    in_inr = v.get("india_inr_per_10g")
    savings = None
    if us_inr is not None and in_inr is not None:
        savings = in_inr - us_inr

    lines = ["🪙 <b>Gold Pulse — right now</b>", ""]
    if savings is not None and savings > 0:
        lines.append(f"💰 <b>₹{savings:,.0f}/10g</b> saved buying in US")
    elif savings is not None:
        lines.append(f"India is ₹{-savings:,.0f}/10g cheaper right now (rare).")
    lines.append("")
    if us_inr:
        us_src = (inputs.get("us_source") or "").upper()
        lines.append(f"US:    ₹{us_inr:,.0f}/10g  ({us_src})")
    if in_inr:
        in_src = (inputs.get("india_source") or "").upper()
        in_sess = inputs.get("india_session") or ""
        lines.append(
            f"India: ₹{in_inr:,.0f}/10g  ({in_src} {in_sess}, incl. 3% GST)"
        )
    if inputs.get("usd_inr"):
        lines.append(f"USD→INR: ₹{inputs['usd_inr']:.2f}")
    lines.append("")
    lines.append(f"Dashboard: {DASHBOARD_URL}")
    return "\n".join(lines), _dirty()


def handle_list(subscribers: List[dict], deny: List[int]) -> Tuple[str, Dict[str, bool]]:
    if not subscribers:
        return ("No subscribers yet.", _dirty())
    # Telegram caps messages at 4096 chars; a thousand-sub list would need
    # paging. At family-and-friends scale we're far below that — but guard.
    rows = []
    for s in subscribers:
        handle = f"@{s['username']}" if s.get("username") else "(no @)"
        name = s.get("first_name") or "?"
        joined = (s.get("joined_at") or "")[:10]
        rows.append(f"• <code>{s['chat_id']}</code>  {name}  {handle}  · {joined}")
    body = "\n".join(rows[:50])
    more = "" if len(rows) <= 50 else f"\n\n…and {len(rows) - 50} more (showing first 50)"
    deny_note = f"\n\nDenied: {len(deny)}" if deny else ""
    return (
        f"<b>Subscribers ({len(subscribers)}):</b>\n{body}{more}{deny_note}",
        _dirty(),
    )


def handle_kick(
    args: str,
    subscribers: List[dict],
) -> Tuple[str, Dict[str, bool]]:
    d = _dirty()
    target = _resolve_target_chat_id(args, subscribers)
    if target is None:
        return ("Usage: /kick <chat_id>  or  /kick @username", d)
    if remove_subscriber(subscribers, target):
        d["subscribers"] = True
        return (f"Kicked <code>{target}</code>. They can re-subscribe.", d)
    return (f"No subscriber with id <code>{target}</code>.", d)


def handle_block(
    args: str,
    subscribers: List[dict],
    deny: List[int],
) -> Tuple[str, Dict[str, bool]]:
    d = _dirty()
    target = _resolve_target_chat_id(args, subscribers)
    if target is None:
        # Allow blocking raw chat_ids even if not currently subscribed.
        try:
            target = int(args.strip())
        except (ValueError, TypeError):
            return ("Usage: /block <chat_id>  or  /block @username", d)

    removed = remove_subscriber(subscribers, target)
    if removed:
        d["subscribers"] = True
    if target not in deny:
        deny.append(target)
        d["deny"] = True
    return (
        f"Blocked <code>{target}</code>."
        + (" (also removed from subscribers)" if removed else ""),
        d,
    )


def handle_unblock(args: str, deny: List[int]) -> Tuple[str, Dict[str, bool]]:
    d = _dirty()
    try:
        target = int(args.strip())
    except (ValueError, TypeError):
        return ("Usage: /unblock <chat_id>", d)
    if target in deny:
        deny.remove(target)
        d["deny"] = True
        return (f"Unblocked <code>{target}</code>.", d)
    return (f"<code>{target}</code> wasn't blocked.", d)


def handle_stats(
    subscribers: List[dict],
    deny: List[int],
) -> Tuple[str, Dict[str, bool]]:
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    recent = 0
    for s in subscribers:
        try:
            joined = datetime.fromisoformat((s.get("joined_at") or "").replace("Z", "+00:00"))
            if joined >= week_ago:
                recent += 1
        except (ValueError, TypeError):
            pass
    return (
        f"<b>Bot stats</b>\n"
        f"• Subscribers: {len(subscribers)} (cap {MAX_SUBSCRIBERS or '∞'})\n"
        f"• New this week: {recent}\n"
        f"• Blocked: {len(deny)}\n"
        f"• Admins: {len(ADMIN_CHAT_IDS)}",
        _dirty(),
    )


def handle_broadcast(
    args: str,
    subscribers: List[dict],
) -> Tuple[str, Dict[str, bool]]:
    """Admin-triggered one-off message to everyone. Uses the broadcast
    notifier directly so behavior (rate-limit, prune) matches price alerts."""
    d = _dirty()
    msg = args.strip()
    if not msg:
        return ("Usage: /broadcast <message>  (plain text or HTML)", d)

    # Local import to avoid cyclic-at-import-time risk; also means a broken
    # notifier config doesn't break the whole bot processor.
    from scripts.notifier import get_broadcast_notifier

    try:
        result = get_broadcast_notifier().send(msg)
    except Exception as e:
        return (f"Broadcast failed: {e}", d)

    # BroadcastNotifier may have pruned subscribers; reload for report.
    # (It already saved the cleaned file; we just resync in-memory state.)
    subscribers[:] = load_subscribers()
    if result.get("pruned"):
        d["subscribers"] = True  # keep the outer save_subscribers a no-op, harmless

    errors_tail = (
        ("\n" + "\n".join(f"  - {cid}: {err[:60]}" for cid, err in result["errors"][:5]))
        if result.get("errors")
        else ""
    )
    return (
        f"Broadcast done: sent={result['sent']} failed={result['failed']} "
        f"pruned={result['pruned']} of {result['targets']} targets.{errors_tail}",
        d,
    )


# ---------------------------------------------------------------------------
# Update router
# ---------------------------------------------------------------------------

def _extract_user_info(message: dict) -> dict:
    u = message.get("from") or {}
    return {
        "username": u.get("username"),
        "first_name": u.get("first_name"),
    }


def _process_message(
    message: dict,
    subscribers: List[dict],
    deny: List[int],
    state: dict,
) -> Dict[str, bool]:
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    chat_type = chat.get("type", "")
    if chat_id is None:
        return _dirty()

    text = message.get("text") or ""
    cmd, args = _parse_command(text)

    # Gentle nudge when someone adds the bot to a group — don't route commands.
    if chat_type != "private":
        if cmd == "/start":
            _reply(chat_id, NON_PRIVATE_HINT)
        return _dirty()

    user_info = _extract_user_info(message)
    is_admin = _is_admin(chat_id)

    # No command → ignore silently. Keeps the bot from chatting back at
    # arbitrary text. (We don't want to be an AI chatbot.)
    if not cmd:
        return _dirty()

    reply: Optional[str]
    dirty: Dict[str, bool]

    if cmd == "/start":
        reply, dirty = handle_start(chat_id, user_info, subscribers, deny, state)
    elif cmd == "/stop":
        reply, dirty = handle_stop(chat_id, subscribers)
    elif cmd == "/help":
        reply, dirty = handle_help()
    elif cmd == "/status":
        reply, dirty = handle_status()
    elif cmd == "/list":
        if not is_admin:
            reply, dirty = UNAUTHORIZED, _dirty()
        else:
            reply, dirty = handle_list(subscribers, deny)
    elif cmd == "/kick":
        if not is_admin:
            reply, dirty = UNAUTHORIZED, _dirty()
        else:
            reply, dirty = handle_kick(args, subscribers)
    elif cmd == "/block":
        if not is_admin:
            reply, dirty = UNAUTHORIZED, _dirty()
        else:
            reply, dirty = handle_block(args, subscribers, deny)
    elif cmd == "/unblock":
        if not is_admin:
            reply, dirty = UNAUTHORIZED, _dirty()
        else:
            reply, dirty = handle_unblock(args, deny)
    elif cmd == "/stats":
        if not is_admin:
            reply, dirty = UNAUTHORIZED, _dirty()
        else:
            reply, dirty = handle_stats(subscribers, deny)
    elif cmd == "/broadcast":
        if not is_admin:
            reply, dirty = UNAUTHORIZED, _dirty()
        else:
            reply, dirty = handle_broadcast(args, subscribers)
    else:
        reply, dirty = UNKNOWN_COMMAND, _dirty()

    if reply:
        _reply(chat_id, reply)
    return dirty


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    if not TELEGRAM_BOT_TOKEN:
        print("[bot] TELEGRAM_BOT_TOKEN not configured — exiting")
        return 2

    state = load_state()
    subscribers = load_subscribers()
    deny = load_deny_list()
    last_id = get_last_update_id(state)

    try:
        updates = _get_updates(last_id)
    except Exception as e:
        print(f"[bot] getUpdates failed: {e}")
        return 3

    if not updates:
        print("[bot] no new updates")
        return 0

    print(f"[bot] processing {len(updates)} update(s)")

    dirty_agg = _dirty()
    max_update_id = last_id or 0

    for upd in updates:
        uid = upd.get("update_id")
        if uid is not None and uid > max_update_id:
            max_update_id = uid

        # We only care about `message` updates. Edited messages, channel
        # posts, callback queries etc. are safely ignored.
        msg = upd.get("message")
        if not msg:
            continue

        try:
            d = _process_message(msg, subscribers, deny, state)
            for k, v in d.items():
                if v:
                    dirty_agg[k] = True
        except Exception as e:
            chat_id = (msg.get("chat") or {}).get("id")
            print(f"[bot] handler error for chat_id={chat_id}: {e}")

    update_last_update_id(state, max_update_id)
    save_state(state)
    if dirty_agg["subscribers"]:
        save_subscribers(subscribers)
    if dirty_agg["deny"]:
        save_deny_list(deny)

    print(
        f"[bot] done · max_update_id={max_update_id} "
        f"subs={len(subscribers)} denied={len(deny)} "
        f"dirty={{subs:{dirty_agg['subscribers']}, deny:{dirty_agg['deny']}}}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
