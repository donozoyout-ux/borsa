import time
from datetime import datetime

from alerts import is_hit, is_near, load_alerts, set_alert_flags
from bist_data import PriceFetchError, get_bist_price
from telegram_notifier import send_telegram_message

CHECK_INTERVAL_SECONDS = 60


def format_condition(condition: str) -> str:
    return "üstüne çıkarsa" if condition == "above" else "altına düşerse"


def check_alerts_once() -> None:
    alerts = load_alerts()
    active_alerts = [a for a in alerts if a.get("active", True)]

    if not active_alerts:
        print("Aktif alarm yok.")
        return

    for alert in active_alerts:
        symbol = alert["symbol"]
        target = float(alert["target_price"])
        condition = alert["condition"]
        near_percent = float(alert.get("near_percent", 0))
        note = alert.get("note", "")

        try:
            price = get_bist_price(symbol)
        except PriceFetchError as exc:
            print(exc)
            continue

        if price is None:
            print(f"{symbol} fiyat bulunamadi.")
            continue

        print(f"{datetime.now().strftime('%H:%M:%S')} {symbol}: {price} | hedef: {target}")

        if is_hit(price, target, condition):
            if not alert.get("hit_sent", False):
                message = (
                    f"🚨 <b>BIST ALARM GELDİ</b>\n"
                    f"Hisse: <b>{symbol}</b>\n"
                    f"Anlık fiyat: <b>{price}</b>\n"
                    f"Hedef: <b>{target}</b> ({format_condition(condition)})\n"
                    f"Not: {note or '-'}"
                )
                send_telegram_message(message)
                set_alert_flags(alert["id"], hit_sent=True, active=False)
            continue

        if near_percent > 0 and is_near(price, target, near_percent):
            if not alert.get("near_sent", False):
                message = (
                    f"⚠️ <b>BIST hedefe yaklaştı</b>\n"
                    f"Hisse: <b>{symbol}</b>\n"
                    f"Anlık fiyat: <b>{price}</b>\n"
                    f"Hedef: <b>{target}</b>\n"
                    f"Yaklaşma aralığı: %{near_percent}\n"
                    f"Not: {note or '-'}"
                )
                send_telegram_message(message)
                set_alert_flags(alert["id"], near_sent=True)


def run_forever() -> None:
    send_telegram_message("✅ BIST alarm takip botu başlatıldı.")
    while True:
        check_alerts_once()
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_forever()
