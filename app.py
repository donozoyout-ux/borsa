import os
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from alerts import create_alert, delete_alert, load_alerts, set_alert_flags
from portfolio import add_item as pf_add, delete_item as pf_delete, load_portfolio
from bist_data import (
    PriceFetchError,
    get_all_cached_prices,
    get_bist_price,
    get_historical_prices,
    get_price_history_chart,
    load_bist_symbols,
    refresh_all_prices,
    _load_file_cache,
)
from indicators import calculate_all, analyze_trend
from ai_analysis import get_ai_analysis, get_multi_ai_analysis, analyze_image
from news import get_stock_news, get_fundamentals, parse_fundamentals

app = Flask(__name__)

_bot_running = False
_bot_logs: list[str] = []
_bot_stop_event = threading.Event()
_MAX_LOGS = 50
_bot_auto_started = False

LOGS_FILE = Path(__file__).resolve().parent / "data" / "bot_logs.json"


def _ensure_bot_started():
    """Botu bir kez otomatik baslat (gunicorn icin)."""
    global _bot_auto_started
    if _bot_auto_started:
        return
    _bot_auto_started = True
    _load_logs()
    _auto_start_bot()


def _add_log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    _bot_logs.append(f'<span class="time">{ts}</span> {msg}')
    if len(_bot_logs) > _MAX_LOGS:
        _bot_logs.pop(0)


