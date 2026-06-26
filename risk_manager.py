"""Risk yönetimi modülü — SL/TP hesaplama, pozisyon büyüklüğü, limitler."""

import json
from pathlib import Path
from datetime import datetime, date

SETTINGS_FILE = Path(__file__).resolve().parent / "data" / "trading_settings.json"
DAILY_STATS_FILE = Path(__file__).resolve().parent / "data" / "daily_stats.json"

DEFAULT_SETTINGS = {
    "max_position_pct": 10,        # Tek hisseye max portföyün %10'u
    "max_daily_loss_pct": 3,       # Günlük toplam zarar limiti (%)
    "max_open_positions": 5,       # Aynı anda max 5 açık pozisyon
    "min_signal_strength": 70,     # Minimum sinyal gücü (%)
    "sl_method": "atr",            # "atr" veya "percent"
    "atr_sl_multiplier": 1.5,      # ATR × 1.5 = SL mesafesi
    "fixed_sl_pct": 2.5,           # Sabit SL yüzdesi
    "tp_rr_ratio": 2.0,            # Risk/Ödül oranı (min 1:2)
    "tp_method": "rr",             # "rr" veya "percent"
    "fixed_tp_pct": 5.0,           # Sabit TP yüzdesi
    "portfolio_total_tl": 100000,  # Toplam portföy büyüklüğü (TL)
    "auto_scan_enabled": False,    # Otomatik tarama aktif mi
    "auto_scan_interval": 30,      # Tarama aralığı (dakika)
    "auto_scan_min_strength": 82,  # Otomatik tarama min sinyal gücü
    "enabled": True,
}


def load_settings() -> dict:
    try:
        if SETTINGS_FILE.exists():
            saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            merged = {**DEFAULT_SETTINGS, **saved}
            return merged
    except Exception:
        pass
    return DEFAULT_SETTINGS.copy()


