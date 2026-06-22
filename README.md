# BIST Alarm Botu

Bu proje BIST hisseleri icin alarm kurup, sart saglandiginda Telegram bildirimi gondermek icin baslatildi.

> Onemli: Bu uygulama yatirim tavsiyesi vermez. Sadece senin girdigin fiyat/kurallara gore bildirim gonderir.

## Mevcut Ozellikler

- Telegram bildirimi gonderir.
- BIST hisse listesini arayuzde gosterir.
- Hisse secip anlik fiyat kontrolu yapar.
- Alarm ekler:
  - Fiyat hedefin ustune cikarsa
  - Fiyat hedefin altina duserse
- Hedefe yaklasinca erken uyari gonderir.
- Alarm notu eklenebilir: "nerede, ne icin takip ediyorum" gibi.

## Dosyalar

- `app.py`  
  Web arayuzu. Hisse secme ve alarm ekleme ekrani.

- `alarm_worker.py`  
  Arka planda calisan takip botu. Alarmlari kontrol eder ve Telegram'a bildirir.

- `bist_data.py`  
  BIST hisse listesini okur ve fiyat bilgisini ceker.

- `alerts.py`  
  Alarm kaydetme, silme ve kontrol mantigi.

- `telegram_notifier.py`  
  Telegram mesaj gonderme modulu.

- `data/bist_symbols.csv`  
  BIST hisse listesi.

- `data/alerts.json`  
  Eklenen alarmlar burada tutulur. Ilk alarm eklenince olusur.

- `.env`  
  Telegram bot token ve chat id bilgileri.

## Kurulum

Terminalde proje klasorunde calistir:

```bash
python -m pip install -r requirements.txt
```

## Telegram Ayarlari

`.env` dosyasi su sekilde olmali:

```env
TELEGRAM_BOT_TOKEN=bot_token
TELEGRAM_CHAT_ID=chat_id
```

Test icin:

```bash
python main.py
```

Telegram'a test mesaji gelirse bildirim sistemi calisiyor demektir.

## Arayuzu Calistirma

Bir terminal ac:

```bash
python app.py
```

Sonra tarayicida ac:

```text
http://127.0.0.1:5000
```

Buradan:

1. Hisse sececeksin.
2. Hedef fiyat gireceksin.
3. Ustune cikarsa mi altina duserse mi sececeksin.
4. Yaklasma araligi gireceksin. Ornek: `%1`
5. Not yazacaksin. Ornek: `direnc bolgesi`, `destek kirilimi`, `satis icin takip`.
6. Alarmi ekleyeceksin.

## Alarm Takip Botunu Calistirma

Arayuzden alarm ekledikten sonra ikinci bir terminal ac:

```bash
python alarm_worker.py
```

Bu bot 60 saniyede bir alarmlari kontrol eder.

### Bildirimler

Hedefe yaklasinca:

```text
⚠️ BIST hedefe yaklaştı
Hisse: THYAO
Anlık fiyat: 315.20
Hedef: 318.00
Yaklaşma aralığı: %1
Not: direnç bölgesi
```

Hedef gelince:

```text
🚨 BIST ALARM GELDİ
Hisse: THYAO
Anlık fiyat: 318.10
Hedef: 318.00
Not: satış için takip
```

Hedef alarmi geldiginde alarm otomatik pasife alinir.

## Sonraki Gelistirme Adimlari

1. Mobil uygulama arayuzu yapilacak.
2. BIST fiyat kaynagi daha profesyonel hale getirilecek.
3. RSI, MACD, hareketli ortalama gibi indikatorler eklenecek.
4. Alarm kurallari genisletilecek:
   - Yuzde artis/dusus
   - Hacim artisi
   - Destek/direnc kirilimi
   - Indikator kesişimleri
5. Uygulama Android APK olarak paketlenecek.
