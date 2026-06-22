import csv
import json
import time
from pathlib import Path
from typing import Optional

import requests

BASE_DIR = Path(__file__).resolve().parent
SYMBOLS_FILE = BASE_DIR / "data" / "bist_symbols.csv"

_price_cache: dict[str, tuple[float, float]] = {}
_CACHE_TTL = 30


class PriceFetchError(Exception):
    pass


def load_bist_symbols() -> list[dict]:
    if not SYMBOLS_FILE.exists():
        return []
    symbols: list[dict] = []
    with SYMBOLS_FILE.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("name") or "").strip()
            symbol = (row.get("symbol") or "").strip().upper()
            if symbol:
                symbols.append({"symbol": symbol, "name": name})
    return symbols


def _get_json(url: str, params: dict, headers: dict, timeout: int = 7) -> Optional[dict]:
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def _fetch_yahoo_v8(symbol: str) -> Optional[float]:
    clean = symbol.strip().upper().replace(".IS", "")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{clean}.IS"
    params = {"range": "1d", "interval": "1m"}
    headers = {"User-Agent": "Mozilla/5.0 BISTAlarmBot/2.0", "Accept": "application/json"}
    data = _get_json(url, params, headers)
    if not data:
        return None
    try:
        result = data["chart"]["result"][0]
        meta = result.get("meta", {})
        price = meta.get("regularMarketPrice")
        if price is not None:
            return float(price)
        closes = result["indicators"]["quote"][0].get("close") or []
        valid = [float(x) for x in closes if x is not None]
        if valid:
            return valid[-1]
    except Exception:
        pass
    return None


def _fetch_yahoo_v7(symbol: str) -> Optional[float]:
    clean = symbol.strip().upper().replace(".IS", "")
    url = "https://query1.finance.yahoo.com/v7/finance/quote"
    params = {"symbols": f"{clean}.IS"}
    headers = {"User-Agent": "Mozilla/5.0 BISTAlarmBot/2.0", "Accept": "application/json"}
    data = _get_json(url, params, headers)
    if not data:
        return None
    try:
        quotes = data.get("quoteResponse", {}).get("result", [])
        if quotes:
            price = quotes[0].get("regularMarketPrice")
            if price is not None:
                return float(price)
    except Exception:
        pass
    return None


def get_bist_price(symbol: str) -> Optional[float]:
    clean = symbol.strip().upper().replace(".IS", "")

    if clean in _price_cache:
        cached_price, cached_time = _price_cache[clean]
        if time.time() - cached_time < _CACHE_TTL:
            return cached_price

    for fetcher in [_fetch_yahoo_v8, _fetch_yahoo_v7]:
        try:
            price = fetcher(clean)
            if price is not None and price > 0:
                _price_cache[clean] = (price, time.time())
                return price
        except Exception:
            continue

    raise PriceFetchError(f"{clean} fiyatı alınamadı")


def get_historical_prices(symbol: str, range_str: str = "3mo", interval: str = "1d") -> Optional[list[float]]:
    clean = symbol.strip().upper().replace(".IS", "")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{clean}.IS"
    params = {"range": range_str, "interval": interval}
    headers = {"User-Agent": "Mozilla/5.0 BISTAlarmBot/2.0", "Accept": "application/json"}

    data = _get_json(url, params, headers, timeout=8)
    if not data:
        return None
    try:
        result = data["chart"]["result"][0]
        closes = result["indicators"]["quote"][0].get("close") or []
        valid = [float(x) for x in closes if x is not None]
        return valid if valid else None
    except Exception:
        return None


def get_price_history_chart(symbol: str, range_str: str = "1mo", interval: str = "1d") -> Optional[dict]:
    """Fiyat ve tarih bilgisini birlikte döndür (chart çizimi için)."""
    clean = symbol.strip().upper().replace(".IS", "")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{clean}.IS"
    params = {"range": range_str, "interval": interval}
    headers = {"User-Agent": "Mozilla/5.0 BISTAlarmBot/2.0", "Accept": "application/json"}

    data = _get_json(url, params, headers, timeout=8)
    if not data:
        return None
    try:
        result = data["chart"]["result"][0]
        timestamps = result.get("timestamp", [])
        quote = result["indicators"]["quote"][0]
        closes = quote.get("close") or []
        volumes = quote.get("volume") or []
        prices = []
        for ts, close, vol in zip(timestamps, closes, volumes):
            if close is not None:
                prices.append({"t": ts, "p": float(close), "v": float(vol) if vol else 0})
        return {"symbol": clean, "prices": prices} if prices else None
    except Exception:
        return None


if __name__ == "__main__":
    print(json.dumps(load_bist_symbols()[:5], ensure_ascii=False, indent=2))
    print("THYAO fiyat:", get_bist_price("THYAO"))
    hist = get_historical_prices("THYAO", "3mo")
    if hist:
        print(f"THYAO geçmiş veri: {len(hist)} gün, son: {hist[-1]:.2f}")
