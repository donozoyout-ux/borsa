import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

import requests


_MAX_AGE_DAYS = 7


def _parse_date(date_str: str) -> Optional[datetime]:
    """Tarih string'ini datetime'a çevir, başarısızsa None dön."""
    if not date_str:
        return None
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        pass
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _is_recent(dt: Optional[datetime], max_age_days: int = _MAX_AGE_DAYS) -> bool:
    """Haberin tarihi son max_age_days gün içinde mi?"""
    if dt is None:
        return True  # Tarihi bilinmeyenler dahil et
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt) <= timedelta(days=max_age_days)


def _format_date(dt: Optional[datetime]) -> str:
    if not dt:
        return ""
    try:
        now = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        diff = now - dt
        if diff.days == 0:
            hours = diff.seconds // 3600
            if hours == 0:
                mins = diff.seconds // 60
                return f"{mins} dk once"
            return f"{hours} sa once"
        if diff.days == 1:
            return "dun"
        if diff.days < 7:
            return f"{diff.days} gun once"
        return dt.strftime("%d.%m.%Y")
    except Exception:
        return ""


def _fetch_google_news(symbol: str, max_items: int = 15) -> list[dict]:
    """Google News RSS - Türkce haberler."""
    clean = symbol.strip().upper().replace(".IS", "")
    queries = [
        f"{clean} BIST hisse",
        f"{clean} borsa",
        f"{clean} hisse senedi",
    ]
    seen_titles = set()
    items = []

    for query in queries:
        url = f"https://news.google.com/rss/search?q={query}&hl=tr&gl=TR&ceid=TR:tr"
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                timeout=8,
            )
            if resp.status_code != 200:
                continue
            root = ET.fromstring(resp.content)
            for item in root.findall(".//item"):
                title = (item.findtext("title") or "").strip()
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)
                link = item.findtext("link") or ""
                pub_date = item.findtext("pubDate") or ""
                source = item.findtext("source") or "Google News"
                dt = _parse_date(pub_date)
                if not _is_recent(dt):
                    continue
                items.append({
                    "title": title,
                    "link": link,
                    "source": source or "Google News",
                    "date": _format_date(dt),
                    "_dt": dt,
                })
                if len(items) >= max_items:
                    return items
        except Exception:
            continue
    return items


def _fetch_yahoo_news(symbol: str, max_items: int = 10) -> list[dict]:
    """Yahoo Finance RSS feed."""
    clean = symbol.strip().upper().replace(".IS", "")
    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={clean}.IS&region=TR&lang=tr-TR"
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            timeout=8,
        )
        if resp.status_code != 200:
            return []
        root = ET.fromstring(resp.content)
        items = []
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            if not title:
                continue
            link = item.findtext("link") or ""
            pub_date = item.findtext("pubDate") or ""
            dt = _parse_date(pub_date)
            if not _is_recent(dt):
                continue
            desc = item.findtext("description") or ""
            desc = re.sub(r"<[^>]+>", "", desc).strip()[:120]
            items.append({
                "title": title,
                "link": link,
                "source": "Yahoo Finance",
                "date": _format_date(dt),
                "_dt": dt,
            })
            if len(items) >= max_items:
                break
        return items
    except Exception:
        return []


def _fetch_investing_news(symbol: str, max_items: int = 10) -> list[dict]:
    """Investing.com RSS - Türkce finans haberleri."""
    clean = symbol.strip().upper().replace(".IS", "")
    queries = [
        f"{clean}-hisse-yorum",
        f"{clean}-borsa",
    ]
    items = []
    seen_titles = set()

    for q in queries:
        url = f"https://www.investing.com/rss/news_{q}.rss"
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                timeout=8,
            )
            if resp.status_code != 200:
                continue
            root = ET.fromstring(resp.content)
            for item in root.findall(".//item"):
                title = (item.findtext("title") or "").strip()
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)
                link = item.findtext("link") or ""
                pub_date = item.findtext("pubDate") or ""
                dt = _parse_date(pub_date)
                if not _is_recent(dt):
                    continue
                items.append({
                    "title": title,
                    "link": link,
                    "source": "Investing.com",
                    "date": _format_date(dt),
                    "_dt": dt,
                })
                if len(items) >= max_items:
                    return items
        except Exception:
            continue
    return items


