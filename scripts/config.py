"""Central config. Edit these to change what's tracked."""
import os

COSTCO_PRODUCT_URL = os.environ.get(
    "COSTCO_PRODUCT_URL",
    "https://www.costco.com/pamp-suisse-lady-fortuna-veriscan-1-oz-gold-bar.product.4000156851.html",
)

COSTCO_SKU_GRAMS = float(os.environ.get("COSTCO_SKU_GRAMS", 31.1035))

JMBULLION_CATEGORY_URL = os.environ.get(
    "JMBULLION_CATEGORY_URL",
    "https://www.jmbullion.com/gold/gold-bars/1-oz-gold-bars/",
)

US_RETAIL_PREMIUM_RATE = float(os.environ.get("US_RETAIL_PREMIUM_RATE", 0.03))

INDIA_GST_RATE = float(os.environ.get("INDIA_GST_RATE", 0.03))

PRICE_DROP_THRESHOLD_PCT = float(os.environ.get("PRICE_DROP_THRESHOLD_PCT", 0.5))

DATA_FILE = os.environ.get("DATA_FILE", "docs/data.json")
STATE_FILE = os.environ.get("STATE_FILE", "docs/state.json")
HISTORY_FILE = os.environ.get("HISTORY_FILE", "docs/history.json")
HISTORY_MAX_POINTS = int(os.environ.get("HISTORY_MAX_POINTS", 168))

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

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
