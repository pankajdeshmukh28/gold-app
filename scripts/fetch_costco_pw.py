"""Local-only Costco gold bar price fetcher via Playwright.

This is intentionally decoupled from fetch_prices.py because:
  1. Costco sits behind Akamai Bot Manager which blocks datacenter IPs.
  2. Playwright + a real chromium instance running from a residential IP
     (your Mac) solves the JS challenge and passes IP-reputation checks
     reliably.
  3. Running it remotely (GitHub Actions) is ~30-50% reliable; locally
     it's ~95%+.

Output: writes the latest Costco snapshot to docs/costco.json. The dashboard
reads this file independently and shows a Costco card when the data is
fresh (< 24h). The main verdict / Telegram alerts still rely on the
JM Bullion-driven data.json.

Usage:
    python -m scripts.fetch_costco_pw
"""
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.config import COSTCO_PRODUCT_URL, COSTCO_SKU_GRAMS  # noqa: E402

try:
    from playwright.sync_api import TimeoutError as PwTimeout
    from playwright.sync_api import sync_playwright
except ImportError:
    print(
        "[costco-pw] playwright not installed. Run:\n"
        "  pip install -r requirements-local.txt\n"
        "  playwright install chromium",
        file=sys.stderr,
    )
    sys.exit(2)


COSTCO_OUTPUT = REPO_ROOT / "docs" / "costco.json"
# Persistent profile so cookies + Akamai reputation score survive across
# runs. Stored outside the repo to avoid committing browser state.
PW_PROFILE_DIR = Path.home() / ".cache" / "gold-app" / "pw-chromium-profile"


def _extract_from_json_ld(page) -> Optional[float]:
    """Costco usually embeds a Product JSON-LD block with the offer price."""
    blocks = page.query_selector_all('script[type="application/ld+json"]')
    for block in blocks:
        raw = block.inner_text() or ""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            if item.get("@type") not in ("Product", ["Product"]):
                continue
            offers = item.get("offers")
            if isinstance(offers, list) and offers:
                offers = offers[0]
            if isinstance(offers, dict):
                price = offers.get("price") or offers.get("lowPrice")
                if price is not None:
                    try:
                        return float(str(price).replace(",", ""))
                    except ValueError:
                        pass
    return None


def _extract_from_meta(page) -> Optional[float]:
    """Some templates expose og:price meta tags."""
    for selector in (
        'meta[property="product:price:amount"]',
        'meta[property="og:price:amount"]',
        'meta[itemprop="price"]',
    ):
        el = page.query_selector(selector)
        if el:
            val = el.get_attribute("content") or ""
            try:
                return float(val.replace(",", ""))
            except ValueError:
                continue
    return None


def _extract_from_rendered_html(page) -> Optional[float]:
    """Last-resort regex scan of rendered HTML for the product price."""
    html = page.content()
    for pattern in (
        r'"price"\s*:\s*"?([\d,]+\.\d{2})"?',
        r'currentPrice["\']?\s*:\s*["\']?([\d,]+\.\d{2})',
        r'\$\s*([\d,]{2,}\.\d{2})',
    ):
        for match in re.finditer(pattern, html):
            try:
                val = float(match.group(1).replace(",", ""))
                if 500 < val < 20000:
                    return val
            except ValueError:
                continue
    return None


def _looks_like_bot_challenge(page) -> bool:
    """Sanity check — if we somehow still got the Akamai JS page, bail fast."""
    title = (page.title() or "").lower()
    if "error" in title and "access denied" in title:
        return True
    html = page.content().lower()
    return any(
        marker in html
        for marker in (
            "_abck=",
            "akamai bot manager",
            "access denied",
            "reference&#32;#",
        )
    ) and "gold" not in html


def fetch_costco_via_playwright(product_url: str, headless: bool = True) -> float:
    PW_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PW_PROFILE_DIR),
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/128.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
            locale="en-US",
            timezone_id="America/Los_Angeles",
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = context.new_page()
        try:
            page.goto(product_url, wait_until="domcontentloaded", timeout=45_000)
        except PwTimeout:
            context.close()
            raise RuntimeError("Costco page timed out (>45s)")

        page.wait_for_timeout(4000)

        if _looks_like_bot_challenge(page):
            context.close()
            raise RuntimeError(
                "Costco served a bot-challenge page even via Playwright. "
                "Try headful mode or re-run later."
            )

        price = (
            _extract_from_json_ld(page)
            or _extract_from_meta(page)
            or _extract_from_rendered_html(page)
        )
        context.close()

        if price is None:
            raise RuntimeError("Could not find a plausible price on the Costco page.")
        return price


def main() -> int:
    print(f"[costco-pw] fetching {COSTCO_PRODUCT_URL}")
    headless = os.environ.get("COSTCO_PW_HEADFUL", "").lower() != "true"
    try:
        price = fetch_costco_via_playwright(COSTCO_PRODUCT_URL, headless=headless)
    except Exception as e:
        print(f"[costco-pw] FAILED: {e}", file=sys.stderr)
        return 1

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "costco",
        "price_usd": round(price, 2),
        "grams": COSTCO_SKU_GRAMS,
        "usd_per_gram": round(price / COSTCO_SKU_GRAMS, 2),
        "usd_per_10g": round((price / COSTCO_SKU_GRAMS) * 10, 2),
        "url": COSTCO_PRODUCT_URL,
    }
    COSTCO_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(COSTCO_OUTPUT, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"[costco-pw] OK ${price:,.2f} (${payload['usd_per_10g']:,.2f}/10g) -> {COSTCO_OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
