from telegram_notifier import send_telegram_message


def main():
    # Simdilik ilk hedef: Telegram bildiriminin calismasini test etmek.
    # Sonraki adimda buraya fiyat takip / indikator kontrol sistemi eklenecek.
    mesaj = "🚀 Bot basladi. Ilk test bildirimi basarili."
    send_telegram_message(mesaj)
    print("Test bildirimi gonderildi.")


if __name__ == "__main__":
    main()
