"""Teknik indikatör hesaplama modülü — saf Python, bağımlılık yok."""

from typing import Optional


def linear_regression_forecast(prices: list[float], days: int = 5) -> Optional[dict]:
    """Linear regresyon ile fiyat tahmini."""
    if len(prices) < 5:
        return None
    n = len(prices)
    x_vals = list(range(n))
    y_vals = prices
    x_mean = sum(x_vals) / n
    y_mean = sum(y_vals) / n
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_vals, y_vals))
    den = sum((x - x_mean) ** 2 for x in x_vals)
    slope = num / den if den != 0 else 0
    intercept = y_mean - slope * x_mean

    predictions = []
    for i in range(1, days + 1):
        pred = slope * (n + i - 1) + intercept
        predictions.append(round(pred, 2))

    last_price = prices[-1]
    change_pct = round((predictions[-1] - last_price) / last_price * 100, 2) if last_price else 0

    return {
        "predictions": predictions,
        "slope": round(slope, 4),
        "change_pct": change_pct,
        "direction": "up" if slope > 0 else ("down" if slope < 0 else "flat"),
    }


def bollinger_bands(prices: list[float], period: int = 20) -> Optional[dict]:
    """Bollinger Bands hesaplama."""
    if len(prices) < period:
        return None
    recent = prices[-period:]
    mean = sum(recent) / period
    variance = sum((x - mean) ** 2 for x in recent) / period
    std_dev = variance ** 0.5
    current = prices[-1]
    bb_width = round((std_dev * 2) / mean * 100, 2) if mean else 0

    position = "middle"
    if current > mean + std_dev:
        position = "upper"
    elif current < mean - std_dev:
        position = "lower"

    return {
        "upper": round(mean + 2 * std_dev, 2),
        "middle": round(mean, 2),
        "lower": round(mean - 2 * std_dev, 2),
        "width": bb_width,
        "position": position,
    }


def sma(prices: list[float], period: int) -> Optional[float]:
    """Simple Moving Average."""
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


def ema(prices: list[float], period: int) -> Optional[float]:
    """Exponential Moving Average."""
    if len(prices) < period:
        return None
    multiplier = 2 / (period + 1)
    ema_val = sum(prices[:period]) / period
    for price in prices[period:]:
        ema_val = (price - ema_val) * multiplier + ema_val
    return ema_val


