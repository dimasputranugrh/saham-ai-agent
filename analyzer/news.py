import concurrent.futures
import re
import time
from typing import Any
from urllib.parse import quote_plus
import feedparser

_RSS_CACHE: dict[tuple[str, str, int], tuple[float, list[dict[str, str]]]] = {}
_RSS_CACHE_TTL_SECONDS = 900


def _strip_html(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    return re.sub(r"\s+", " ", text).strip()

# Peta Lengkap Seluruh Sektor BEI/IDX, Emiten Utama, dan Hukum Sebab-Akibat Katalis Berita
SECTOR_CATALYST_MAP: dict[str, dict[str, Any]] = {
    "ROKOK_CUKAI": {
        "label": "🚬 Sektor Rokok & Cukai (HMSP, GGRM, WIIM)",
        "query": "cukai rokok OR saham HMSP OR GGRM OR WIIM OR tembakau",
        "tickers": ["HMSP.JK", "GGRM.JK", "WIIM.JK"],
        "causal_logic": (
            "• Jika Cukai Rokok NAIK TINGGI -> Harga jual rokok terpaksa naik, daya beli turun, margin laba tergerus -> Saham Rokok Cenderung TURUN (Bearish).\n"
            "• Jika Cukai Rokok DITAHAN / BATAL NAIK -> Beban pajak stabil, margin laba aman & dividen besar -> Saham Rokok Cenderung NAIK (Bullish)."
        ),
        "positive_keywords": ["batal naik", "tidak naik", "ditahan", "stabil", "laba naik", "dividen", "penjualan naik"],
        "negative_keywords": ["cukai naik", "tarif naik", "kenaikan cukai", "laba turun", "anjlok", "tertekan"],
    },
    "PERBANKAN_BUNGA": {
        "label": "🏦 Sektor Perbankan & Suku Bunga (BBCA, BBRI, BMRI, BBNI, BRIS)",
        "query": "BI Rate saham bank OR saham BBCA OR BBRI OR BMRI OR BBNI OR BRIS",
        "tickers": ["BBCA.JK", "BBRI.JK", "BMRI.JK", "BBNI.JK", "BRIS.JK"],
        "causal_logic": (
            "• Jika Suku Bunga (BI Rate) TURUN / Likuiditas Longgar / Kredit Tumbuh -> Bunga deposito murah, kredit lancar -> Saham Bank NAIK.\n"
            "• Jika BI Rate NAIK TINGGI / Kredit Macet (NPL) Naik / Asing Jualan -> Beban bunga naik -> Saham Bank TERTAHAN/TURUN."
        ),
        "positive_keywords": ["pangkas bunga", "bunga turun", "laba cetak rekor", "dividen", "kredit tumbuh", "akumulasi asing"],
        "negative_keywords": ["bunga naik", "npl naik", "kredit macet", "asing keluar", "net sell", "laba turun"],
    },
    "ENERGI_BATUBARA_MINYAK": {
        "label": "⚡ Sektor Energi, Batu Bara & Migas (ADRO, PTBA, ITMG, MEDC, PGAS, AKRA)",
        "query": "harga batu bara saham OR harga minyak saham OR ADRO OR PTBA OR ITMG OR MEDC OR PGAS",
        "tickers": ["ADRO.JK", "PTBA.JK", "ITMG.JK", "MEDC.JK", "PGAS.JK", "AKRA.JK"],
        "causal_logic": (
            "• Jika Harga Batu Bara / Minyak Dunia NAIK (misal karena musim dingin, krisis geopolitik, permintaan China/India naik) -> Laba emiten tambang energi melesat -> Saham Energi NAIK.\n"
            "• Jika Harga Komoditas Energi ANJLOK -> Pendapatan ekspor turun -> Saham Energi TURUN."
        ),
        "positive_keywords": ["harga batu bara naik", "minyak melonjak", "dividen jumbo", "permintaan naik", "laba naik", "kontrak baru"],
        "negative_keywords": ["harga batu bara anjlok", "minyak turun", "koreksi", "laba merosot", "oversupply"],
    },
    "TAMBANG_EMAS_LOGAM": {
        "label": "🪙 Sektor Tambang Emas, Nikel & Tembaga (ANTM, MDKA, AMMN, BRMS, INCO, TINS)",
        "query": "harga emas ANTM OR saham MDKA OR AMMN OR BRMS OR INCO OR TINS OR nikel",
        "tickers": ["ANTM.JK", "MDKA.JK", "AMMN.JK", "BRMS.JK", "INCO.JK", "TINS.JK"],
        "causal_logic": (
            "• Jika Harga Emas Dunia CETAK REKOR / Permintaan Baterai EV & Tembaga Naik -> ANTM, BRMS, MDKA, AMMN diuntungkan langsung -> Saham Logam NAIK.\n"
            "• Jika Harga Emas / Nikel Dunia Turun Tajam -> Saham Logam KOREKSI."
        ),
        "positive_keywords": ["emas rekor", "emas naik", "emas melonjak", "smelter", "ekspor naik", "laba melesat"],
        "negative_keywords": ["emas turun", "nikel anjlok", "kuota dipangkas", "rugi", "terkoreksi"],
    },
    "KONSUMER_RITEL_POULTRY": {
        "label": "🛒 Sektor Konsumer, Ritel & Peternakan (ICBP, INDF, MYOR, AMRT, JPFA, CPIN)",
        "query": "saham konsumer ICBP OR INDF OR AMRT OR MYOR OR JPFA OR CPIN OR daya beli",
        "tickers": ["ICBP.JK", "INDF.JK", "MYOR.JK", "AMRT.JK", "JPFA.JK", "CPIN.JK"],
        "causal_logic": (
            "• Jika Ada Bansos / THR / Lebaran / Program Makan Bergizi Gratis / Harga Gandum & Jagung Turun -> Penjualan makanan & ayam naik, biaya bahan baku murah -> Saham Konsumer & Poultry NAIK.\n"
            "• Jika Rupiah Melemah Parah & Harga Bahan Baku Impor Naik -> Beban produksi naik -> Saham Konsumer TERTEKAN."
        ),
        "positive_keywords": ["daya beli naik", "makan bergizi", "laba tumbuh", "ekspansi gerai", "penjualan meningkat", "bahan baku turun"],
        "negative_keywords": ["daya beli lemah", "beban naik", "rupiah anjlok", "inflasi pangan", "laba tergerus"],
    },
    "PROPERTI_OTOMOTIF": {
        "label": "🏗️ Sektor Properti, Konstruksi & Otomotif (BSDE, CTRA, SMRA, PWON, ASII, UNTR)",
        "query": "insentif PPN properti saham BSDE OR CTRA OR SMRA OR saham ASII OR UNTR",
        "tickers": ["BSDE.JK", "CTRA.JK", "SMRA.JK", "PWON.JK", "ASII.JK", "UNTR.JK"],
        "causal_logic": (
            "• Jika Pemerintah Perpanjang Insentif Bebas PPN Rumah (PPN DTP) & Bunga KPR Turun -> Penjualan rumah & kendaraan ramai -> Saham Properti & Otomotif NAIK.\n"
            "• Jika Suku Bunga KPR/Kredit Kendaraan Mahal -> Pembeli menunda beli rumah/mobil -> Saham Properti/Otomotif LESU."
        ),
        "positive_keywords": ["ppn dtp", "insentif properti", "marketing sales", "penjualan mobil naik", "bunga turun", "dividen"],
        "negative_keywords": ["penjualan mobil turun", "kpr mahal", "daya beli turun", "lesu"],
    },
    "TELKO_TEKNOLOGI_EBT": {
        "label": "📡 Sektor Telko, Teknologi & Energi Hijau (TLKM, ISAT, EXCL, BREN, GOTO, PGEO)",
        "query": "saham TLKM OR ISAT OR EXCL OR BREN OR PGEO OR GOTO OR data center AI Indonesia",
        "tickers": ["TLKM.JK", "ISAT.JK", "EXCL.JK", "BREN.JK", "PGEO.JK", "GOTO.JK"],
        "causal_logic": (
            "• Jika Tarif Kuota Internet Stabil/Naik, Ekspansi Data Center AI, atau Proyek Energi Hijau Baru -> Pendapatan berulang naik -> Saham Telko/EBT NAIK.\n"
            "• Jika Perang Harga Kuota Murah atau Bunga Utang Teknologi Tinggi -> Margin tertekan -> Saham Telko/Tech TURUN."
        ),
        "positive_keywords": ["data center", "laba naik", "merger", "energi hijau", "ekspansi", "buyback", "dividen"],
        "negative_keywords": ["perang tarif", "rugi", "koreksi tajam", "beban membengkak"],
    },
}


def _fetch_rss_query(query_str: str, when_window: str = "3d", limit: int = 8) -> list[dict[str, str]]:
    key = (query_str, when_window, limit)
    cached = _RSS_CACHE.get(key)
    if cached and time.time() - cached[0] < _RSS_CACHE_TTL_SECONDS:
        return list(cached[1])

    q = quote_plus(query_str)
    url = f"https://news.google.com/rss/search?q={q}+when:{when_window}&hl=id&gl=ID&ceid=ID:id"
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:limit]:
            title = str(entry.get("title", "")).strip()
            source = str(entry.get("source", {}).get("title", "Media Pasar")).strip()
            pub = str(entry.get("published", "")).strip()
            link = str(entry.get("link", "")).strip()
            summary = _strip_html(str(entry.get("summary", "")))[:600]
            if not title:
                continue
            dedup_key = re.sub(r"[^a-z0-9]", "", title.lower())[:60]
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            items.append(
                {
                    "title": title,
                    "source": source,
                    "published": pub,
                    "link": link,
                    "summary": summary,
                }
            )
    except Exception:
        pass
    _RSS_CACHE[key] = (time.time(), items)
    return list(items)


