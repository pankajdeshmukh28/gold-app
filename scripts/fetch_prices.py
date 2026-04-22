"""Main entry point. Run by GitHub Actions cron.

Flow:
  1. Fetch USD→INR, international gold spot (USD/oz).
  2. Fetch US retail gold bar price (Costco → APMEX fallback).
  3. Compute per-gram USD on both sides (India side adds 3% GST).
  4. Write docs/data.json for the dashboard.
  5. Append to docs/history.json.
  6. If US price dropped vs last seen (by threshold), send Telegram notification.
"""
import json
import os
import sys
from datetime import datetime, timezone
from typing import List, Optional

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(THIS_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts.config import (
    COSTCO_PRODUCT_URL,
    COSTCO_SKU_GRAMS,
    DATA_FILE,
    INDIA_GST_RATE,
    PRICE_DROP_THRESHOLD_PCT,
)
from scripts.notifier import NotifierNotConfigured, get_default_notifier
from scripts.sources.costco import (
    CostcoBotBlocked,
    CostcoFetchError,
    CostcoLoginWall,
    fetch_costco_price,
)
from scripts.sources.jmbullion import JmbullionFetchError, fetch_jmbullion_price
from scripts.sources.fx import FxError, fetch_usd_inr
from scripts.sources.gold_spot import (
    GoldSpotError,
    TROY_OUNCE_GRAMS,
    fetch_gold_spot_usd_per_oz,
)
from scripts.sources.us_retail_estimate import estimate_us_retail_price
from scripts.state import (
    append_history,
    get_last_us_price,
    load_state,
    save_state,
    update_last_us_price,
)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fetch_us_price(spot_usd_per_oz: float) -> dict:
    """Resolve the US retail gold bar price via a 3-tier fallback chain.

    Tier 1: Costco (primary) — usually blocked by Akamai; caught + logged.
    Tier 2: JM Bullion 1-oz gold bar category → lowest in-stock price.
    Tier 3: spot × (1 + premium) estimate — guarantees we always produce data.
    """
    try:
        price = fetch_costco_price(COSTCO_PRODUCT_URL)
        return {
            "price_usd": price,
            "source": "costco",
            "url": COSTCO_PRODUCT_URL,
            "grams": COSTCO_SKU_GRAMS,
            "notes": None,
        }
    except CostcoBotBlocked as e:
        print(f"[us_price] Costco bot-blocked (Akamai). Falling back to JM Bullion. ({e})")
    except CostcoLoginWall as e:
        print(f"[us_price] Costco login wall. Falling back to JM Bullion. ({e})")
    except CostcoFetchError as e:
        print(f"[us_price] Costco fetch failed. Falling back to JM Bullion. ({e})")

    try:
        price, product_url = fetch_jmbullion_price()
        return {
            "price_usd": price,
            "source": "jmbullion",
            "url": product_url,
            "grams": COSTCO_SKU_GRAMS,
            "notes": "Using JM Bullion 1-oz gold bar (lowest in-stock) — Costco is behind Akamai bot protection.",
        }
    except JmbullionFetchError as e:
        print(f"[us_price] JM Bullion fetch failed. Using spot-based estimate. ({e})")

    estimated_price = estimate_us_retail_price(spot_usd_per_oz, COSTCO_SKU_GRAMS)
    return {
        "price_usd": estimated_price,
        "source": "estimate",
        "url": None,
        "grams": COSTCO_SKU_GRAMS,
        "notes": (
            "⚠ Estimated (spot × 1+premium). Both Costco and JM Bullion scrapers failed. "
            "Directional only — adjust US_RETAIL_PREMIUM_RATE to tune."
        ),
    }


def compute_verdict(
    us_price_usd: float,
    us_grams: float,
    spot_usd_per_oz: float,
    usd_inr: float,
    gst_rate: float,
) -> dict:
    us_usd_per_gram = us_price_usd / us_grams

    india_inr_per_gram_pre_gst = (spot_usd_per_oz * usd_inr) / TROY_OUNCE_GRAMS
    india_inr_per_gram = india_inr_per_gram_pre_gst * (1 + gst_rate)
    india_usd_per_gram = india_inr_per_gram / usd_inr

    delta_pct = ((us_usd_per_gram - india_usd_per_gram) / india_usd_per_gram) * 100.0

    if delta_pct < -0.1:
        verdict = "BUY_IN_US"
        verdict_human = f"US is {abs(delta_pct):.2f}% cheaper than India"
    elif delta_pct > 0.1:
        verdict = "BUY_IN_INDIA"
        verdict_human = f"India is {delta_pct:.2f}% cheaper than US"
    else:
        verdict = "NEUTRAL"
        verdict_human = "US and India are roughly equivalent"

    return {
        "us_usd_per_gram": round(us_usd_per_gram, 2),
        "india_usd_per_gram": round(india_usd_per_gram, 2),
        "india_inr_per_gram": round(india_inr_per_gram, 2),
        "delta_pct": round(delta_pct, 2),
        "verdict": verdict,
        "verdict_human": verdict_human,
    }


def maybe_notify(
    us_price_usd: float,
    last_us_price: Optional[float],
    verdict_data: dict,
    us_source: str,
) -> Optional[str]:
    if last_us_price is None:
        return None

    diff_pct = ((us_price_usd - last_us_price) / last_us_price) * 100.0
    if diff_pct >= -PRICE_DROP_THRESHOLD_PCT:
        return None

    dollar_drop = last_us_price - us_price_usd
    msg = (
        f"🟢 <b>Gold price drop detected</b>\n"
        f"Source: {us_source.upper()}\n"
        f"Was: <b>${last_us_price:,.2f}</b> → Now: <b>${us_price_usd:,.2f}</b> "
        f"({diff_pct:+.2f}%, -${dollar_drop:,.2f})\n\n"
        f"vs India: {verdict_data['verdict_human']}\n"
        f"• US: ${verdict_data['us_usd_per_gram']}/g\n"
        f"• India: ${verdict_data['india_usd_per_gram']}/g (incl. 3% GST)"
    )

    try:
        notifier = get_default_notifier()
        notifier.send(msg)
        print(f"[notify] sent drop alert ({diff_pct:+.2f}%)")
        return msg
    except NotifierNotConfigured as e:
        print(f"[notify] skipped — {e}")
    except Exception as e:
        print(f"[notify] failed to send: {e}")
    return None


def write_data_file(payload: dict) -> None:
    os.makedirs(os.path.dirname(DATA_FILE) or ".", exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(payload, f, indent=2)


def send_test_notification() -> int:
    """Send a one-off Telegram ping to verify the bot setup is wired correctly."""
    print("[test-notify] sending test message...")
    try:
        notifier = get_default_notifier()
        notifier.send(
            "✅ <b>Gold tracker: test message</b>\n"
            f"Sent at {_utcnow_iso()}\n"
            "If you see this, your Telegram bot is wired up correctly. "
            "Real alerts will fire on price drops ≥ the configured threshold."
        )
        print("[test-notify] OK — check Telegram.")
        return 0
    except NotifierNotConfigured as e:
        print(f"[test-notify] FAILED: {e}")
        return 2
    except Exception as e:
        print(f"[test-notify] FAILED: {e}")
        return 3


def main() -> int:
    if os.environ.get("TEST_NOTIFY", "").lower() == "true":
        return send_test_notification()

    print(f"[main] run started @ {_utcnow_iso()}")

    errors: List[str] = []

    try:
        usd_inr = fetch_usd_inr()
        print(f"[main] USD→INR = {usd_inr:.4f}")
    except FxError as e:
        errors.append(f"fx: {e}")
        usd_inr = None

    try:
        spot = fetch_gold_spot_usd_per_oz()
        print(f"[main] spot gold = ${spot:.2f}/oz")
    except GoldSpotError as e:
        errors.append(f"gold_spot: {e}")
        spot = None

    if spot:
        try:
            us = fetch_us_price(spot)
            print(f"[main] US price = ${us['price_usd']:.2f} via {us['source']}")
        except Exception as e:
            errors.append(f"us_price: {e}")
            us = None
    else:
        us = None
        errors.append("us_price: skipped (spot unavailable)")

    if not (usd_inr and spot and us):
        payload = {
            "timestamp": _utcnow_iso(),
            "status": "error",
            "errors": errors,
        }
        write_data_file(payload)
        print(f"[main] FAILED: {errors}")
        return 1

    verdict = compute_verdict(
        us_price_usd=us["price_usd"],
        us_grams=us["grams"],
        spot_usd_per_oz=spot,
        usd_inr=usd_inr,
        gst_rate=INDIA_GST_RATE,
    )

    state = load_state()
    last_us_price = get_last_us_price(state)
    alert_sent = maybe_notify(us["price_usd"], last_us_price, verdict, us["source"])

    update_last_us_price(state, us["price_usd"])
    save_state(state)

    timestamp = _utcnow_iso()
    payload = {
        "timestamp": timestamp,
        "status": "ok",
        "inputs": {
            "spot_usd_per_oz": round(spot, 2),
            "usd_inr": round(usd_inr, 4),
            "us_price_usd": round(us["price_usd"], 2),
            "us_source": us["source"],
            "us_url": us["url"],
            "us_grams": us["grams"],
            "india_gst_rate": INDIA_GST_RATE,
            "us_notes": us.get("notes"),
        },
        "verdict": verdict,
        "alert_sent": bool(alert_sent),
        "last_us_price_seen": last_us_price,
    }
    write_data_file(payload)

    append_history(
        {
            "t": timestamp,
            "us": round(us["price_usd"], 2),
            "us_per_g": verdict["us_usd_per_gram"],
            "in_per_g": verdict["india_usd_per_gram"],
            "delta": verdict["delta_pct"],
            "src": us["source"],
        }
    )

    print(f"[main] DONE. {verdict['verdict_human']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
