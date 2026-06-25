"""Trading engine — sinyal üretimi: RSI, MACD, Bollinger, AI onayı, skorlama."""

import json
import uuid
from datetime import datetime
from pathlib import Path

from indicators import rsi, macd, bollinger_bands, sma, ema, analyze_trend, calculate_all
from risk_manager import (
    calculate_stop_loss,
    calculate_take_profit,
    calculate_position_size,
    can_open_trade,
    load_settings,
)
from ai_analysis import get_signal_prediction

SIGNALS_FILE = Path(__file__).resolve().parent / "data" / "signals.json"


def _load_signals() -> list[dict]:
    try:
        if SIGNALS_FILE.exists():
            return json.loads(SIGNALS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []


def _save_signals(signals: list[dict]) -> None:
    SIGNALS_FILE.parent.mkdir(exist_ok=True)
    SIGNALS_FILE.write_text(json.dumps(signals, ensure_ascii=False, indent=2), encoding="utf-8")


def _rsi_signal(prices: list[float]) -> dict:
    val = rsi(prices)
    if val is None:
        return {"name": "RSI", "signal": "neutral", "strength": 0, "detail": "Veri yetersiz"}

    if val < 25:
        return {"name": "RSI", "signal": "strong_buy", "strength": 25, "detail": f"RSI {val:.1f} — Aşırı satım"}
    elif val < 30:
        return {"name": "RSI", "signal": "buy", "strength": 18, "detail": f"RSI {val:.1f} — Satım bölgesi"}
    elif val > 75:
        return {"name": "RSI", "signal": "strong_sell", "strength": 25, "detail": f"RSI {val:.1f} — Aşırı alım"}
    elif val > 70:
        return {"name": "RSI", "signal": "sell", "strength": 18, "detail": f"RSI {val:.1f} — Alım bölgesi"}
    return {"name": "RSI", "signal": "neutral", "strength": 0, "detail": f"RSI {val:.1f} — Nötr"}


def _macd_signal(prices: list[float]) -> dict:
    val = macd(prices)
    if val is None:
        return {"name": "MACD", "signal": "neutral", "strength": 0, "detail": "Veri yetersiz"}

    crossover = val["crossover"]
    histogram = val["histogram"]

    if crossover == "bullish":
        strength = 22 if histogram > 0 else 15
        return {"name": "MACD", "signal": "buy", "strength": strength, "detail": f"MACD Bullish kesişim (hist: {histogram:.4f})"}
    elif crossover == "bearish":
        strength = 22 if histogram < 0 else 15
        return {"name": "MACD", "signal": "sell", "strength": strength, "detail": f"MACD Bearish kesişim (hist: {histogram:.4f})"}

    if histogram > 0:
        return {"name": "MACD", "signal": "neutral", "strength": 5, "detail": f"MACD pozitif (hist: {histogram:.4f})"}
    elif histogram < 0:
        return {"name": "MACD", "signal": "neutral", "strength": -5, "detail": f"MACD negatif (hist: {histogram:.4f})"}

    return {"name": "MACD", "signal": "neutral", "strength": 0, "detail": "MACD nötr"}


def _bollinger_signal(prices: list[float]) -> dict:
    val = bollinger_bands(prices)
    if val is None:
        return {"name": "Bollinger", "signal": "neutral", "strength": 0, "detail": "Veri yetersiz"}

    position = val["position"]
    price = prices[-1]

    if position == "lower":
        return {"name": "Bollinger", "signal": "buy", "strength": 18, "detail": f"Alt banda değdi ({price:.2f} < {val['lower']:.2f})"}
    elif position == "upper":
        return {"name": "Bollinger", "signal": "sell", "strength": 18, "detail": f"Üst banda değdi ({price:.2f} > {val['upper']:.2f})"}

    return {"name": "Bollinger", "signal": "neutral", "strength": 0, "detail": f"Orta bantta ({position})"}


def _ma_crossover_signal(prices: list[float]) -> dict:
    sma20 = sma(prices, 20)
    sma50 = sma(prices, 50)
    ema12 = ema(prices, 12)
    ema26 = ema(prices, 26)

    if not all([sma20, sma50, ema12, ema26]):
        return {"name": "MA Kesişim", "signal": "neutral", "strength": 0, "detail": "Veri yetersiz"}

    signals = []
    strength = 0

    if ema12 > ema26:
        signals.append("EMA12>26")
        strength += 8
    else:
        signals.append("EMA12<26")
        strength -= 8

    if sma20 > sma50:
        signals.append("SMA20>50")
        strength += 7
    else:
        signals.append("SMA20<50")
        strength -= 7

    if strength > 10:
        return {"name": "MA Kesişim", "signal": "buy", "strength": strength, "detail": f"{', '.join(signals)} — Yükseliş"}
    elif strength < -10:
        return {"name": "MA Kesişim", "signal": "sell", "strength": abs(strength), "detail": f"{', '.join(signals)} — Düşüş"}

    return {"name": "MA Kesişim", "signal": "neutral", "strength": 0, "detail": f"{', '.join(signals)} — Nötr"}


def _trend_signal(prices: list[float]) -> dict:
    trend = analyze_trend(prices)
    score = trend.get("score", 50)
    trend_dir = trend.get("trend", "nötr")

    if score >= 70:
        return {"name": "Trend", "signal": "buy", "strength": 15, "detail": f"Güçlü yükseliş trendi (skor: {score})"}
    elif score <= 30:
        return {"name": "Trend", "signal": "sell", "strength": 15, "detail": f"Güçlü düşüş trendi (skor: {score})"}

    return {"name": "Trend", "signal": "neutral", "strength": 0, "detail": f"Trend: {trend_dir} (skor: {score})"}


def generate_signal(symbol: str, prices: list[float], current_price: float, ai_analysis: str | None = None) -> dict | None:
    if len(prices) < 30:
        return None

    trade_check = can_open_trade()
    if not trade_check["allowed"]:
        return None

    all_signals = [
        _rsi_signal(prices),
        _macd_signal(prices),
        _bollinger_signal(prices),
        _ma_crossover_signal(prices),
        _trend_signal(prices),
    ]

    buy_score = sum(s["strength"] for s in all_signals if s["signal"] in ("buy", "strong_buy"))
    sell_score = sum(s["strength"] for s in all_signals if s["signal"] in ("sell", "strong_sell"))
    buy_count = sum(1 for s in all_signals if s["signal"] in ("buy", "strong_buy"))
    sell_count = sum(1 for s in all_signals if s["signal"] in ("sell", "strong_sell"))

    ai_bonus = 0
    ai_confirmation = None
    ai_prediction = None
    if ai_analysis:
        lower = ai_analysis.lower()
        if "al" in lower or "buy" in lower:
            ai_bonus = 20
            ai_confirmation = "AI Onayli Yukselis"
        elif "sat" in lower or "sell" in lower:
            ai_bonus = -20
            ai_confirmation = "AI Onayli Dusus"
        ai_prediction = ai_analysis[:500]

    net_score = buy_score - sell_score + ai_bonus
    total_strength = min(100, max(0, 50 + net_score))

    settings = load_settings()
    settings["min_signal_strength"] = 82
    if total_strength < settings["min_signal_strength"]:
        return None

    if buy_score > sell_score and buy_count >= 3:
        direction = "BUY"
    elif sell_score > buy_score and sell_count >= 3:
        direction = "SELL"
    else:
        return None

    atr_data = calculate_all(prices).get("atr")
    atr_value = atr_data["value"] if atr_data else None

    sl = calculate_stop_loss(current_price, atr_value, direction)
    tp = calculate_take_profit(current_price, sl["stop_loss"], direction)
    pos = calculate_position_size(current_price, sl["stop_loss"])

    if pos["recommended_lots"] <= 0:
        return None

    strategy_parts = []
    for s in all_signals:
        if s["signal"] != "neutral":
            strategy_parts.append(s["name"])

    ai_prediction = None
    try:
        trend_result = analyze_trend(prices)
        ai_prediction = get_signal_prediction(
            symbol=symbol,
            price=current_price,
            direction=direction,
            indicators=calculate_all(prices),
            trend=trend_result,
            entry_price=current_price,
            stop_loss=sl["stop_loss"],
            take_profit=tp["take_profit"],
        )
    except Exception:
        pass

    signal = {
        "id": f"sig_{uuid.uuid4().hex[:8]}",
        "symbol": symbol.upper(),
        "direction": direction,
        "entry_price": current_price,
        "stop_loss": sl["stop_loss"],
        "sl_pct": sl["sl_pct"],
        "take_profit": tp["take_profit"],
        "tp_pct": tp["tp_pct"],
        "rr_ratio": tp["rr_ratio"],
        "strength": total_strength,
        "position_size": pos["recommended_lots"],
        "position_amount": pos["recommended_amount"],
        "strategy": " + ".join(strategy_parts) if strategy_parts else "Karma",
        "signals": all_signals,
        "ai_analysis": ai_analysis[:500] if ai_analysis else None,
        "ai_confirmation": ai_confirmation,
        "ai_prediction": ai_prediction,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "pending",
    }

    signals = _load_signals()
    signals.insert(0, signal)
    if len(signals) > 100:
        signals = signals[:100]
    _save_signals(signals)

    return signal


def scan_all_stocks(prices_cache: dict, get_history_func) -> list[dict]:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    signals = []
    settings = load_settings()

    top_stocks = [(s, p) for s, p in prices_cache.items() if p and p > 0][:50]

    def _scan_one(item):
        symbol, price = item
        try:
            hist = get_history_func(symbol, range_str="1mo", interval="1d")
            if not hist or len(hist) < 20:
                return None
            return generate_signal(symbol, hist, price)
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(_scan_one, item): item for item in top_stocks}
        for f in as_completed(futures, timeout=30):
            try:
                sig = f.result()
                if sig:
                    signals.append(sig)
            except Exception:
                pass

    signals.sort(key=lambda x: x["strength"], reverse=True)
    return signals[:7]


def get_signals(status: str | None = None) -> list[dict]:
    signals = _load_signals()
    if status:
        signals = [s for s in signals if s.get("status") == status]
    return signals


def get_signal(signal_id: str) -> dict | None:
    signals = _load_signals()
    for s in signals:
        if s["id"] == signal_id:
            return s
    return None


def update_signal_status(signal_id: str, status: str) -> bool:
    signals = _load_signals()
    for s in signals:
        if s["id"] == signal_id:
            s["status"] = status
            s["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _save_signals(signals)
            return True
    return False
