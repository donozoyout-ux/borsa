import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional

import requests


def get_stock_news(symbol: str, max_items: int = 5) -> list[dict]:
    """Google News RSS üzerinden hisse haberlerini çeker."""
    clean = symbol.strip().upper().replace(".IS", "")
    query = f"{clean} BIST hisse"
    url = f"https://news.google.com/rss/search?q={query}&hl=tr&gl=TR"

    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        items = []
        for item in root.findall(".//item")[:max_items]:
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            pub_date = item.findtext("pubDate", "")
            source = item.findtext("source", "")
            items.append({
                "title": title,
                "link": link,
                "source": source or "Google News",
                "date": pub_date,
            })
        return items
    except Exception:
        return []


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
