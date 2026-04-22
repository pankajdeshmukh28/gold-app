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

PRICE_DROP_THRESHOLD_PCT = _env_float("PRICE_DROP_THRESHOLD_PCT", 0.5)

DATA_FILE = _env_str("DATA_FILE", "docs/data.json")
STATE_FILE = _env_str("STATE_FILE", "docs/state.json")
HISTORY_FILE = _env_str("HISTORY_FILE", "docs/history.json")
HISTORY_MAX_POINTS = _env_int("HISTORY_MAX_POINTS", 168)

TELEGRAM_BOT_TOKEN = _env_str("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = _env_str("TELEGRAM_CHAT_ID", "")

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
