"""Last-resort fallback: estimate US retail 1-oz gold bar price from spot.

Formula:  retail_usd_for_1oz = spot_usd_per_oz * (1 + premium_rate)

The premium_rate is a config default (US 1-oz bar retail typically runs 2–4%
over spot in normal market conditions). This is purely directional — it just
prevents the app from going dark when all scrapers fail.
"""
from scripts.config import US_RETAIL_PREMIUM_RATE


def estimate_us_retail_price(spot_usd_per_oz: float, sku_grams: float) -> float:
    """Return estimated US retail price for a bar of `sku_grams` grams of gold."""
    TROY_OUNCE_GRAMS = 31.1034768
    oz_in_sku = sku_grams / TROY_OUNCE_GRAMS
    spot_cost = spot_usd_per_oz * oz_in_sku
    return spot_cost * (1 + US_RETAIL_PREMIUM_RATE)
