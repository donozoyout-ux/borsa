import base64
import os
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def get_ai_analysis(
    symbol: str,
    price: float,
    indicators: dict,
    trend: dict,
    fundamentals: Optional[dict] = None,
    news: Optional[list[dict]] = None,
) -> Optional[str]:
    if not GROQ_API_KEY:
        return None

    ma = (indicators.get("moving_averages") or {}) if indicators else {}
    rsi_val = (indicators.get("rsi") or {}).get("value") if indicators else None
    macd_data = (indicators.get("macd") or {}) if indicators else {}
    bb = (trend.get("bollinger") or {}) if trend else {}
    forecast = (trend.get("forecast") or {}) if trend else {}
    signals = (trend.get("signals") or []) if trend else {}

    fin = (fundamentals or {}).get("ratios", {}) if fundamentals else {}
    bs = (fundamentals or {}).get("balance_sheet", {}) if fundamentals else {}

    system_prompt = """Sen profesyonel bir BIST hisse senedi analistisin. Görevin kapsamlı teknik + temel analiz yapıp yatırımcıya net yönlendirme vermek.

Analizini şu formatta yap (Türkçe, max 6 satır):

📊 TEKNİK ANALİZ:
- Trend: [yükseliş/düşüş/nötr] · RSI: [değer] · MACD: [sinyal]
- Destek/Direnç: [seviyeler]
- Tahmin (5gün): [yön ve yüzde]

📋 TEMEL ANALİZ:
- F/K: [değer] · PD/DD: [değer] · Beta: [değer]
- Bilanço: [varsa yorum]
- [varsa haber etkisi]

🎯 YÖNLENDİRME:
- Kısa vade (1-5 gün): [AL/TUT/SAT] · [gerekçe]
- Orta vade (1-3 ay): [AL/TUT/SAT] · [gerekçe]
- Risk seviyesi: [düşük/orta/yüksek]
- Stop-loss: [TL] · Hedef: [TL]

Önemli: Sadece verilen verilere göre yorum yap. Kesin AL/SAT tavsiyesi değil, yatırımcıya yol gösterici analiz sun."""

    prompt_parts = [f"Hisse: {symbol.upper()}, Fiyat: {price} TL, Veri: {indicators.get('data_points', 'N/A')} gün"]

    prompt_parts.append(f"""
TEKNİK GÖSTERGELER:
- RSI(14): {rsi_val or 'N/A'}
- MACD: {macd_data.get('macd', 'N/A')} / Sinyal: {macd_data.get('signal', 'N/A')} / Histogram: {macd_data.get('histogram', 'N/A')} / Kesişim: {macd_data.get('crossover', 'N/A')}
- SMA 20: {ma.get('sma_20', 'N/A')} / SMA 50: {ma.get('sma_50', 'N/A')} / SMA 200: {ma.get('sma_200', 'N/A')}
- EMA 12: {ma.get('ema_12', 'N/A')} / EMA 26: {ma.get('ema_26', 'N/A')}
- Bollinger: Üst {bb.get('upper', 'N/A')} / Orta {bb.get('middle', 'N/A')} / Alt {bb.get('lower', 'N/A')} / Fiyat: {bb.get('position', 'N/A')} bantta
- Destek: {trend.get('support', 'N/A')} / Direnç: {trend.get('resistance', 'N/A')}
- Sinyaller: {', '.join(signals) if signals else 'Yok'}
- Trend: {trend.get('trend', 'N/A')} / Güç: {trend.get('strength', 'N/A')}
- Tahmin 5gün: {forecast.get('predictions', 'N/A')} / Değişim: %{forecast.get('change_pct', 'N/A')}
- Skor: {trend.get('score', 'N/A')}/100""")

    if fundamentals and fundamentals.get("has_data"):
        prompt_parts.append(f"""
TEMEL ANALİZ:
- Piyasa Değeri: {fin.get('market_cap', 'N/A')}
- F/K (PE): {fin.get('pe_ratio', 'N/A')} / PD/DD: {fin.get('pb_ratio', 'N/A')}
- EPS: {fin.get('eps', 'N/A')} / Beta: {fin.get('beta', 'N/A')}
- Temettü: %{fin.get('dividend_yield', 'N/A')}
- Kar Marjı: %{fin.get('profit_margins', 'N/A')}
- Borç/Öz Kaynak: {fin.get('debt_to_equity', 'N/A')}
- ROE: %{fin.get('roe', 'N/A')}
- 52 Hafta: Yüksek {fin.get('52w_high', 'N/A')} / Düşük {fin.get('52w_low', 'N/A')}
- Ciros: {fin.get('revenue', 'N/A')}
- Nakit: {bs.get('cash', 'N/A')} / Toplam Borç: {bs.get('total_debt', 'N/A')} / Toplam Varlık: {bs.get('total_assets', 'N/A')}""")

    if news:
        news_text = "\n".join([f"- {n['title']}" for n in news[:5]])
        prompt_parts.append(f"\nGÜNCEL HABERLER:\n{news_text}")

    try:
        resp = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "\n".join(prompt_parts)},
                ],
                "temperature": 0.2,
                "max_tokens": 600,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


def analyze_image(image_base64: str, symbol: str = "", price: Optional[float] = None) -> Optional[str]:
    """Gemini ile görsel analizi. Sadece Part.from_bytes() kullanır, upload fallback yok."""
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        return None

    text_prompt = f"""Bu grafiği/görseli analiz et ve yorumla.
{'Hisse: ' + symbol if symbol else ''}
{'Güncel Fiyat: ' + str(price) + ' TL' if price else ''}

Şu başlıklarla analiz yap (Türkçe, max 6 satır):
GORSEL YORUMU:
- Gördüğün trend, formasyon, destek/direnç seviyeleri

YONLENDIRME:
- Kisa vade: [AL/TUT/SAT]
- Risk uyarisi varsa belirt"""

    try:
        from google import genai as genai_sdk
        from google.genai import types
        client = genai_sdk.Client(api_key=GEMINI_API_KEY)
        image_data = base64.b64decode(image_base64)
        mime = "image/png"
        if image_base64.startswith("/9j/"):
            mime = "image/jpeg"
        elif image_base64.startswith("UklGR"):
            mime = "image/webp"

        # Sadece gemini-2.5-flash dene; image modelleri mevcut olmayabilir
        try:
            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[text_prompt, types.Part.from_bytes(data=image_data, mime_type=mime)],
            )
            if resp.text:
                return resp.text.strip()
        except Exception:
            pass

        # İkinci deneme: alternatif model
        try:
            resp = client.models.generate_content(
                model="gemini-3.1-flash-image",
                contents=[text_prompt, types.Part.from_bytes(data=image_data, mime_type=mime)],
            )
            if resp.text:
                return resp.text.strip()
        except Exception:
            pass

        return None
    except Exception:
        return None
