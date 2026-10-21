from urllib.parse import quote_plus
import feedparser


def fetch_market_news_indonesia(max_items: int = 6) -> list[dict[str, str]]:
    """
    Mengambil berita pasar saham Indonesia (IHSG, Bursa Efek Indonesia, saham pilihan)
    terbaru dari Google News RSS Indonesia untuk bahan rapat DSU Karyawan AI.
    """
    query = quote_plus("IHSG OR saham BEI OR rekomendasi saham hari ini")
    url = f"https://news.google.com/rss/search?q={query}+when:2d&hl=id&gl=ID&ceid=ID:id"
    items: list[dict[str, str]] = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:max_items]:
            items.append(
                {
                    "title": entry.get("title", ""),
                    "published": entry.get("published", ""),
                    "source": entry.get("source", {}).get("title", "Berita Pasar"),
                }
            )
    except Exception:
        pass
    return items


def fetch_ticker_news(ticker: str, max_items: int = 5) -> list[dict[str, str]]:
    """
    Mengambil berita spesifik untuk satu kode saham (contoh: BBCA.JK -> cari berita 'saham BBCA').
    """
    clean_code = ticker.upper().replace(".JK", "")
    query = quote_plus(f"saham {clean_code}")
    url = f"https://news.google.com/rss/search?q={query}+when:7d&hl=id&gl=ID&ceid=ID:id"
    items: list[dict[str, str]] = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:max_items]:
            items.append(
                {
                    "title": entry.get("title", ""),
                    "published": entry.get("published", ""),
                    "source": entry.get("source", {}).get("title", "Media Keuangan"),
                }
            )
    except Exception:
        pass
    return items
