import csv
import json
import threading
import time
from pathlib import Path
from typing import Optional

import requests

BASE_DIR = Path(__file__).resolve().parent
SYMBOLS_FILE = BASE_DIR / "data" / "bist_symbols.csv"
PRICE_CACHE_FILE = BASE_DIR / "data" / "price_cache.json"

_price_cache: dict[str, tuple[float, float]] = {}
_CACHE_TTL = 30

_file_price_cache: dict[str, float] = {}
_file_cache_lock = threading.Lock()
_file_cache_time = 0.0


def _load_file_cache():
    global _file_cache_time, _file_price_cache
    try:
        if PRICE_CACHE_FILE.exists():
            with PRICE_CACHE_FILE.open("r") as f:
                data = json.load(f)
            with _file_cache_lock:
                _file_price_cache = data.get("prices", {})
                _file_cache_time = data.get("time", 0.0)
    except Exception:
        pass


def _save_file_cache():
    try:
        with _file_cache_lock:
            data = {"time": time.time(), "prices": _file_price_cache}
        PRICE_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with PRICE_CACHE_FILE.open("w") as f:
            json.dump(data, f)
    except Exception:
        pass


def get_all_cached_prices() -> tuple[dict[str, float], float]:
    with _file_cache_lock:
        return dict(_file_price_cache), _file_cache_time


def refresh_all_prices():
    all_syms = load_bist_symbols()
    sym_list = [s["symbol"] for s in all_syms]
    
    results = _fetch_tv_batch(sym_list)
    if results:
        price_map = {k: v["last"] for k, v in results.items() if v.get("last")}
        with _file_cache_lock:
            _file_price_cache.update(price_map)
        _save_file_cache()
        return

    results = _fetch_bigpara_all()
    if not results:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        results = {}
        with ThreadPoolExecutor(max_workers=10) as ex:
            fut = {ex.submit(get_bist_price_nocache, s): s for s in sym_list}
            for f in as_completed(fut, timeout=30):
                try:
                    p = f.result()
                    if p is not None:
                        results[fut[f]] = p
                except Exception:
                    pass
    with _file_cache_lock:
        _file_price_cache.update(results)
    _save_file_cache()


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


_TV_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Content-Type": "text/plain",
}


