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
        r = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()


def get_default_notifier() -> Notifier:
    return TelegramNotifier(TELEGRAM_BOT_TOKEN or "", TELEGRAM_CHAT_ID or "")
