"""Central config. Edit these to change what's tracked."""
import os


def _env_str(key: str, default: str) -> str:
    """Return env var value, falling back to default when unset OR empty.

    GitHub Actions sets unconfigured `vars` as empty strings, not as missing
    keys, so plain os.environ.get(key, default) would return "" in CI.
    """
    val = os.environ.get(key)
    if val is None or val.strip() == "":
        return default
    return val


def _env_float(key: str, default: float) -> float:
    return float(_env_str(key, str(default)))


def _env_int(key: str, default: int) -> int:
    return int(_env_str(key, str(default)))


COSTCO_PRODUCT_URL = _env_str(
    "COSTCO_PRODUCT_URL",
    "https://www.costco.com/pamp-suisse-lady-fortuna-veriscan-1-oz-gold-bar.product.4000156851.html",
)

COSTCO_SKU_GRAMS = _env_float("COSTCO_SKU_GRAMS", 31.1035)

JMBULLION_CATEGORY_URL = _env_str(
    "JMBULLION_CATEGORY_URL",
    "https://www.jmbullion.com/gold/gold-bars/1-oz-gold-bars/",
)

US_RETAIL_PREMIUM_RATE = _env_float("US_RETAIL_PREMIUM_RATE", 0.03)

# Most US states exempt investment-grade bullion (1oz+ gold bars). Leave at 0
# unless your state taxes bullion. Set via repo variable US_SALES_TAX_RATE.
US_SALES_TAX_RATE = _env_float("US_SALES_TAX_RATE", 0.0)

INDIA_GST_RATE = _env_float("INDIA_GST_RATE", 0.03)

# Minimum INR/10g increase in "buying-in-US savings" between runs to trigger
# a Telegram alert. Default: ₹500/10g. Raise it (e.g. 1000) if you want fewer
# pings; lower it (e.g. 250) for more.
SAVINGS_INCREASE_THRESHOLD_INR = _env_float("SAVINGS_INCREASE_THRESHOLD_INR", 500.0)

DATA_FILE = _env_str("DATA_FILE", "docs/data.json")
STATE_FILE = _env_str("STATE_FILE", "docs/state.json")
HISTORY_FILE = _env_str("HISTORY_FILE", "docs/history.json")
HISTORY_MAX_POINTS = _env_int("HISTORY_MAX_POINTS", 168)

SUBSCRIBERS_FILE = _env_str("SUBSCRIBERS_FILE", "docs/subscribers.json")
DENY_LIST_FILE = _env_str("DENY_LIST_FILE", "docs/deny_list.json")

# Dashboard URL surfaced inside Telegram messages (welcome, help, /status,
# price alerts, weekly digest). Falls back to a hardcoded default; override
# via `DASHBOARD_URL` GH Actions variable so different repos/forks work.
# Uses _env_str so an empty string from CI is treated as "unset".
DASHBOARD_URL = _env_str("DASHBOARD_URL", "https://pankajdeshmukh28.github.io/gold-app/")

TELEGRAM_BOT_TOKEN = _env_str("TELEGRAM_BOT_TOKEN", "")
# TELEGRAM_CHAT_ID is the "admin" chat — yours. It's always included in
# broadcasts (safety net: even if subscribers.json is empty or corrupted
# you still get pinged) and it's the default admin for /kick, /list, etc.
# Additional admins can be added via ADMIN_CHAT_IDS (comma-separated).
TELEGRAM_CHAT_ID = _env_str("TELEGRAM_CHAT_ID", "")
_ADMIN_CHAT_IDS_RAW = _env_str("ADMIN_CHAT_IDS", "")


def _parse_admin_ids() -> list:
    out = []
    if TELEGRAM_CHAT_ID:
        try:
            out.append(int(TELEGRAM_CHAT_ID))
        except ValueError:
            pass
    for part in _ADMIN_CHAT_IDS_RAW.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            cid = int(part)
            if cid not in out:
                out.append(cid)
        except ValueError:
            pass
    return out


ADMIN_CHAT_IDS = _parse_admin_ids()

# Broadcast fan-out: Telegram's documented limit is ~30 msgs/sec to different
# chats. We sleep this many seconds between sends as a conservative buffer,
# and retry on HTTP 429 with the server-provided retry_after.
BROADCAST_SLEEP_SEC = _env_float("BROADCAST_SLEEP_SEC", 0.05)

# How many Telegram updates to fetch per poll. 100 is plenty for a family
# bot; 100 is also Telegram's default.
TELEGRAM_UPDATES_LIMIT = _env_int("TELEGRAM_UPDATES_LIMIT", 100)

# Hard cap on subscribers — safety rail against a social-media viral moment
# that balloons your subscriber list unexpectedly. Set to 0 to disable.
MAX_SUBSCRIBERS = _env_int("MAX_SUBSCRIBERS", 1000)

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

REQUEST_TIMEOUT = 20
