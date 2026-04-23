"""Notification abstraction. Current impl: Telegram bot."""
import requests

from scripts.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, REQUEST_TIMEOUT


class NotifierNotConfigured(Exception):
    pass


class Notifier:
    """Swap in another backend by subclassing this."""

    def send(self, message: str) -> None:
        raise NotImplementedError


class TelegramNotifier(Notifier):
    def __init__(self, bot_token: str, chat_id: str):
        if not bot_token or not chat_id:
            raise NotifierNotConfigured(
                "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must both be set."
            )
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send(self, message: str) -> None:
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            r = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
        except Exception as e:
            raise RuntimeError(f"Telegram request failed (network): {e}") from e

        # Telegram always returns JSON with an `ok` field. If the call
        # failed, surface Telegram's own description so we don't have to
        # guess (e.g. "chat not found", "bot was blocked by the user",
        # "Unauthorized" from a revoked token).
        body_preview = (r.text or "")[:400]
        try:
            data = r.json()
        except Exception:
            data = None

        if r.status_code != 200 or (data and not data.get("ok", False)):
            tg_desc = (data or {}).get("description", "(no description)")
            tg_code = (data or {}).get("error_code", "?")
            token_hint = (
                f"{self.bot_token[:6]}…{self.bot_token[-4:]}"
                if self.bot_token and len(self.bot_token) > 10
                else "(short)"
            )
            raise RuntimeError(
                f"Telegram HTTP {r.status_code} code={tg_code} "
                f"desc={tg_desc!r} chat_id={self.chat_id!r} "
                f"bot={token_hint} body={body_preview!r}"
            )


def get_default_notifier() -> Notifier:
    return TelegramNotifier(TELEGRAM_BOT_TOKEN or "", TELEGRAM_CHAT_ID or "")