def fetch_market_news_indonesia(max_items: int = 12) -> list[dict[str, str]]:
    """
    Mengambil & membandingkan berita dari BANYAK sumber media dan lintas sektor BEI
    (bukan cuma 1-2 artikel), lalu menghapus duplikat judul.
    """
    queries = [
        "IHSG OR Bursa Efek Indonesia OR rekomendasi saham",
        "cukai rokok OR saham perbankan OR BI Rate",
        "saham batu bara OR harga emas ANTM OR nikel",
        "insentif properti OR saham konsumer OR dividen saham BEI",
    ]
    all_articles: list[dict[str, str]] = []
    seen_titles: set[str] = set()

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(_fetch_rss_query, q, "2d", 6) for q in queries]
        for fut in concurrent.futures.as_completed(futs, timeout=10):
            try:
                for art in fut.result():
                    key = art["title"][:45].lower()
                    if key not in seen_titles:
                        seen_titles.add(key)
                        all_articles.append(art)
            except Exception:
                pass

    return all_articles[:max_items]


def fetch_ticker_news(ticker: str, max_items: int = 8) -> list[dict[str, str]]:
    """
    Mengambil berita spesifik untuk satu kode saham dari banyak artikel media keuangan
    dan juga menyertakan berita sektor terkaitnya agar perbandingan komprehensif.
    """
    clean_code = ticker.upper().replace(".JK", "")
    items = _fetch_rss_query(f"saham {clean_code} OR emiten {clean_code}", when_window="7d", limit=max_items)
    return items


