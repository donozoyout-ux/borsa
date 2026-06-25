import base64
import os
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Kullanilabilir Groq modelleri (sira oncelikli)
GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
]


def _call_groq(messages: list[dict], model: str, max_tokens: int = 600, temperature: float = 0.2) -> Optional[str]:
    if not GROQ_API_KEY:
        return None
    try:
        resp = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


def _build_analysis_prompt(
    symbol: str,
    price: float,
    indicators: dict,
    trend: dict,
    fundamentals: Optional[dict] = None,
    news: Optional[list[dict]] = None,
) -> tuple[str, str]:
    """System prompt ve user prompt olustur."""
    system_prompt = """Sen profesyonel bir BIST hisse senedi analistisin. Kapsamli teknik + temel analiz yap ve yatirimciya net yonlendirme ver.

Analizini su formatta yap Turkce max 8 satir:

TEKNIK ANALIZ:
- Trend: [yukselis/dusus/notr] RSI: [deger] MACD: [sinyal]
- Destek/Direnc: [seviyeler]
- Tahmin (5gun): [yon ve yuzde]

TEMEL ANALIZ:
- Sunulan temel verileri kullan: 52 hafta araligi, 50/200 gunluk ortalamalar, gunluk degisim, vb.
- Eger F/K PD/DD gibi geleneksel oranlar verilmemisse onlara deginme, sadece mevcut verilerle analiz yap
- Haber etkisi varsa ekle

YONLENDIRME:
- Kisa vade (1-5 gun): [AL/TUT/SAT] [gerekce]
- Orta vade (1-3 ay): [AL/TUT/SAT] [gerekce]
- Risk seviyesi: [dusuk/orta/yuksek]
- Stop-loss: [TL] Hedef: [TL]

Onemli: Veri yetersizligi deme, sunulan verileri kullanarak analiz yap. Kesin AL/SAT tavsiyesi degil yatirimciya yol gosterici analiz sun."""

    ma = (indicators.get("moving_averages") or {}) if indicators else {}
    rsi_val = (indicators.get("rsi") or {}).get("value") if indicators else None
    macd_data = (indicators.get("macd") or {}) if indicators else {}
    bb = (trend.get("bollinger") or {}) if trend else {}
    forecast = (trend.get("forecast") or {}) if trend else {}
    signals = (trend.get("signals") or []) if trend else {}
    fin = (fundamentals or {}).get("ratios", {}) if fundamentals else {}
    bs = (fundamentals or {}).get("balance_sheet", {}) if fundamentals else {}

    prompt_parts = [f"Hisse: {symbol.upper()}, Fiyat: {price} TL, Veri: {indicators.get('data_points', 'N/A')} gun"]

    prompt_parts.append(f"""
TEKNIK GOSTERGELER:
- RSI(14): {rsi_val or 'N/A'}
- MACD: {macd_data.get('macd', 'N/A')} / Sinyal: {macd_data.get('signal', 'N/A')} / Histogram: {macd_data.get('histogram', 'N/A')} / Kesim: {macd_data.get('crossover', 'N/A')}
- SMA 20: {ma.get('sma_20', 'N/A')} / SMA 50: {ma.get('sma_50', 'N/A')} / SMA 200: {ma.get('sma_200', 'N/A')}
- EMA 12: {ma.get('ema_12', 'N/A')} / EMA 26: {ma.get('ema_26', 'N/A')}
- Bollinger: Ust {bb.get('upper', 'N/A')} / Orta {bb.get('middle', 'N/A')} / Alt {bb.get('lower', 'N/A')} / Fiyat: {bb.get('position', 'N/A')} bantta
- Destek: {trend.get('support', 'N/A')} / Direnc: {trend.get('resistance', 'N/A')}
- Sinyaller: {', '.join(signals) if signals else 'Yok'}
- Trend: {trend.get('trend', 'N/A')} / Guc: {trend.get('strength', 'N/A')}
- Tahmin 5gun: {forecast.get('predictions', 'N/A')} / Degisim: %{forecast.get('change_pct', 'N/A')}
- Skor: {trend.get('score', 'N/A')}/100""")

    if fundamentals and fundamentals.get("has_data"):
        fund_lines = []
        if fin.get('market_cap'): fund_lines.append(f"Piyasa Degeri: {fin['market_cap']}")
        if fin.get('pe_ratio'): fund_lines.append(f"F/K (PE): {fin['pe_ratio']}")
        if fin.get('pb_ratio'): fund_lines.append(f"PD/DD: {fin['pb_ratio']}")
        if fin.get('eps'): fund_lines.append(f"EPS: {fin['eps']}")
        if fin.get('beta'): fund_lines.append(f"Beta: {fin['beta']}")
        if fin.get('dividend_yield'): fund_lines.append(f"Temettu: %{fin['dividend_yield']}")
        if fin.get('profit_margins'): fund_lines.append(f"Kar Marji: %{fin['profit_margins']}")
        if fin.get('debt_to_equity'): fund_lines.append(f"Borc/Oz Kaynak: {fin['debt_to_equity']}")
        if fin.get('roe'): fund_lines.append(f"ROE: %{fin['roe']}")
        if fin.get('revenue'): fund_lines.append(f"Ciros: {fin['revenue']}")
        if bs.get('cash'): fund_lines.append(f"Nakit: {bs['cash']}")
        if bs.get('total_debt'): fund_lines.append(f"Toplam Borc: {bs['total_debt']}")
        if bs.get('total_assets'): fund_lines.append(f"Toplam Varlik: {bs['total_assets']}")
        if fin.get('52w_high') or fin.get('52w_low'):
            fund_lines.append(f"52 Hafta: Yuksek {fin.get('52w_high', 'N/A')} / Dusuk {fin.get('52w_low', 'N/A')}")
        if fin.get('50d_avg'): fund_lines.append(f"50 Gunluk Ort: {fin['50d_avg']}")
        if fin.get('200d_avg'): fund_lines.append(f"200 Gunluk Ort: {fin['200d_avg']}")
        if fin.get('day_high'): fund_lines.append(f"Gunluk: Yuksek {fin['day_high']} / Dusuk {fin['day_low']}")
        if fin.get('prev_close'): fund_lines.append(f"Onceki Kapanis: {fin['prev_close']}")
        if fin.get('change_pct') is not None: fund_lines.append(f"Degisim: %{fin['change_pct']}")
        if fin.get('avg_volume'): fund_lines.append(f"Ort Hacim: {fin['avg_volume']}")
        if fund_lines:
            prompt_parts.append(f"\nTEMEL ANALIZ:\n" + "\n".join(f"- {l}" for l in fund_lines))

    if news:
        news_text = "\n".join([f"- {n['title']}" for n in news[:5]])
        prompt_parts.append(f"\nGUNCEL HABERLER:\n{news_text}")

    return system_prompt, "\n".join(prompt_parts)