def save_settings(settings: dict) -> None:
    SETTINGS_FILE.parent.mkdir(exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


def load_daily_stats() -> dict:
    today = date.today().isoformat()
    try:
        if DAILY_STATS_FILE.exists():
            data = json.loads(DAILY_STATS_FILE.read_text(encoding="utf-8"))
            if data.get("date") == today:
                return data
    except Exception:
        pass
    return {"date": today, "trades": 0, "pnl": 0.0, "wins": 0, "losses": 0}


def save_daily_stats(stats: dict) -> None:
    DAILY_STATS_FILE.parent.mkdir(exist_ok=True)
    DAILY_STATS_FILE.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")


def calculate_stop_loss(current_price: float, atr_value: float | None, direction: str = "BUY") -> dict:
    settings = load_settings()

    if settings["sl_method"] == "atr" and atr_value and atr_value > 0:
        sl_distance = atr_value * settings["atr_sl_multiplier"]
    else:
        sl_distance = current_price * (settings["fixed_sl_pct"] / 100)

    if direction == "BUY":
        stop_loss = round(current_price - sl_distance, 2)
    else:
        stop_loss = round(current_price + sl_distance, 2)

    sl_pct = round(abs(current_price - stop_loss) / current_price * 100, 2)

    return {
        "stop_loss": stop_loss,
        "sl_distance": round(sl_distance, 2),
        "sl_pct": sl_pct,
        "method": settings["sl_method"],
    }


def calculate_take_profit(current_price: float, stop_loss: float, direction: str = "BUY") -> dict:
    settings = load_settings()
    sl_distance = abs(current_price - stop_loss)

    if settings["tp_method"] == "rr":
        tp_distance = sl_distance * settings["tp_rr_ratio"]
    else:
        tp_distance = current_price * (settings["fixed_tp_pct"] / 100)

    if direction == "BUY":
        take_profit = round(current_price + tp_distance, 2)
    else:
        take_profit = round(current_price - tp_distance, 2)

    tp_pct = round(abs(take_profit - current_price) / current_price * 100, 2)
    rr_ratio = round(tp_distance / sl_distance, 2) if sl_distance > 0 else 0

    return {
        "take_profit": take_profit,
        "tp_distance": round(tp_distance, 2),
        "tp_pct": tp_pct,
        "rr_ratio": rr_ratio,
    }


def calculate_position_size(current_price: float, stop_loss: float) -> dict:
    settings = load_settings()
    portfolio = settings["portfolio_total_tl"]
    max_risk_pct = settings["max_daily_loss_pct"]
    max_per_stock_pct = settings["max_position_pct"]

    max_amount_per_stock = portfolio * (max_per_stock_pct / 100)
    max_shares_by_position = int(max_amount_per_stock / current_price) if current_price > 0 else 0

    risk_per_share = abs(current_price - stop_loss)
    if risk_per_share > 0:
        max_risk_amount = portfolio * (max_risk_pct / 100)
        max_shares_by_risk = int(max_risk_amount / risk_per_share)
    else:
        max_shares_by_risk = max_shares_by_position

    recommended_lots = min(max_shares_by_position, max_shares_by_risk)
    recommended_amount = round(recommended_lots * current_price, 2)

    return {
        "recommended_lots": recommended_lots,
        "recommended_amount": recommended_amount,
        "max_by_position": max_shares_by_position,
        "max_by_risk": max_shares_by_risk,
        "portfolio_pct": round(recommended_amount / portfolio * 100, 2) if portfolio > 0 else 0,
    }


def can_open_trade() -> dict:
    settings = load_settings()
    daily = load_daily_stats()

    reasons = []
    allowed = True

    if not settings["enabled"]:
        allowed = False
        reasons.append("Trading devre dışı")

    if daily["trades"] >= settings["max_open_positions"]:
        allowed = False
        reasons.append(f"Maks pozisyon sayısına ulaşıldı ({settings['max_open_positions']})")

    daily_loss_pct = abs(daily["pnl"]) / settings["portfolio_total_tl"] * 100 if daily["pnl"] < 0 else 0
    if daily_loss_pct >= settings["max_daily_loss_pct"]:
        allowed = False
        reasons.append(f"Günlük zarar limitine ulaşıldı (%{daily_loss_pct:.1f})")

    return {
        "allowed": allowed,
        "reasons": reasons,
        "daily_trades": daily["trades"],
        "daily_pnl": daily["pnl"],
        "max_positions": settings["max_open_positions"],
    }


def record_trade(pnl: float = 0) -> None:
    stats = load_daily_stats()
    stats["trades"] += 1
    stats["pnl"] = round(stats["pnl"] + pnl, 2)
    if pnl > 0:
        stats["wins"] += 1
    elif pnl < 0:
        stats["losses"] += 1
    save_daily_stats(stats)


def format_signal_message(signal: dict) -> str:
    direction = signal.get("direction", "BUY")
    emoji = "📈" if direction == "BUY" else "📉"
    action = "AL" if direction == "BUY" else "SAT"

    lines = [
        f"{emoji} <b>YENİ İŞLEM SİNYALİ</b>",
        "",
        f"<b>{signal['symbol']}</b> — {action}",
        f"Giriş: <b>{signal['entry_price']} TL</b>",
        f"SL: <b>{signal['stop_loss']} TL</b> (%{signal['sl_pct']})",
        f"TP: <b>{signal['take_profit']} TL</b> (%{signal['tp_pct']})",
        f"R/R: <b>1:{signal['rr_ratio']}</b>",
        f"Güç: <b>%{signal['strength']}</b>",
        f"Lots: <b>{signal['position_size']}</b>",
        "",
        f"Strateji: {signal.get('strategy', 'N/A')}",
    ]

    if signal.get("ai_confirmation"):
        lines.append(f"AI: {signal['ai_confirmation'][:80]}")

    lines.extend([
        "",
        f"ID: {signal['id']}",
        f"Zaman: {signal['timestamp']}",
    ])

    return "\n".join(lines)