def _save_logs() -> None:
    try:
        LOGS_FILE.parent.mkdir(exist_ok=True)
        LOGS_FILE.write_text(json.dumps(_bot_logs, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _load_logs() -> None:
    global _bot_logs
    try:
        if LOGS_FILE.exists():
            _bot_logs = json.loads(LOGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        _bot_logs = []


def _bot_worker() -> None:
    global _bot_running
    _bot_running = True
    _add_log('Blarm botu başlatıldı.')
    _save_logs()

    while not _bot_stop_event.is_set():
        alerts = load_alerts()
        active = [a for a in alerts if a.get("active", True)]

        if active:
            for alert in active:
                if _bot_stop_event.is_set():
                    break
                symbol = alert["symbol"]
                target = float(alert["target_price"])
                condition = alert["condition"]
                near_percent = float(alert.get("near_percent", 0))
                note = alert.get("note", "")
                try:
                    price = get_bist_price(symbol)
                except PriceFetchError as exc:
                    _add_log(f'<span class="sym">{symbol}</span> hata: {exc}')
                    continue
                if price is None:
                    continue
                _add_log(f'<span class="sym">{symbol}</span> <span class="price">{price}</span> hedef: {target}')

                if condition == "above" and price >= target and not alert.get("hit_sent", False):
                    from telegram_notifier import send_telegram_message
                    try:
                        send_telegram_message(f"🚨 <b>BIST ALARM GELDİ</b>\nHisse: <b>{symbol}</b>\nAnlık fiyat: <b>{price}</b>\nHedef: <b>{target}</b> (üstüne çıktı)\nNot: {note or '-'}")
                    except Exception:
                        pass
                    set_alert_flags(alert["id"], hit_sent=True, active=False)
                    _add_log(f'ALARM <span class="sym">{symbol}</span> {price} hedef {target} üstüne çıktı')
                elif condition == "below" and price <= target and not alert.get("hit_sent", False):
                    from telegram_notifier import send_telegram_message
                    try:
                        send_telegram_message(f"🚨 <b>BIST ALARM GELDİ</b>\nHisse: <b>{symbol}</b>\nAnlık fiyat: <b>{price}</b>\nHedef: <b>{target}</b> (altına düştü)\nNot: {note or '-'}")
                    except Exception:
                        pass
                    set_alert_flags(alert["id"], hit_sent=True, active=False)
                    _add_log(f'ALARM <span class="sym">{symbol}</span> {price} hedef {target} altına düştü')

                if near_percent > 0 and not alert.get("near_sent", False) and target > 0:
                    diff = abs(price - target) / target * 100
                    if diff <= near_percent:
                        from telegram_notifier import send_telegram_message
                        try:
                            send_telegram_message(f"⚠️ <b>BIST hedefe yaklaştı</b>\nHisse: <b>{symbol}</b>\nAnlık fiyat: <b>{price}</b>\nHedef: <b>{target}</b>\nNot: {note or '-'}")
                        except Exception:
                            pass
                        set_alert_flags(alert["id"], near_sent=True)
                        _add_log(f'HEDEFE YAKLAŞTI <span class="sym">{symbol}</span> {price}')
        else:
            _add_log('Aktif alarm yok, bekleniyor...')

        _save_logs()
        _bot_stop_event.wait(timeout=60)

    _bot_running = False
    _add_log('Bot durduruldu.')
    _save_logs()


@app.route("/")
def index():
    _ensure_bot_started()
    return render_template("index.html", symbols=load_bist_symbols())


@app.route("/api/alerts", methods=["GET"])
def api_alerts_list():
    return jsonify(load_alerts())


@app.route("/api/alerts", methods=["POST"])
def api_alerts_create():
    data = request.get_json(silent=True) or {}
    symbol = (data.get("symbol") or "").strip().upper()
    target = data.get("target_price")
    condition = data.get("condition", "above")
    near = data.get("near_percent", "1")
    note = data.get("note", "")
    if not symbol or not target:
        return jsonify({"ok": False, "error": "Symbol ve hedef fiyat gerekli"}), 400
    try:
        create_alert(symbol=symbol, target_price=float(str(target).replace(",", ".")), condition=condition, near_percent=float(str(near).replace(",", ".")), note=note)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True})


@app.route("/api/alerts/<alert_id>", methods=["DELETE"])
def api_alerts_delete(alert_id):
    delete_alert(alert_id)
    return jsonify({"ok": True})


@app.route("/api/price/<symbol>")
def api_price(symbol):
    try:
        price = get_bist_price(symbol)
        if price is not None:
            return jsonify({"symbol": symbol.upper(), "price": price, "source": "Yahoo Finance"})
        return jsonify({"error": "Fiyat bulunamadı"}), 404
    except PriceFetchError as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/api/prices/all")
def api_prices_all():
    prices, cache_time = get_all_cached_prices()
    age = int(time.time() - cache_time) if cache_time else -1
    results = [{"symbol": s, "price": p} for s, p in prices.items() if p is not None]
    return jsonify({"prices": results, "count": len(results), "cache_age": age})


@app.route("/api/chart/<symbol>")
def api_chart(symbol):
    range_str = request.args.get("range", "1mo")
    interval = request.args.get("interval", "1d")
    data = get_price_history_chart(symbol, range_str, interval)
    if data:
        return jsonify(data)
    return jsonify({"error": "Grafik verisi alınamadı"}), 502


@app.route("/api/indicators/<symbol>")
def api_indicators(symbol):
    hist = get_historical_prices(symbol, range_str="3mo", interval="1d")
    if not hist:
        hist = get_historical_prices(symbol, range_str="1mo", interval="1d")
    if not hist:
        return jsonify({"error": f"{symbol} için geçmiş veri alınamadı"}), 502
    try:
        result = calculate_all(hist)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/analysis/<symbol>")
def api_analysis(symbol):
    clean = symbol.upper().strip().replace(".IS", "")
    hist = get_historical_prices(clean, range_str="6mo", interval="1d")
    if not hist:
        hist = get_historical_prices(clean, range_str="3mo", interval="1d")
    if not hist:
        return jsonify({"error": f"{symbol} için veri alınamadı"}), 502
    try:
        indicators_result = calculate_all(hist)
        trend_result = analyze_trend(hist)
        current_price = indicators_result.get("current_price")
        news = get_stock_news(clean, 5)
        raw_fund = get_fundamentals(clean)
        fund = parse_fundamentals(raw_fund) if raw_fund else {"has_data": False}
        ai_text = get_ai_analysis(clean, current_price, indicators_result, trend_result, fund, news)
        return jsonify({
            "symbol": clean,
            "indicators": indicators_result,
            "trend": trend_result,
            "news": news,
            "fundamentals": fund,
            "ai_analysis": ai_text,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/ai/analyze-image", methods=["POST"])
def api_ai_analyze_image():
    data = request.get_json(silent=True) or {}
    image_base64 = data.get("image", "")
    symbol = (data.get("symbol") or "").strip().upper().replace(".IS", "")
    if not image_base64:
        return jsonify({"error": "Görsel verisi gerekli"}), 400
    price = None
    if symbol:
        try:
            from bist_data import get_bist_price
            price = get_bist_price(symbol)
        except Exception:
            pass
    try:
        result = analyze_image(image_base64, symbol, price)
        if result:
            return jsonify({"ok": True, "analysis": result})
        return jsonify({"error": "Görsel analizi için GEMINI_API_KEY gerekli. .env dosyasına ekleyin."}), 502
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/news/<symbol>")
def api_news(symbol):
    clean = symbol.upper().strip().replace(".IS", "")
    news = get_stock_news(clean, 10)
    return jsonify(news)


@app.route("/api/analysis/<symbol>/multi")
def api_analysis_multi(symbol):
    clean = symbol.upper().strip().replace(".IS", "")
    hist = get_historical_prices(clean, range_str="6mo", interval="1d")
    if not hist:
        hist = get_historical_prices(clean, range_str="3mo", interval="1d")
    if not hist:
        return jsonify({"error": f"{symbol} icin veri alinamadi"}), 502
    try:
        indicators_result = calculate_all(hist)
        trend_result = analyze_trend(hist)
        current_price = indicators_result.get("current_price")
        news = get_stock_news(clean, 5)
        raw_fund = get_fundamentals(clean)
        fund = parse_fundamentals(raw_fund) if raw_fund else {"has_data": False}
        result = get_multi_ai_analysis(clean, current_price, indicators_result, trend_result, fund, news)
        return jsonify({
            "symbol": clean,
            "indicators": indicators_result,
            "trend": trend_result,
            "news": news,
            "fundamentals": fund,
            **result,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/fundamentals/<symbol>")
def api_fundamentals(symbol):
    clean = symbol.upper().strip().replace(".IS", "")
    raw = get_fundamentals(clean)
    if not raw:
        return jsonify({"error": "Fundamentals verisi alınamadı"}), 502
    fund = parse_fundamentals(raw)
    return jsonify(fund)


@app.route("/api/price-chart/<symbol>")
def api_price_chart(symbol):
    range_str = request.args.get("range", "1mo")
    interval = request.args.get("interval", "1d")
    chart = get_price_history_chart(symbol, range_str, interval)
    price = None
    try:
        price = get_bist_price(symbol)
    except Exception:
        pass
    return jsonify({"symbol": symbol.upper(), "current_price": price, "chart": chart.get("prices", []) if chart else []})


@app.route("/api/portfolio", methods=["GET"])
def api_portfolio_list():
    return jsonify(load_portfolio())


@app.route("/api/portfolio", methods=["POST"])
def api_portfolio_add():
    data = request.get_json(silent=True) or {}
    symbol = (data.get("symbol") or "").strip().upper()
    quantity = data.get("quantity")
    avg_cost = data.get("avg_cost")
    note = data.get("note", "")
    if not symbol or not quantity or not avg_cost:
        return jsonify({"ok": False, "error": "Sembol, adet ve maliyet gerekli"}), 400
    try:
        item = pf_add(symbol=symbol, quantity=float(quantity), avg_cost=float(str(avg_cost).replace(",", ".")), note=note)
        return jsonify({"ok": True, "item": item})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/portfolio/<item_id>", methods=["DELETE"])
def api_portfolio_delete(item_id):
    pf_delete(item_id)
    return jsonify({"ok": True})


@app.route("/api/portfolio/summary")
def api_portfolio_summary():
    items = load_portfolio()
    if not items:
        return jsonify({"total_cost": 0, "total_value": 0, "profit_loss": 0, "change_pct": 0, "items": []})
    from bist_data import get_bist_price, PriceFetchError
    total_cost = 0
    total_value = 0
    results = []
    for item in items:
        sym = item["symbol"]
        qty = float(item["quantity"])
        cost = float(item.get("avg_cost") or 0)
        total_cost += qty * cost if cost else 0
        try:
            price = get_bist_price(sym)
        except PriceFetchError:
            price = None
        if price:
            val = qty * price
            total_value += val
            pl = (price - cost) * qty if cost else 0
            pl_pct = (price - cost) / cost * 100 if cost else 0
        else:
            val = 0
            pl = 0
            pl_pct = 0
        results.append({
            "id": item["id"],
            "symbol": sym,
            "quantity": qty,
            "avg_cost": cost if cost else None,
            "current_price": price,
            "value": round(val, 2),
            "profit_loss": round(pl, 2) if cost else 0,
            "profit_loss_pct": round(pl_pct, 2) if cost else 0,
            "note": item.get("note", ""),
        })
    change_pct = round((total_value - total_cost) / total_cost * 100, 2) if total_cost else 0
    return jsonify({
        "total_cost": round(total_cost, 2),
        "total_value": round(total_value, 2),
        "profit_loss": round(total_value - total_cost, 2),
        "change_pct": change_pct,
        "items": results,
    })


@app.route("/api/portfolio/telegram", methods=["POST"])
def api_portfolio_telegram():
    try:
        from telegram_notifier import send_telegram_message
        items = load_portfolio()
        if not items:
            return jsonify({"ok": False, "error": "Portföy boş"}), 400
        from bist_data import get_bist_price, PriceFetchError
        total_cost = 0
        total_value = 0
        lines = ["<b>📊 PORTFÖY ÖZETİ</b>", ""]
        for item in items:
            sym = item["symbol"]
            qty = float(item["quantity"])
            cost = float(item["avg_cost"])
            total_cost += qty * cost
            try:
                price = get_bist_price(sym)
            except PriceFetchError:
                price = None
            if price:
                val = qty * price
                total_value += val
                pl = (price - cost) * qty
                pl_pct = (price - cost) / cost * 100
                emoji = "🟢" if pl >= 0 else "🔴"
                lines.append(f"{emoji} <b>{sym}</b>: {qty} ad × {cost} = {val:.2f} TL ({pl:+.2f} / %{pl_pct:+.2f})")
            else:
                lines.append(f"⚪ <b>{sym}</b>: {qty} ad × {cost} (fiyat alınamadı)")
        lines.append("")
        total_pl = total_value - total_cost
        total_pl_pct = (total_pl / total_cost * 100) if total_cost else 0
        emoji_total = "🟢" if total_pl >= 0 else "🔴"
        lines.append(f"{emoji_total} <b>Toplam</b>: Yatırım: {total_cost:.2f} TL → Güncel: {total_value:.2f} TL")
        lines.append(f"   Kar/Zarar: {total_pl:+.2f} TL (%{total_pl_pct:+.2f})")
        send_telegram_message("\n".join(lines))
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/bot/status")
def api_bot_status():
    return jsonify({"running": _bot_running})


@app.route("/api/bot/start", methods=["POST"])
def api_bot_start():
    global _bot_running
    if _bot_running:
        return jsonify({"running": True})
    _bot_stop_event.clear()
    _load_logs()
    t = threading.Thread(target=_bot_worker, daemon=True)
    t.start()
    return jsonify({"running": True})


@app.route("/api/bot/stop", methods=["POST"])
def api_bot_stop():
    global _bot_running
    if not _bot_running:
        return jsonify({"running": False})
    _bot_stop_event.set()
    return jsonify({"running": False})


@app.route("/api/bot/logs")
def api_bot_logs():
    _load_logs()
    return jsonify({"logs": _bot_logs[-50:]})


def _start_price_cache_refresher():
    _load_file_cache()
    def _run():
        while True:
            try:
                now = datetime.now()
                hour = now.hour
                minute = now.minute
                weekday = now.weekday()  # 0=Pazartesi, 6=Pazar
                market_open = (9 <= hour < 18) or (hour == 18 and minute < 15)
                is_weekday = weekday < 5
                if market_open and is_weekday:
                    refresh_all_prices()
                    time.sleep(300)  # Piyasa acikken 5 dk bekle
                else:
                    time.sleep(600)  # Piyasa kapalıyken 10 dk bekle
            except Exception:
                time.sleep(60)
    t = threading.Thread(target=_run, daemon=True)
    t.start()


@app.route("/api/hourly/<symbol>")
def api_hourly(symbol):
    """1 günlük saatlik veri (1d, 1h)"""
    clean = symbol.upper().strip().replace(".IS", "")
    try:
        chart = get_price_history_chart(clean, "1d", "1h")
        _price = None
        try:
            from bist_data import get_bist_price
            _price = get_bist_price(clean)
        except Exception:
            pass
        if chart and chart.get("prices"):
            return jsonify({
                "symbol": clean,
                "current_price": _price,
                "prices": chart["prices"]
            })
        return jsonify({"error": "Saatlik veri yok"}), 502
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/daily-featured")
def api_daily_featured():
    """Yukselen ve dusen hisseleri ayri ayri dondur"""
    try:
        symbols = load_bist_symbols()
        if not symbols:
            return jsonify({"error": "Sembol listesi bos"}), 500

        scored = []

        for s in symbols[:100]:
            sym = s["symbol"]
            try:
                chart = get_price_history_chart(sym, "5d", "1h")
                if not chart or not chart.get("prices") or len(chart["prices"]) < 10:
                    continue

                prices_data = chart["prices"]
                prices = [p["p"] for p in prices_data]
                volumes = [p.get("v", 0) for p in prices_data]

                open_price = prices[0]
                close_price = prices[-1]
                change_pct = (close_price - open_price) / open_price * 100

                avg_vol = sum(volumes) / len(volumes) if volumes else 0
                last_vol = volumes[-1] if volumes else 0
                vol_ratio = last_vol / avg_vol if avg_vol > 0 else 1

                recent = prices[-5:] if len(prices) >= 5 else prices
                momentum = (recent[-1] - recent[0]) / recent[0] * 100 if len(recent) > 1 else 0

                score = 0
                if change_pct > 0: score += 30
                if vol_ratio > 1.5: score += 25
                if momentum > 0: score += 25
                if vol_ratio > 1 and change_pct > 0: score += 20

                scored.append({
                    "symbol": sym,
                    "name": s["name"],
                    "price": close_price,
                    "change_pct": round(change_pct, 2),
                    "volume_ratio": round(vol_ratio, 2),
                    "momentum": round(momentum, 2),
                    "score": score
                })
            except Exception:
                continue

        risers = [x for x in scored if x["change_pct"] > 0]
        fallers = [x for x in scored if x["change_pct"] < 0]

        risers.sort(key=lambda x: x["score"], reverse=True)
        fallers.sort(key=lambda x: x["score"], reverse=True)

        risers = risers[:8]
        fallers = fallers[:8]

        return jsonify({
            "risers": risers,
            "fallers": fallers,
            "risers_count": len(risers),
            "fallers_count": len(fallers),
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/key-stocks-daily")
def api_key_stocks_daily():
    """Portföy + izleme listesi hisselerinin günlük değişimleri"""
    try:
        portfolio = load_portfolio()
        alerts = load_alerts()
        all_symbols = set()
        
        for item in portfolio:
            all_symbols.add(item["symbol"])
        for a in alerts:
            if a.get("active", True):
                all_symbols.add(a["symbol"])
        
        if not all_symbols:
            return jsonify({"stocks": []})
        
        results = []
        for sym in list(all_symbols)[:20]:
            try:
                chart = get_price_history_chart(sym, "5d", "1d")
                if not chart or not chart.get("prices") or len(chart["prices"]) < 2:
                    continue
                prices_data = chart["prices"]
                open_price = prices_data[0]["p"]
                close_price = prices_data[-1]["p"]
                change_pct = (close_price - open_price) / open_price * 100
                
                in_pf = any(i["symbol"] == sym for i in portfolio)
                in_alert = any(a["symbol"] == sym for a in alerts if a.get("active", True))
                
                results.append({
                    "symbol": sym,
                    "price": round(close_price, 2),
                    "change_pct": round(change_pct, 2),
                    "in_portfolio": in_pf,
                    "in_alerts": in_alert
                })
            except Exception:
                continue
        
        # Portföy hisseleri önce, sonra alarm hisseleri, sonra değişime göre
        results.sort(key=lambda x: (not x["in_portfolio"], not x["in_alerts"], -x["change_pct"]))
        
        return jsonify({"stocks": results})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/settings/telegram-status")
def api_settings_telegram_status():
    from telegram_notifier import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    return jsonify({
        "token_set": bool(TELEGRAM_BOT_TOKEN),
        "chat_id_set": bool(TELEGRAM_CHAT_ID),
        "token_preview": (TELEGRAM_BOT_TOKEN[:8] + "..." + TELEGRAM_BOT_TOKEN[-4:]) if TELEGRAM_BOT_TOKEN else "",
        "chat_id": TELEGRAM_CHAT_ID or "",
    })


@app.route("/api/settings/check-env")
def api_settings_check_env():
    return jsonify({
        "TELEGRAM_BOT_TOKEN": bool(os.getenv("TELEGRAM_BOT_TOKEN")),
        "TELEGRAM_CHAT_ID": bool(os.getenv("TELEGRAM_CHAT_ID")),
        "GROQ_API_KEY": bool(os.getenv("GROQ_API_KEY")),
        "GEMINI_API_KEY": bool(os.getenv("GEMINI_API_KEY")),
    })


@app.route("/api/settings/test-telegram", methods=["POST"])
def api_settings_test_telegram():
    try:
        from telegram_notifier import send_telegram_message
        send_telegram_message("🧪 <b>Test Mesaji</b>\nBIST Terminal Telegram baglantisi basarili!")
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


def _auto_start_bot():
    """Render gibi ortamlarda botu otomatik baslatir."""
    global _bot_running
    if _bot_running:
        return
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_chat = os.getenv("TELEGRAM_CHAT_ID")
    if telegram_token and telegram_chat:
        _add_log('Telegram ayarlari bulundu, bot otomatik baslatiliyor...')
        _save_logs()
        _bot_stop_event.clear()
        t = threading.Thread(target=_bot_worker, daemon=True)
        t.start()
    else:
        _add_log('Telegram ayarlari bulunamadi! .env veya Render Environment Variables ayarlayin.')
        _save_logs()


if __name__ == "__main__":
    _load_logs()
    _start_price_cache_refresher()
    _ensure_bot_started()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, threaded=True, debug=False)