def rsi(prices: list[float], period: int = 14) -> Optional[float]:
    """Relative Strength Index."""
    if len(prices) < period + 1:
        return None

    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(prices: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Optional[dict]:
    """MACD indicator: line, signal, histogram, crossover."""
    if len(prices) < slow + signal:
        return None

    ema_fast_vals = _ema_series(prices, fast)
    ema_slow_vals = _ema_series(prices, slow)

    if ema_fast_vals is None or ema_slow_vals is None:
        return None

    macd_line = [f - s for f, s in zip(ema_fast_vals, ema_slow_vals)]

    if len(macd_line) < signal:
        return None

    signal_line_vals = _ema_series(macd_line, signal)
    if signal_line_vals is None:
        return None

    macd_val = macd_line[-1]
    signal_val = signal_line_vals[-1]
    histogram = macd_val - signal_val

    prev_macd = macd_line[-2]
    prev_signal = signal_line_vals[-2]
    prev_histogram = prev_macd - prev_signal

    crossover = "neutral"
    if prev_histogram <= 0 and histogram > 0:
        crossover = "bullish"
    elif prev_histogram >= 0 and histogram < 0:
        crossover = "bearish"

    return {
        "macd": macd_val,
        "signal": signal_val,
        "histogram": histogram,
        "crossover": crossover,
    }


def _ema_series(data: list[float], period: int) -> Optional[list[float]]:
    """Return full EMA series for a given data list."""
    if len(data) < period:
        return None
    multiplier = 2 / (period + 1)
    ema_vals = [sum(data[:period]) / period]
    for val in data[period:]:
        ema_vals.append((val - ema_vals[-1]) * multiplier + ema_vals[-1])
    return ema_vals


def analyze_trend(prices: list[float]) -> dict:
    """Trend analizi: yön, güç, sinyaller."""
    if not prices or len(prices) < 5:
        return {"trend": "yetersiz_veri", "strength": 0, "signals": []}

    price = prices[-1]
    signals = []

    # Kısa/orta/uzun vadeli trend
    sma_20_val = sma(prices, 20)
    sma_50_val = sma(prices, 50)
    sma_200_val = sma(prices, 200)

    trend = "nötr"
    strength = 0

    if sma_20_val and sma_50_val:
        if sma_20_val > sma_50_val * 1.02:
            trend = "yükseliş"
            strength += 1
            if sma_200_val and sma_20_val > sma_200_val * 1.02:
                strength += 1
                signals.append("golden_cross")
        elif sma_20_val < sma_50_val * 0.98:
            trend = "düşüş"
            strength -= 1
            if sma_200_val and sma_20_val < sma_200_val * 0.98:
                strength -= 1
                signals.append("death_cross")

    # RSI sinyalleri
    rsi_val = rsi(prices)
    if rsi_val is not None:
        if rsi_val > 70:
            signals.append("rsi_asiri_alim")
        elif rsi_val < 30:
            signals.append("rsi_asiri_satim")

    # MACD sinyali
    macd_val = macd(prices)
    if macd_val and macd_val["crossover"] != "neutral":
        signals.append("macd_" + macd_val["crossover"])

    # Son 5 gün trend
    recent = prices[-5:]
    if len(recent) >= 5:
        changes = sum(1 for i in range(1, len(recent)) if recent[i] > recent[i - 1])
        if changes >= 4:
            signals.append("son_5g_yukselis")
        elif changes <= 1:
            signals.append("son_5g_dusus")

    # Destek/direnç (basit: son 20 gün min/max)
    support = min(prices[-20:]) if len(prices) >= 20 else min(prices)
    resistance = max(prices[-20:]) if len(prices) >= 20 else max(prices)
    distance_to_resistance = ((resistance - price) / price) * 100 if resistance > price else 0
    distance_to_support = ((price - support) / price) * 100 if support < price else 0

    # Tahmin
    forecast = linear_regression_forecast(prices)
    bb = bollinger_bands(prices)

    # Skor (basit puanlama)
    score = 50  # nötr
    if rsi_val is not None:
        if rsi_val < 30:
            score += 15
        elif rsi_val > 70:
            score -= 15
    if strength > 0:
        score += 10 * strength
    elif strength < 0:
        score -= 10 * abs(strength)
    if forecast and forecast["direction"] == "up":
        score += 5
    elif forecast and forecast["direction"] == "down":
        score -= 5
    score = max(0, min(100, score))

    return {
        "trend": trend,
        "strength": strength,
        "score": score,
        "signals": signals,
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "distance_to_resistance": round(distance_to_resistance, 2),
        "distance_to_support": round(distance_to_support, 2),
        "rsi_signal": "aşırı alım" if (rsi_val or 0) > 70 else ("aşırı satım" if (rsi_val or 0) < 30 else "nötr"),
        "forecast": forecast,
        "bollinger": bb,
    }


def calculate_all(prices: list[float], current_price: Optional[float] = None) -> dict:
    """Hesapla tüm indikatörleri ve sonuçları döndür."""
    if not prices or len(prices) < 2:
        return {"error": "Yeterli veri yok (en az 2 gün gerekli)"}

    price = current_price or prices[-1]

    rsi_val = rsi(prices)
    macd_val = macd(prices)

    return {
        "current_price": price,
        "data_points": len(prices),
        "rsi": {"value": round(rsi_val, 2)} if rsi_val is not None else None,
        "macd": {
            "macd": round(macd_val["macd"], 4),
            "signal": round(macd_val["signal"], 4),
            "histogram": round(macd_val["histogram"], 4),
            "crossover": macd_val["crossover"],
        } if macd_val else None,
        "moving_averages": {
            "sma_20": round(sma(prices, 20), 2) if sma(prices, 20) else None,
            "sma_50": round(sma(prices, 50), 2) if sma(prices, 50) else None,
            "sma_200": round(sma(prices, 200), 2) if sma(prices, 200) else None,
            "ema_12": round(ema(prices, 12), 2) if ema(prices, 12) else None,
            "ema_26": round(ema(prices, 26), 2) if ema(prices, 26) else None,
        },
    }
