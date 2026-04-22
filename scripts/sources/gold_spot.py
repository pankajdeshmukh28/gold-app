"""International gold spot price fetcher (USD per troy ounce).

This is the anchor for the India-side price calculation:
  India per-gram INR = (spot_usd_per_oz × USD_INR ÷ 31.1035) × (1 + GST)
"""
from curl_cffi import requests as cffi_requests

from scripts.config import REQUEST_TIMEOUT

TROY_OUNCE_GRAMS = 31.1034768


class GoldSpotError(Exception):
    pass


def fetch_gold_spot_usd_per_oz() -> float:
    """Return current spot gold price in USD per troy ounce."""
    primary = "https://data-asg.goldprice.org/dbXRates/USD"
    try:
        r = cffi_requests.get(primary, impersonate="chrome124", timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        items = data.get("items", [])
        if items:
            xau = items[0].get("xauPrice")
            if xau and float(xau) > 0:
                return float(xau)
    except Exception as e:
        print(f"[gold_spot] primary source failed: {e}")

    fallback = "https://api.gold-api.com/price/XAU"
    try:
        r = cffi_requests.get(fallback, impersonate="chrome124", timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        price = data.get("price")
        if price and float(price) > 0:
            return float(price)
    except Exception as e:
        print(f"[gold_spot] fallback source failed: {e}")

    raise GoldSpotError("All gold spot sources failed.")
