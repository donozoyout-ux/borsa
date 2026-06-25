"""Alpaca API modülü — ABD borsasında otomatik işlem için."""

import os
import json
import time
import hmac
import hashlib
import base64
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

SETTINGS_FILE = Path(__file__).resolve().parent / "data" / "alpaca_settings.json"
ORDERS_FILE = Path(__file__).resolve().parent / "data" / "alpaca_orders.json"

ALPACA_BASE_URL = "https://paper-api.alpaca.markets"
ALPACA_DATA_URL = "https://data.alpaca.markets"


def _get_headers() -> dict:
    key = os.getenv("ALPACA_API_KEY", "")
    secret = os.getenv("ALPACA_API_SECRET", "")
    return {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        "Content-Type": "application/json",
    }


def is_configured() -> bool:
    return bool(os.getenv("ALPACA_API_KEY") and os.getenv("ALPACA_API_SECRET"))


def get_account() -> dict:
    if not is_configured():
        return {"error": "Alpaca API ayarlanmamis"}
    try:
        r = requests.get(f"{ALPACA_BASE_URL}/v2/account", headers=_get_headers(), timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def get_positions() -> list[dict]:
    if not is_configured():
        return []
    try:
        r = requests.get(f"{ALPACA_BASE_URL}/v2/positions", headers=_get_headers(), timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return []


def get_stock_price(symbol: str) -> Optional[float]:
    try:
        r = requests.get(
            f"{ALPACA_DATA_URL}/v2/stocks/{symbol}/trades/latest",
            headers=_get_headers(),
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        return float(data["trade"]["p"])
    except Exception:
        return None


def get_stock_bars(symbol: str, timeframe: str = "1Day", limit: int = 100) -> list[dict]:
    try:
        r = requests.get(
            f"{ALPACA_DATA_URL}/v2/stocks/{symbol}/bars",
            headers=_get_headers(),
            params={"timeframe": timeframe, "limit": limit},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("bars", [])
    except Exception:
        return []


def place_order(
    symbol: str,
    qty: int,
    side: str = "buy",
    order_type: str = "market",
    time_in_force: str = "day",
    limit_price: Optional[float] = None,
    stop_price: Optional[float] = None,
) -> dict:
    if not is_configured():
        return {"error": "Alpaca API ayarlanmamis"}

    if qty <= 0:
        return {"error": "Gecersiz lot miktari"}

    order = {
        "symbol": symbol.upper(),
        "qty": str(qty),
        "side": side,
        "type": order_type,
        "time_in_force": time_in_force,
    }

    if order_type == "limit" and limit_price:
        order["limit_price"] = str(round(limit_price, 2))
    if order_type == "stop" and stop_price:
        order["stop_price"] = str(round(stop_price, 2))

    try:
        r = requests.post(
            f"{ALPACA_BASE_URL}/v2/orders",
            headers=_get_headers(),
            json=order,
            timeout=10,
        )
        r.raise_for_status()
        result = r.json()

        _save_order(result)
        return result
    except requests.exceptions.HTTPError as e:
        error_detail = ""
        try:
            error_detail = e.response.json().get("message", str(e))
        except Exception:
            error_detail = str(e)
        return {"error": f"Emir hatasi: {error_detail}"}
    except Exception as e:
        return {"error": str(e)}


def cancel_order(order_id: str) -> dict:
    if not is_configured():
        return {"error": "Alpaca API ayarlanmamis"}
    try:
        r = requests.delete(f"{ALPACA_BASE_URL}/v2/orders/{order_id}", headers=_get_headers(), timeout=10)
        if r.status_code == 204:
            return {"ok": True}
        return {"error": "Iptal hatasi"}
    except Exception as e:
        return {"error": str(e)}


def get_orders(status: str = "open") -> list[dict]:
    if not is_configured():
        return []
    try:
        r = requests.get(
            f"{ALPACA_BASE_URL}/v2/orders",
            headers=_get_headers(),
            params={"status": status},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return []


def get_latest_quote(symbol: str) -> dict:
    try:
        r = requests.get(
            f"{ALPACA_DATA_URL}/v2/stocks/{symbol}/quotes/latest",
            headers=_get_headers(),
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}


def search_symbol(query: str) -> list[dict]:
    try:
        r = requests.get(
            f"{ALPACA_DATA_URL}/v1beta1/us/symbols/search",
            params={"q": query, "limit": 10},
            headers=_get_headers(),
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("symbols", [])
    except Exception:
        return []


def _save_order(order: dict) -> None:
    try:
        orders = []
        if ORDERS_FILE.exists():
            orders = json.loads(ORDERS_FILE.read_text(encoding="utf-8"))
        orders.insert(0, {
            "id": order.get("id"),
            "symbol": order.get("symbol"),
            "qty": order.get("qty"),
            "side": order.get("side"),
            "type": order.get("type"),
            "status": order.get("status"),
            "filled_avg_price": order.get("filled_avg_price"),
            "created_at": order.get("created_at"),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        if len(orders) > 50:
            orders = orders[:50]
        ORDERS_FILE.parent.mkdir(exist_ok=True)
        ORDERS_FILE.write_text(json.dumps(orders, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def get_portfolio_summary() -> dict:
    account = get_account()
    if "error" in account:
        return account

    positions = get_positions()
    total_value = float(account.get("equity", 0))
    buying_power = float(account.get("buying_power", 0))
    cash = float(account.get("cash", 0))
    day_pnl = float(account.get("equity", 0)) - float(account.get("last_equity", 0))
    day_pnl_pct = (day_pnl / float(account["last_equity"]) * 100) if account.get("last_equity") else 0

    pos_list = []
    for p in positions:
        unrealized_pl = float(p.get("unrealized_pl", 0))
        unrealized_plpc = float(p.get("unrealized_plpc", 0))
        pos_list.append({
            "symbol": p.get("symbol"),
            "qty": p.get("qty"),
            "avg_entry": p.get("avg_entry_price"),
            "current_price": p.get("current_price"),
            "market_value": p.get("market_value"),
            "unrealized_pl": round(unrealized_pl, 2),
            "unrealized_plpc": round(unrealized_plpc * 100, 2),
            "side": p.get("side"),
        })

    return {
        "equity": round(total_value, 2),
        "buying_power": round(buying_power, 2),
        "cash": round(cash, 2),
        "day_pnl": round(day_pnl, 2),
        "day_pnl_pct": round(day_pnl_pct, 2),
        "positions": pos_list,
        "positions_count": len(pos_list),
    }


def test_connection() -> dict:
    if not is_configured():
        return {"ok": False, "error": "ALPICA_API_KEY ve ALPACA_API_SECRET ayarlanmamis"}
    try:
        account = get_account()
        if "error" in account:
            return {"ok": False, "error": account["error"]}
        return {
            "ok": True,
            "account_id": account.get("id"),
            "status": account.get("status"),
            "equity": account.get("equity"),
            "buying_power": account.get("buying_power"),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
