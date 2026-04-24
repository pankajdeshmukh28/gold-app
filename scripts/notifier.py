"""Notification abstraction.

Two concrete notifiers:
  * `TelegramNotifier` — single-chat sendMessage (original behavior)
  * `BroadcastNotifier` — fan-out to all subscribers + admins with
    rate-limit handling, 403/400 auto-prune, and a single shared client.

Also exposes a module-level `send_telegram_message()` helper used by
`scripts/telegram_bot.py` to reply to commands without bothering with
class instances.
"""
import time
from typing import List, Optional, Tuple

import requests

from scripts.config import (
    ADMIN_CHAT_IDS,
    BROADCAST_SLEEP_SEC,
    REQUEST_TIMEOUT,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
)
from scripts.state import (
    load_subscribers,
    remove_subscriber,
    save_subscribers,
)


class NotifierNotConfigured(Exception):
    pass


class Notifier:
    """Swap in another backend by subclassing this."""

    def send(self, message: str) -> None:
        raise NotImplementedError


def _telegram_api_url(bot_token: str, method: str) -> str:
    return f"https://api.telegram.org/bot{bot_token}/{method}"


def send_telegram_message(
    chat_id,
    message: str,
    bot_token: Optional[str] = None,
    parse_mode: str = "HTML",
    disable_preview: bool = True,
    disable_notification: bool = False,
    reply_markup: Optional[dict] = None,
) -> Tuple[bool, dict]:
    """Low-level Telegram sendMessage wrapper.

    Returns (ok, response_json). Does NOT raise on Telegram API errors —
    the caller decides what to do based on `ok` + `error_code`. This is
    the same contract as Telegram's own API, intentionally.

    Raises RuntimeError only on network-level failures (timeouts, DNS, etc).
    """
    bot_token = bot_token or TELEGRAM_BOT_TOKEN
    if not bot_token:
        raise NotifierNotConfigured("TELEGRAM_BOT_TOKEN is not set")

    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": parse_mode,
        "disable_web_page_preview": disable_preview,
        "disable_notification": disable_notification,
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup

    try:
        r = requests.post(
            _telegram_api_url(bot_token, "sendMessage"),
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
    except Exception as e:
        raise RuntimeError(f"Telegram request failed (network): {e}") from e

    try:
        data = r.json() if r.text else {}
    except Exception:
        data = {"ok": False, "description": f"non-json response: {r.text[:200]!r}"}

    ok = bool(data.get("ok"))
    return ok, data


class TelegramNotifier(Notifier):
    """Single-chat notifier. Preserved for backward compat + admin-only pings."""

    def __init__(self, bot_token: str, chat_id: str):
        if not bot_token or not chat_id:
            raise NotifierNotConfigured(
                "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must both be set."
            )
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send(self, message: str) -> None:
        ok, data = send_telegram_message(
            chat_id=self.chat_id, message=message, bot_token=self.bot_token
        )
        if not ok:
            tg_desc = data.get("description", "(no description)")
            tg_code = data.get("error_code", "?")
            token_hint = (
                f"{self.bot_token[:6]}…{self.bot_token[-4:]}"
                if self.bot_token and len(self.bot_token) > 10
                else "(short)"
            )
            raise RuntimeError(
                f"Telegram code={tg_code} desc={tg_desc!r} "
                f"chat_id={self.chat_id!r} bot={token_hint}"
            )


class BroadcastNotifier(Notifier):
    """Fan-out notifier — sends the same message to every subscriber + admin.

    Auto-prunes subscribers whose chats Telegram says are gone (403 Forbidden:
    bot blocked/deactivated, 400 chat not found). Retries on 429 using the
    retry_after hint. Writes back a cleaned subscribers.json after the run.
    """

    def __init__(self, bot_token: str):
        if not bot_token:
            raise NotifierNotConfigured("TELEGRAM_BOT_TOKEN is not set")
        self.bot_token = bot_token

    def _collect_targets(self) -> Tuple[List[int], List[dict]]:
        """Return (ordered target chat_ids, full subscribers list).

        Admins come first so a bad broadcast fails loudly to you, not to a
        random subscriber. Dedupes admin vs subscriber overlap.
        """
        subscribers = load_subscribers()
        ordered: List[int] = []
        seen = set()
        for cid in ADMIN_CHAT_IDS:
            if cid not in seen:
                ordered.append(cid)
                seen.add(cid)
        for s in subscribers:
            try:
                cid = int(s["chat_id"])
            except (KeyError, ValueError, TypeError):
                continue
            if cid not in seen:
                ordered.append(cid)
                seen.add(cid)
        return ordered, subscribers

    def send(self, message: str) -> dict:
        """Broadcast `message`. Returns a summary dict:
        {sent, failed, pruned, targets}.
        """
        targets, subscribers = self._collect_targets()
        if not targets:
            raise NotifierNotConfigured(
                "No broadcast targets — set TELEGRAM_CHAT_ID or populate "
                "subscribers.json (or both)."
            )

        admin_ids = set(ADMIN_CHAT_IDS)
        sent = 0
        failed: List[Tuple[int, str]] = []
        to_prune: List[int] = []

        for cid in targets:
            attempt = 0
            while True:
                attempt += 1
                try:
                    ok, data = send_telegram_message(
                        chat_id=cid, message=message, bot_token=self.bot_token
                    )
                except RuntimeError as e:
                    failed.append((cid, f"network: {e}"))
                    break

                if ok:
                    sent += 1
                    break

                err_code = int(data.get("error_code") or 0)
                desc = data.get("description", "")

                # 429 — rate limit. Sleep the suggested amount and retry.
                if err_code == 429:
                    retry_after = int(
                        (data.get("parameters") or {}).get("retry_after", 1)
                    )
                    if attempt > 3:
                        failed.append((cid, f"429 after {attempt} attempts"))
                        break
                    time.sleep(retry_after + 1)
                    continue

                # 403 (bot was blocked / deactivated / kicked) or 400
                # (chat not found) → subscriber is permanently gone. Prune.
                # Never prune admin chat IDs — that's a config problem, not
                # a subscriber problem.
                if err_code in (400, 403) and cid not in admin_ids:
                    to_prune.append(cid)
                    failed.append((cid, f"{err_code} {desc} (pruned)"))
                else:
                    failed.append((cid, f"{err_code} {desc}"))
                break

            if BROADCAST_SLEEP_SEC > 0:
                time.sleep(BROADCAST_SLEEP_SEC)

        if to_prune:
            for cid in to_prune:
                remove_subscriber(subscribers, cid)
            save_subscribers(subscribers)

        return {
            "sent": sent,
            "failed": len(failed),
            "pruned": len(to_prune),
            "targets": len(targets),
            "errors": failed,
        }


def get_default_notifier() -> Notifier:
    """Back-compat: single-chat notifier for the existing call sites that
    don't want fan-out (e.g. manual test_notify). New broadcast call sites
    should instantiate BroadcastNotifier directly."""
    return TelegramNotifier(TELEGRAM_BOT_TOKEN or "", TELEGRAM_CHAT_ID or "")


def get_broadcast_notifier() -> BroadcastNotifier:
    return BroadcastNotifier(TELEGRAM_BOT_TOKEN or "")