def _fetch_tv_single(symbol: str) -> Optional[float]:
    """TradingView Scanner API ile tek hisse fiyati al."""
    clean = symbol.strip().upper().replace(".IS", "")
    body = json.dumps({
        "columns": ["name", "close", "change", "high", "low", "open", "volume"],
        "symbols": {"tickers": [f"BIST:{clean}"]},
        "markets": ["turkey"],
    })
    try:
        r = requests.post(
            "https://scanner.tradingview.com/turkey/scan",
            data=body, headers=_TV_HEADERS, timeout=10,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        for item in data.get("data", []):
            vals = item.get("d", [])
            if len(vals) >= 2 and vals[1] is not None:
                return float(vals[1])
    except Exception:
        pass
    return None


def _fetch_tv_batch(symbols: list[str]) -> dict[str, dict]:
    """TradingView Scanner API ile toplu fiyat + detay al."""
    clean_list = [s.strip().upper().replace(".IS", "") for s in symbols]
    body = json.dumps({
        "columns": ["name", "close", "change", "change_abs", "high", "low", "open", "volume",
                     "market_cap_basic", "price_52_week_high", "price_52_week_low",
                     "average_volume_10d_calc", "description"],
        "symbols": {"tickers": [f"BIST:{s}" for s in clean_list]},
        "markets": ["turkey"],
    })
    try:
        r = requests.post(
            "https://scanner.tradingview.com/turkey/scan",
            data=body, headers=_TV_HEADERS, timeout=12,
        )
        if r.status_code != 200:
            return {}
        data = r.json()
        results = {}
        for item in data.get("data", []):
            sym = item.get("s", "").replace("BIST:", "")
            d = item.get("d", [])
            if sym and len(d) >= 8 and d[1] is not None:
                results[sym] = {
                    "last": d[1],
                    "change_pct": d[2],
                    "change_abs": d[3],
                    "high": d[4],
                    "low": d[5],
                    "open": d[6],
                    "volume": d[7],
                    "market_cap": d[8] if len(d) > 8 else None,
                    "52w_high": d[9] if len(d) > 9 else None,
                    "52w_low": d[10] if len(d) > 10 else None,
                    "avg_volume": d[11] if len(d) > 11 else None,
                    "name": d[12] if len(d) > 12 else "",
                }
        return results
    except Exception:
        return {}


def _fetch_bigpara(symbol: str) -> Optional[float]:
    """Bigpara (Hurriyet) API'den BIST fiyati al."""
    clean = symbol.strip().upper().replace(".IS", "")
    url = f"https://bigpara.hurriyet.com.tr/api/v1/hisse/{clean}/fiyat"
    headers = {"User-Agent": "Mozilla/5.0 BISTAlarmBot/2.0", "Accept": "application/json"}
    try:
        resp = requests.get(url, headers=headers, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        price = data.get("data", {}).get("son")
        if price is not None:
            return float(str(price).replace(",", "."))
    except Exception:
        pass
    return None


def _fetch_bigpara_all() -> Optional[dict]:
    """Tum BIST hisselerini Bigpara'dan al."""
    url = "https://bigpara.hurriyet.com.tr/api/v1/borsa/canli-borsa"
    headers = {"User-Agent": "Mozilla/5.0 BISTAlarmBot/2.0", "Accept": "application/json"}
    try:
        resp = requests.get(url, headers=headers, timeout=12)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("data", [])
        if not items:
            return None
        result = {}
        for item in items:
            sym = (item.get("kod") or "").strip().upper()
            p = item.get("son")
            if sym and p is not None:
                try:
                    result[sym] = float(str(p).replace(",", "."))
                except (ValueError, TypeError):
                    pass
        return result if result else None
    except Exception:
        return None


def _fetch_yahoo_v8(symbol: str) -> Optional[float]:
    clean = symbol.strip().upper().replace(".IS", "")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{clean}.IS"
    params = {"range": "1d", "interval": "1d"}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36", "Accept": "application/json"}
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


def _fetch_yahoo_v8_batch(symbols: list[str]) -> dict[str, float]:
    """Yahoo v8 ile toplu fiyat al — her sembol icin ayri istek paralel gonder."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    results = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        fut = {ex.submit(_fetch_yahoo_v8, s): s for s in symbols}
        for f in as_completed(fut, timeout=20):
            try:
                price = f.result()
                if price is not None and price > 0:
                    results[fut[f]] = price
            except Exception:
                pass
    return results


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


def get_yahoo_v7_quote(symbol: str) -> Optional[dict]:
    clean = symbol.strip().upper().replace(".IS", "")
    url = "https://query1.finance.yahoo.com/v7/finance/quote"
    params = {"symbols": f"{clean}.IS"}
    headers = {"User-Agent": "Mozilla/5.0 BISTAlarmBot/2.0", "Accept": "application/json"}
    data = _get_json(url, params, headers, timeout=10)
    if not data:
        return None
    try:
        quotes = data.get("quoteResponse", {}).get("result", [])
        if quotes:
            return quotes[0]
    except Exception:
        pass
    return None


def get_yahoo_v8_chart_meta(symbol: str) -> Optional[dict]:
    clean = symbol.strip().upper().replace(".IS", "")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{clean}.IS"
    params = {"range": "1d", "interval": "1m"}
    headers = {"User-Agent": "Mozilla/5.0 BISTAlarmBot/2.0", "Accept": "application/json"}
    data = _get_json(url, params, headers, timeout=10)
    if not data:
        return None
    try:
        result = data["chart"]["result"][0]
        return result.get("meta", {})
    except Exception:
        return None


def get_bist_price_nocache(symbol: str) -> Optional[float]:
    clean = symbol.strip().upper().replace(".IS", "")
    for fetcher in [_fetch_tv_single, _fetch_bigpara, _fetch_yahoo_v8, _fetch_yahoo_v7]:
        try:
            price = fetcher(clean)
            if price is not None and price > 0:
                return price
        except Exception:
            continue
    return None


def get_bist_price(symbol: str) -> Optional[float]:
    clean = symbol.strip().upper().replace(".IS", "")

    if clean in _price_cache:
        cached_price, cached_time = _price_cache[clean]
        if time.time() - cached_time < _CACHE_TTL:
            return cached_price

    for fetcher in [_fetch_tv_single, _fetch_bigpara, _fetch_yahoo_v8, _fetch_yahoo_v7]:
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
