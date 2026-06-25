import os
import requests
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_telegram_message(message: str) -> bool:
    """Telegram'a mesaj gonderir."""
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN bulunamadi. .env dosyasini veya Render Environment Variables'i kontrol et.")

    if not TELEGRAM_CHAT_ID:
        raise ValueError("TELEGRAM_CHAT_ID bulunamadi. .env dosyasini veya Render Environment Variables'i kontrol et.")

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }

    try:
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        data = response.json()
        return bool(data.get("ok"))
    except requests.exceptions.Timeout:
        raise ValueError("Telegram API zaman asimi. Internet baglantinizi kontrol edin.")
    except requests.exceptions.ConnectionError:
        raise ValueError("Telegram API'ye baglanamiyor. Internet baglantinizi kontrol edin.")
    except Exception as e:
        raise ValueError(f"Telegram hatasi: {str(e)}")


def send_signal_notification(message: str, signal_id: str) -> bool:
    """Trading sinyali bildirimi gonderir."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }

    try:
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        return True
    except Exception:
        return False


if __name__ == "__main__":
    try:
        send_telegram_message("✅ Borsa takip botu Telegram bildirimi calisiyor!")
        print("Telegram test mesaji gonderildi.")
    except Exception as e:
        print(f"HATA: {e}")
