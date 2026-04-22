"""USD to INR exchange rate fetcher. Free, no auth."""
import requests
from scripts.config import REQUEST_HEADERS, REQUEST_TIMEOUT


class FxError(Exception):
    pass


def fetch_usd_inr() -> float:
    """Return current USD→INR rate as a float. Raises FxError on any failure."""
    primary = "https://open.er-api.com/v6/latest/USD"
    try:
        r = requests.get(primary, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        rate = data.get("rates", {}).get("INR")
        if rate and float(rate) > 0:
            return float(rate)
    except Exception as e:
        print(f"[fx] primary source failed: {e}")

    fallback = "https://api.frankfurter.app/latest?from=USD&to=INR"
    try:
        r = requests.get(fallback, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        rate = data.get("rates", {}).get("INR")
        if rate and float(rate) > 0:
            return float(rate)
    except Exception as e:
        print(f"[fx] fallback source failed: {e}")

    raise FxError("All FX sources failed. Cannot fetch USD→INR rate.")
