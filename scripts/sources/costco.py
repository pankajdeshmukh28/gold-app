"""Costco gold bar price scraper.

Reality: Costco.com serves an Akamai Bot Manager JS challenge on precious-metal
product pages. Pure HTTP scrapers (including curl_cffi) get the challenge page,
not the product content. This module detects that and fails cleanly so the
orchestrator can fall back to APMEX or a spot-based estimate.

If curl_cffi + real browser fingerprinting ever starts returning content, the
JSON-LD / meta / regex extractors below will pick it up automatically.
"""
import json
import re
from typing import Optional

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

from scripts.config import COSTCO_PRODUCT_URL, REQUEST_TIMEOUT


class CostcoFetchError(Exception):
    pass


class CostcoLoginWall(CostcoFetchError):
    """Raised when Costco gates the page behind sign-in."""


class CostcoBotBlocked(CostcoFetchError):
    """Raised when Akamai/Cloudflare bot-protection challenge is served."""


_LOGIN_WALL_MARKERS = (
    "sign in to see price",
    "please sign in",
    "members only",
    "sign in for price",
    "log in to see",
)

_BOT_CHALLENGE_MARKERS = (
    "sec-if-cpt-container",
    "sec-bc-text-container",
    "protected by</p>",
    "akamai-privacy",
    'aka_re"',
    "/_Incapsula_Resource",
    "captcha-delivery",
)

_PRICE_REGEX = re.compile(r"\$\s?([\d,]+\.\d{2})")


def _extract_from_json_ld(soup: BeautifulSoup) -> Optional[float]:
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            blob = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        nodes = blob if isinstance(blob, list) else [blob]
        for node in nodes:
            if not isinstance(node, dict) or node.get("@type") != "Product":
                continue
            offers = node.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            if not isinstance(offers, dict):
                continue
            for key in ("price", "lowPrice", "highPrice"):
                raw = offers.get(key)
                if raw:
                    try:
                        return float(str(raw).replace(",", ""))
                    except ValueError:
                        continue
    return None


def _extract_from_meta(soup: BeautifulSoup) -> Optional[float]:
    for name in ("product:price:amount", "og:price:amount"):
        tag = soup.find("meta", attrs={"property": name}) or soup.find(
            "meta", attrs={"name": name}
        )
        if tag and tag.get("content"):
            try:
                return float(str(tag["content"]).replace(",", ""))
            except ValueError:
                continue
    return None


def _extract_from_regex(html: str) -> Optional[float]:
    nums = []
    for m in _PRICE_REGEX.findall(html):
        try:
            nums.append(float(m.replace(",", "")))
        except ValueError:
            continue
    plausible = [n for n in nums if 500 < n < 50000]
    return max(plausible) if plausible else None


def fetch_costco_price(url: str = COSTCO_PRODUCT_URL) -> float:
    try:
        r = cffi_requests.get(
            url, impersonate="chrome124", timeout=REQUEST_TIMEOUT, allow_redirects=True
        )
    except Exception as e:
        raise CostcoFetchError(f"Network error: {e}")

    if r.status_code >= 400:
        raise CostcoFetchError(f"HTTP {r.status_code} on {url}")

    html = r.text
    html_lower = html.lower()

    if any(marker in html_lower for marker in _BOT_CHALLENGE_MARKERS):
        raise CostcoBotBlocked("Akamai/bot-manager challenge served (Costco is blocking automated requests).")

    if len(html) < 5000 and "<body" in html_lower and "sign in" not in html_lower:
        raise CostcoBotBlocked(f"Suspiciously short Costco response ({len(html)} bytes) — likely a challenge page.")

    for marker in _LOGIN_WALL_MARKERS:
        if marker in html_lower:
            raise CostcoLoginWall(f"Costco login wall detected (marker: '{marker}').")

    soup = BeautifulSoup(html, "html.parser")

    for extractor in (_extract_from_json_ld, _extract_from_meta):
        price = extractor(soup)
        if price and price > 0:
            return price

    price = _extract_from_regex(html)
    if price and price > 0:
        return price

    raise CostcoFetchError("Could not extract price from Costco page.")