def _fetch_paragaranti_news(symbol: str, max_items: int = 8) -> list[dict]:
    """ParaGaranti RSS - Türkce finans haberleri."""
    url = "https://www.paragaranti.com.tr/rss/main.xml"
    clean = symbol.strip().upper().replace(".IS", "")
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            timeout=8,
        )
        if resp.status_code != 200:
            return []
        root = ET.fromstring(resp.content)
        items = []
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            desc_raw = item.findtext("description") or ""
            desc = re.sub(r"<[^>]+>", "", desc_raw).strip()
            full_text = (title + " " + desc).upper()
            if clean not in full_text and "BIST" not in full_text:
                continue
            link = item.findtext("link") or ""
            pub_date = item.findtext("pubDate") or ""
            dt = _parse_date(pub_date)
            if not _is_recent(dt):
                continue
            items.append({
                "title": title,
                "link": link,
                "source": "ParaGaranti",
                "date": _format_date(dt),
                "_dt": dt,
            })
            if len(items) >= max_items:
                break
        return items
    except Exception:
        return []


def get_stock_news(symbol: str, max_items: int = 10) -> list[dict]:
    """Birden fazla kaynaktan haber çek, tarihe göre sırala ve eski haberleri filtrele."""
    all_items = []
    seen_titles = set()

    # Tüm kaynakları paralel olarak çek
    fetchers = [
        _fetch_google_news,
        _fetch_yahoo_news,
        _fetch_investing_news,
        _fetch_paragaranti_news,
    ]

    for fetcher in fetchers:
        try:
            items = fetcher(symbol, max_items=max_items)
            for item in items:
                title_key = item["title"].lower().strip()
                if title_key not in seen_titles:
                    seen_titles.add(title_key)
                    all_items.append(item)
        except Exception:
            continue

    # Tarihe göre sırala (en yeniler üstte)
    def sort_key(item):
        dt = item.get("_dt")
        if dt is None:
            return datetime.min.replace(tzinfo=timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    all_items.sort(key=sort_key, reverse=True)

    #内部 tarih bilgisini temizle ve max_items kadar dön
    result = []
    for item in all_items[:max_items]:
        clean = {k: v for k, v in item.items() if k != "_dt"}
        result.append(clean)

    return result


def get_fundamentals(symbol: str) -> Optional[dict]:
    """Yahoo Finance v10 API ile finansal verileri çeker."""
    clean = symbol.strip().upper().replace(".IS", "")
    url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{clean}.IS"
    params = {"modules": "financialData,summaryDetail,balanceSheetHistory,incomeStatementHistory,defaultKeyStatistics"}
    headers = {"User-Agent": "Mozilla/5.0 BISTAlarmBot/2.0"}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code == 401:
            return None
        resp.raise_for_status()
        data = resp.json()
        result = data.get("quoteSummary", {}).get("result", [])
        if not result:
            return None
        return result[0]
    except Exception:
        return None


def parse_fundamentals(raw: dict) -> dict:
    """Ham fundamentals verisini temiz formata dönüştür."""
    fd = raw.get("financialData", {}) or {}
    sd = raw.get("summaryDetail", {}) or {}
    ks = raw.get("defaultKeyStatistics", {}) or {}

    def _val(obj, key):
        v = (obj.get(key) or {}).get("raw")
        return v

    fin = {
        "market_cap": _val(fd, "marketCap"),
        "pe_ratio": _val(fd, "trailingPE"),
        "pb_ratio": _val(ks, "priceToBook"),
        "eps": _val(fd, "epsTrailingTwelveMonths"),
        "dividend_yield": _val(sd, "dividendYield"),
        "beta": _val(sd, "beta"),
        "profit_margins": _val(fd, "profitMargins"),
        "revenue": _val(fd, "totalRevenue"),
        "debt_to_equity": _val(fd, "debtToEquity"),
        "roe": _val(fd, "returnOnEquity"),
        "52w_high": _val(sd, "fiftyTwoWeekHigh"),
        "52w_low": _val(sd, "fiftyTwoWeekLow"),
        "avg_volume": _val(sd, "averageVolume"),
        "short_ratio": _val(ks, "shortRatio"),
    }

    # Bilanço
    bs = raw.get("balanceSheetHistory", {}).get("balanceSheetStatements", [])
    balance = {}
    if bs:
        bs0 = bs[0]
        balance = {
            "total_assets": _val(bs0, "totalAssets"),
            "total_debt": _val(bs0, "totalDebt"),
            "total_liabilities": _val(bs0, "totalLiab"),
            "cash": _val(bs0, "cash"),
        }

    return {
        "ratios": fin,
        "balance_sheet": balance,
        "has_data": any(v is not None for v in fin.values()),
    }
