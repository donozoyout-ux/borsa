"""Order manager — sinyal onay/ret akışı, emir takibi, geçmiş."""

import json
from datetime import datetime
from pathlib import Path

from trading_engine import get_signal, update_signal_status
from risk_manager import record_trade, load_daily_stats

ORDERS_FILE = Path(__file__).resolve().parent / "data" / "orders.json"


def _load_orders() -> list[dict]:
    try:
        if ORDERS_FILE.exists():
            return json.loads(ORDERS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []


def _save_orders(orders: list[dict]) -> None:
    ORDERS_FILE.parent.mkdir(exist_ok=True)
    ORDERS_FILE.write_text(json.dumps(orders, ensure_ascii=False, indent=2), encoding="utf-8")


def approve_signal(signal_id: str, note: str = "") -> dict:
    signal = get_signal(signal_id)
    if not signal:
        return {"ok": False, "error": "Sinyal bulunamadı"}

    if signal["status"] != "pending":
        return {"ok": False, "error": f"Sinyal zaten {signal['status']}"}

    update_signal_status(signal_id, "approved")

    order = {
        "id": f"ord_{signal_id.replace('sig_', '')}",
        "signal_id": signal_id,
        "symbol": signal["symbol"],
        "direction": signal["direction"],
        "entry_price": signal["entry_price"],
        "stop_loss": signal["stop_loss"],
        "take_profit": signal["take_profit"],
        "rr_ratio": signal["rr_ratio"],
        "lots": signal["position_size"],
        "amount": signal["position_amount"],
        "status": "approved",
        "note": note,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "executed_at": None,
        "closed_at": None,
        "pnl": None,
    }

    orders = _load_orders()
    orders.insert(0, order)
    _save_orders(orders)

    return {"ok": True, "order": order}


def reject_signal(signal_id: str, reason: str = "") -> dict:
    signal = get_signal(signal_id)
    if not signal:
        return {"ok": False, "error": "Sinyal bulunamadı"}

    update_signal_status(signal_id, "rejected")

    orders = _load_orders()
    orders.insert(0, {
        "id": f"ord_{signal_id.replace('sig_', '')}",
        "signal_id": signal_id,
        "symbol": signal["symbol"],
        "direction": signal["direction"],
        "status": "rejected",
        "reason": reason,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    _save_orders(orders)

    return {"ok": True}


def mark_executed(order_id: str) -> dict:
    orders = _load_orders()
    for o in orders:
        if o["id"] == order_id:
            o["status"] = "executed"
            o["executed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _save_orders(orders)
            update_signal_status(o["signal_id"], "executed")
            return {"ok": True, "order": o}
    return {"ok": False, "error": "Emir bulunamadı"}


def close_order(order_id: str, exit_price: float, pnl: float) -> dict:
    orders = _load_orders()
    for o in orders:
        if o["id"] == order_id:
            o["status"] = "closed"
            o["closed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            o["exit_price"] = exit_price
            o["pnl"] = round(pnl, 2)
            _save_orders(orders)
            record_trade(pnl)
            update_signal_status(o["signal_id"], "closed")
            return {"ok": True, "order": o}
    return {"ok": False, "error": "Emir bulunamadı"}


def get_orders(status: str | None = None, limit: int = 50) -> list[dict]:
    orders = _load_orders()
    if status:
        orders = [o for o in orders if o.get("status") == status]
    return orders[:limit]


def get_active_orders() -> list[dict]:
    orders = _load_orders()
    return [o for o in orders if o.get("status") in ("approved", "executed")]


def get_order(order_id: str) -> dict | None:
    orders = _load_orders()
    for o in orders:
        if o["id"] == order_id:
            return o
    return None


def get_trading_summary() -> dict:
    orders = _load_orders()
    daily = load_daily_stats()

    executed = [o for o in orders if o.get("status") == "closed"]
    wins = [o for o in executed if (o.get("pnl") or 0) > 0]
    losses = [o for o in executed if (o.get("pnl") or 0) < 0]

    total_pnl = sum(o.get("pnl", 0) for o in executed)
    win_rate = len(wins) / len(executed) * 100 if executed else 0

    return {
        "total_trades": len(executed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 1),
        "total_pnl": round(total_pnl, 2),
        "avg_pnl": round(total_pnl / len(executed), 2) if executed else 0,
        "daily_trades": daily["trades"],
        "daily_pnl": daily["pnl"],
        "pending_signals": len([o for o in orders if o.get("status") == "approved"]),
    }
