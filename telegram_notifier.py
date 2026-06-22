import os
import requests
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_telegram_message(message: str) -> bool:
    """Telegram'a mesaj gonderir."""
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN bulunamadi. .env dosyasini kontrol et.")

    if not TELEGRAM_CHAT_ID:
        raise ValueError("TELEGRAM_CHAT_ID bulunamadi. .env dosyasini kontrol et.")

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }

    response = requests.post(url, json=payload, timeout=15)
    response.raise_for_status()
    data = response.json()
    return bool(data.get("ok"))


if __name__ == "__main__":
    send_telegram_message("✅ Borsa takip botu Telegram bildirimi calisiyor!")
    print("Telegram test mesaji gonderildi.")
