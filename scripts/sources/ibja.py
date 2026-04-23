"""Scrape India's Benchmark (IBJA) daily gold rate.

Why: IBJA publishes the reference rates that Indian jewelers and banks
actually use for pricing. These already reflect Indian market dynamics
(import duty, local demand, etc.), so they are the correct number to
compare against US retail — NOT spot + 3% GST (which underestimates
real Indian retail by ~20%).

Source: https://ibjarates.com/
Rate returned: pure 999 (24K) gold, per 10g, in INR, WITHOUT GST.
(Caller should add 3% GST for final buying price.)

IBJA publishes two rates per day:
  AM = opening (morning)
  PM = closing (afternoon)
We prefer PM since it's the "last print" of the day.
"""
import re
from dataclasses import dataclass
from typing import List, Optional

from bs4 import BeautifulSoup
from curl_cffi import requests

from scripts.config import REQUEST_TIMEOUT

IBJA_URL = "https://ibjarates.com/"

RATE_HEADER_PREFIX = ["", "999", "995", "916", "750", "585"]


class IbjaFetchError(Exception):
    pass


@dataclass
class IbjaRate:
    rate_inr_per_10g: float
    purity: str
    date_str: str
    session: str
    source_url: str = IBJA_URL


def _parse_int(raw: str) -> Optional[int]:
    cleaned = re.sub(r"[^\d]", "", raw or "")
    if not cleaned:
        return None
    try:
        val = int(cleaned)
    except ValueError:
        return None
    # sanity window: Indian gold rates per 10g have been 40k-300k INR for years
    if 30_000 <= val <= 500_000:
        return val
    return None


def _find_rate_tables(soup: BeautifulSoup) -> List:
    """Return all tables whose header row matches the IBJA rate table shape."""
    matches = []
    for table in soup.find_all("table"):
        first_row = table.find("tr")
        if not first_row:
            continue
        cells = [c.get_text(strip=True) for c in first_row.find_all(["td", "th"])]
        if cells[: len(RATE_HEADER_PREFIX)] == RATE_HEADER_PREFIX:
            matches.append(table)
    return matches


def _latest_rate_from_table(table, session_hint: str) -> Optional[IbjaRate]:
    """Return the newest-date row as an IbjaRate, or None if unparseable."""
    rows = table.find_all("tr")
    for row in rows[1:]:
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 2:
            continue
        date_str = cells[0]
        rate = _parse_int(cells[1])
        if rate is None or not date_str:
            continue
        return IbjaRate(
            rate_inr_per_10g=float(rate),
            purity="999",
            date_str=date_str,
            session=session_hint,
        )
    return None


def fetch_ibja_999() -> IbjaRate:
    """Fetch today's (or latest available) IBJA 999 gold rate per 10g.

    Raises IbjaFetchError on network / parsing / schema-change failures so the
    caller can fall back to the computed spot-based estimate.
    """
    try:
        resp = requests.get(
            IBJA_URL,
            impersonate="chrome124",
            timeout=REQUEST_TIMEOUT,
        )
    except Exception as e:
        raise IbjaFetchError(f"network: {e}")

    if resp.status_code != 200:
        raise IbjaFetchError(f"HTTP {resp.status_code}")

    soup = BeautifulSoup(resp.text, "html.parser")
    rate_tables = _find_rate_tables(soup)

    if not rate_tables:
        raise IbjaFetchError(
            "IBJA page structure changed — no rate tables matching "
            f"header {RATE_HEADER_PREFIX} were found"
        )

    # Page order on ibjarates.com is AM first, PM second. Prefer PM when
    # available; fall back to AM. If the schema changes and only one table
    # remains, we still get a reading.
    pm_rate = None
    am_rate = None
    if len(rate_tables) >= 2:
        am_rate = _latest_rate_from_table(rate_tables[0], "AM")
        pm_rate = _latest_rate_from_table(rate_tables[-1], "PM")
    else:
        am_rate = _latest_rate_from_table(rate_tables[0], "UNKNOWN")

    chosen = pm_rate or am_rate
    if chosen is None:
        raise IbjaFetchError("Could not parse any rate row from IBJA tables")
    return chosen