def get_ai_analysis(
    symbol: str,
    price: float,
    indicators: dict,
    trend: dict,
    fundamentals: Optional[dict] = None,
    news: Optional[list[dict]] = None,
) -> Optional[str]:
    """Tek AI modeli ile analiz (eski uyumluluk icin)."""
    if not GROQ_API_KEY:
        return None

    system_prompt, user_prompt = _build_analysis_prompt(symbol, price, indicators, trend, fundamentals, news)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    for model in GROQ_MODELS:
        result = _call_groq(messages, model)
        if result:
            return result
    return None


def get_multi_ai_analysis(
    symbol: str,
    price: float,
    indicators: dict,
    trend: dict,
    fundamentals: Optional[dict] = None,
    news: Optional[list[dict]] = None,
) -> dict:
    """Birden fazla AI modeli ile analiz yap ve sonuclari dondur."""
    if not GROQ_API_KEY:
        return {"analyses": [], "consensus": None, "error": "GROQ_API_KEY ayarlanmamis"}

    system_prompt, user_prompt = _build_analysis_prompt(symbol, price, indicators, trend, fundamentals, news)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    analyses = []
    for model in GROQ_MODELS:
        result = _call_groq(messages, model, temperature=0.3)
        if result:
            analyses.append({"model": model.split("/")[0] if "/" in model else model, "analysis": result})

    if not analyses:
        return {"analyses": [], "consensus": None, "error": "AI analiz alinamadi"}

    # Konsensus olustur
    consensus = None
    if len(analyses) >= 2:
        consensus_prompt = f"""Asagidaki {len(analyses)} farkli AI modelinin hisse analizini karsilastir ve kisa bir konsensus olustur.

"""
        for i, a in enumerate(analyses):
            consensus_prompt += f"--- MODEL {i+1} ({a['model']}) ---\n{a['analysis']}\n\n"

        consensus_prompt += """Kisa bir konsensus yazi (max 5 satir):
- Tum modellerin ortak gorusu ne?
- Hangi model daha iyimser/karamsar?
- Nihai onerinin ne olmali? (AL/TUT/SAT)"""

        consensus_messages = [
            {"role": "system", "content": "Sen finansal analiz uzmanisin. Farkli AI modellerinin analizlerini karsilastirip kisa bir konsensus sun."},
            {"role": "user", "content": consensus_prompt},
        ]

        for model in GROQ_MODELS:
            result = _call_groq(consensus_messages, model, max_tokens=400, temperature=0.2)
            if result:
                consensus = result
                break

    return {"analyses": analyses, "consensus": consensus}


def analyze_image(image_base64: str, symbol: str = "", price: Optional[float] = None) -> Optional[str]:
    """Gemini ile gorsel analizi."""
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        return None

    text_prompt = f"""Bu grafigi/gorseli analiz et ve yorumla.
{'Hisse: ' + symbol if symbol else ''}
{'Guncel Fiyat: ' + str(price) + ' TL' if price else ''}

Su basliklarla analiz yap (Türkçe, max 6 satir):
GORSEL YORUMU:
- Gordugun trend, formasyon, destek/direnc seviyeleri

YONLENDIRME:
- Kisa vade: [AL/TUT/SAT]
- Risk uyariyi varsa belirt"""

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

        try:
            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[text_prompt, types.Part.from_bytes(data=image_data, mime_type=mime)],
            )
            if resp.text:
                return resp.text.strip()
        except Exception:
            pass

        try:
            resp = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[text_prompt, types.Part.from_bytes(data=image_data, mime_type=mime)],
            )
            if resp.text:
                return resp.text.strip()
        except Exception:
            pass

        return None
    except Exception:
        return None