def scan_all_sectors_news_and_catalysts(articles_per_sector: int = 6) -> list[dict[str, Any]]:
    """
    Memindai seluruh 7 Sektor Utama BEI secara paralel, mengumpulkan puluhan artikel berita
    dari berbagai media (Kontan, Bisnis, CNBC, Detik, Investor.id, dll.),
    membandingkan konsensus sentimen antar-artikel, dan memetakan dampak sebab-akibatnya!
    """
    results: list[dict[str, Any]] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as ex:
        future_map = {
            ex.submit(_fetch_rss_query, cfg["query"], "3d", articles_per_sector): (sec_key, cfg)
            for sec_key, cfg in SECTOR_CATALYST_MAP.items()
        }
        for fut in concurrent.futures.as_completed(future_map, timeout=12):
            sec_key, cfg = future_map[fut]
            try:
                articles = fut.result()
            except Exception:
                articles = []

            # Deduplicate titles within sector
            unique_arts: list[dict[str, str]] = []
            seen: set[str] = set()
            sources_set: set[str] = set()
            pos_hits = 0
            neg_hits = 0

            for a in articles:
                t_low = (a["title"] + " " + a.get("summary", "")).lower()
                short_k = t_low[:45]
                if short_k in seen:
                    continue
                seen.add(short_k)
                unique_arts.append(a)
                sources_set.add(a["source"])

                for pk in cfg["positive_keywords"]:
                    if pk in t_low:
                        pos_hits += 1
                for nk in cfg["negative_keywords"]:
                    if nk in t_low:
                        neg_hits += 1

            if pos_hits > neg_hits:
                catalyst_direction = "POSITIF (Peluang Naik / Akumulasi)"
                score_bias = +1
            elif neg_hits > pos_hits:
                catalyst_direction = "NEGATIF / WASPADA (Rawan Turun / Hindari Dulu)"
                score_bias = -1
            else:
                catalyst_direction = "NETRAL / CAMPURAN (Pantau Selektif)"
                score_bias = 0

            results.append(
                {
                    "sector_key": sec_key,
                    "label": cfg["label"],
                    "tickers": cfg["tickers"],
                    "causal_logic": cfg["causal_logic"],
                    "articles_compared_count": len(unique_arts),
                    "media_sources": sorted(list(sources_set)),
                    "positive_signals": pos_hits,
                    "negative_signals": neg_hits,
                    "catalyst_direction": catalyst_direction,
                    "score_bias": score_bias,
                    "top_articles": unique_arts[:4],
                }
            )

    # Deduplicate the same headline across sectors, then sort by catalyst strength.
    seen_global: set[str] = set()
    for res in results:
        kept: list[dict[str, str]] = []
        for a in res["top_articles"]:
            key = re.sub(r"[^a-z0-9]", "", a["title"].lower())[:60]
            if key in seen_global:
                continue
            seen_global.add(key)
            kept.append(a)
        res["cross_sector_duplicates_removed"] = len(res["top_articles"]) - len(kept)
        res["top_articles"] = kept

    # Urutkan sektor dengan berita paling aktif & sinyal katalis paling kuat di atas
    results.sort(
        key=lambda x: (abs(x["positive_signals"] - x["negative_signals"]), x["articles_compared_count"]),
        reverse=True,
    )
    return results
