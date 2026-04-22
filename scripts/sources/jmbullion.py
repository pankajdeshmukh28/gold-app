"""JMBullion fallback: scrape 1-oz gold bar category, return lowest price.

JMBullion's category page is server-rendered and includes a grid of product
cards. Each card has a `.price` element showing the "as-low-as" price and an
anchor tag linking to the product detail page.

Strategy:
  1. Fetch the category page with curl_cffi (Chrome TLS impersonation).
  2. Iterate product anchors whose href points to a gold-bar product page.
  3. For each anchor, find the nearest `.price` element and parse it.
  4. Filter to plausible 1-oz gold bar range (current spot × 0.95 < p < × 1.2).
  5. Return the lowest price + the product URL it came from.
"""
import re
from typing import List, Optional, Tuple

from bs4 import BeautifulSoup
from bs4.element import Tag
from curl_cffi import requests as cffi_requests

from scripts.config import JMBULLION_CATEGORY_URL, REQUEST_TIMEOUT

JMBULLION_BASE = "https://www.jmbullion.com"

_PRICE_REGEX = re.compile(r"\$\s?([\d,]+\.\d{2})")

_SLUG_EXCLUDES = (
    "silver",
    "platinum",
    "palladium",
    "kilo",
    "gram-gold-bar",
    "-1-10-",
    "1-5-oz",
    "1-4-oz",
    "1-2-oz",
    "1-20-oz",
    "charts",
    "gold-price",
)


class JmbullionFetchError(Exception):
    pass


def _slug_from_href(href: str) -> Optional[str]:
    """Return the last non-empty path segment if href is a root-level product URL.

    Product URLs on JMBullion look like `/1-oz-pamp-suisse-gold-bar/` or
    `https://www.jmbullion.com/1-oz-pamp-suisse-gold-bar/`. Category URLs
    like `/gold/gold-bars/...` have multiple path segments and are filtered out.
    """
    path = href
    if href.startswith("http"):
        idx = href.find("/", 8)
        if idx < 0:
            return None
        path = href[idx:]
    parts = [p for p in path.split("/") if p]
    if len(parts) != 1:
        return None
    return parts[0].lower()


def _is_one_oz_gold_bar_href(href: str) -> bool:
    slug = _slug_from_href(href)
    if not slug:
        return False
    if "gold-bar" not in slug:
        return False
    if not ("1-oz" in slug or "1oz" in slug or "one-oz" in slug):
        return False
    if any(x in slug for x in _SLUG_EXCLUDES):
        return False
    return True


def _nearest_price(anchor: Tag) -> Optional[float]:
    """Walk up parents until we find a container whose text has a plausible bar price."""
    parent = anchor.parent
    for _ in range(8):
        if parent is None:
            break
        text = parent.get_text(" ", strip=True)
        if "$" in text:
            for m in _PRICE_REGEX.findall(text):
                try:
                    val = float(m.replace(",", ""))
                except ValueError:
                    continue
                if 1500 < val < 20000:
                    return val
        parent = parent.parent
    return None


def _extract_candidates(html: str) -> List[Tuple[float, str]]:
    soup = BeautifulSoup(html, "html.parser")
    seen_urls = set()
    results: List[Tuple[float, str]] = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not _is_one_oz_gold_bar_href(href):
            continue
        full = href if href.startswith("http") else JMBULLION_BASE + href
        if full in seen_urls:
            continue
        seen_urls.add(full)
        price = _nearest_price(a)
        if price is None:
            continue
        results.append((price, full))

    return results


def fetch_jmbullion_price(category_url: str = JMBULLION_CATEGORY_URL) -> Tuple[float, str]:
    """Return (lowest_price_usd, source_url) for an in-stock 1-oz gold bar."""
    try:
        r = cffi_requests.get(
            category_url, impersonate="chrome124", timeout=REQUEST_TIMEOUT
        )
    except Exception as e:
        raise JmbullionFetchError(f"Network error: {e}")

    if r.status_code >= 400:
        raise JmbullionFetchError(f"HTTP {r.status_code} on {category_url}")

    candidates = _extract_candidates(r.text)
    if not candidates:
        raise JmbullionFetchError("No 1-oz gold bar product cards found.")

    plausible = [(p, u) for p, u in candidates if 1500 < p < 20000]
    if not plausible:
        raise JmbullionFetchError(
            f"Found {len(candidates)} product cards but none in plausible price range."
        )

    plausible.sort(key=lambda x: x[0])
    return plausible[0][0], plausible[0][1]