def get_signal_prediction(
    symbol: str,
    price: float,
    direction: str,
    indicators: dict,
    trend: dict,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    fundamentals: Optional[dict] = None,
    news: Optional[list[dict]] = None,
) -> Optional[str]:
    """Trading sinyali icin detayli AI tahmini: neden, ne zaman, ne olacak."""
    if not GROQ_API_KEY:
        return None

    action = "ALIS" if direction == "BUY" else "SATIS"

    system_prompt = f"""Sen profesyonel bir BIST hisse senedi trading analistisin. Bir {action} sinyali icin detayli tahmin yapiyorsun.

COK ONEMLI: Turkce yaz, max 10 satir, su formatta cevap ver:

NEDEN BU SINYAL? (2-3 satir)
- Hangi gostergeler ne soyluyor? (RSI, MACD, Bollinger, MA)
- Neden bu yonde karar verildi?

FIYAT TAHMINI (2-3 satir)
- Kisa vade (1-3 gun): Hedef fiyat ve yuzde degisim
- Orta vade (1-2 hafta): Hedef fiyat ve yuzde degisim
- Olasilik: Yuksek/Orta/Dusuk

RISK ANALIZI (1-2 satir)
- Karsilasabilecek riskler
- Dikkat edilecek seviyeler

ZAMANLAMA (1-2 satir)
- Simdi mi girilmeli yoksa beklenmeli mi?
- En uygun giris zamanı ne zaman?

Kesinlikle "YATIRIM TAVSIYESI DEGIL" gibi uyarilar yazma. Dogrudan analiz yap."""

    ma = (indicators.get("moving_averages") or {}) if indicators else {}
    rsi_val = (indicators.get("rsi") or {}).get("value") if indicators else None
    macd_data = (indicators.get("macd") or {}) if indicators else {}
    bb = (trend.get("bollinger") or {}) if trend else {}
    forecast = (trend.get("forecast") or {}) if trend else {}
    signals_list = (trend.get("signals") or []) if trend else {}
    fin = (fundamentals or {}).get("ratios", {}) if fundamentals else {}
    bs = (fundamentals or {}).get("balance_sheet", {}) if fundamentals else {}

    user_prompt = f"""HISSE: {symbol.upper()}
GUNCEL FIYAT: {price} TL
SINYAL: {action}
GIRIS: {entry_price} TL
STOP-LOSS: {stop_loss} TL
TAKE-PROFIT: {take_profit} TL

TEKNIK GOSTERGELER:
- RSI(14): {rsi_val or 'N/A'}
- MACD: {macd_data.get('macd', 'N/A')} / Sinyal: {macd_data.get('signal', 'N/A')} / Histogram: {macd_data.get('histogram', 'N/A')} / Kesim: {macd_data.get('crossover', 'N/A')}
- SMA 20: {ma.get('sma_20', 'N/A')} / SMA 50: {ma.get('sma_50', 'N/A')} / SMA 200: {ma.get('sma_200', 'N/A')}
- Bollinger: Ust {bb.get('upper', 'N/A')} / Alt {bb.get('lower', 'N/A')} / Fiyat: {bb.get('position', 'N/A')}
- Destek: {trend.get('support', 'N/A')} / Direnc: {trend.get('resistance', 'N/A')}
- Sinyaller: {', '.join(signals_list) if signals_list else 'Yok'}
- Trend: {trend.get('trend', 'N/A')} / Skor: {trend.get('score', 'N/A')}/100
- Tahmin 5gun: {forecast.get('predictions', 'N/A')}

TEMEL VERILER:"""

    if fundamentals and fundamentals.get("has_data"):
        if fin.get('pe_ratio'): user_prompt += f"\n- F/K: {fin['pe_ratio']}"
        if fin.get('52w_high'): user_prompt += f"\n- 52H Yuksek: {fin['52w_high']}"
        if fin.get('52w_low'): user_prompt += f"\n- 52H Dusuk: {fin['52w_low']}"
        if fin.get('50d_avg'): user_prompt += f"\n- 50G Ort: {fin['50d_avg']}"
        if fin.get('200d_avg'): user_prompt += f"\n- 200G Ort: {fin['200d_avg']}"

    if news:
        news_text = "\n".join([f"- {n['title'][:80]}" for n in news[:3]])
        user_prompt += f"\n\nGUNCEL HABERLER:\n{news_text}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    for model in GROQ_MODELS:
        result = _call_groq(messages, model, max_tokens=600, temperature=0.3)
        if result:
            return result
    return None
