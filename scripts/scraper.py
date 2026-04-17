"""
Conference Tracker Scraper  v4
==============================
データ取得の優先順位:
  1. overrides.json        ← 手動で書いた正確な情報（最優先）
  2. 公式サイト直接スクレイプ ← 規則的なURLを持つIEEE主要会議
  3. 既存 conferences.json  ← 前回取得データを保持（劣化させない）

WikiCFP は現在ブロック中のため使用しない。
"""

import json
import re
import time
import logging
from datetime import datetime, date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).parent.parent
TODAY     = date.today()
CY        = TODAY.year  # 現在年度

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# ─────────────────────────────────────────────
# 会議リスト
# url_pattern: {Y} を年度に置換して試みる
# pages: 締切日が載っているページの候補パス
# ─────────────────────────────────────────────
TARGET_CONFERENCES = [
    {
        "abbr": "IEEE GLOBECOM",
        "full": "IEEE Global Communications Conference",
        "area": "Communications",
        "url_pattern": "https://globecom{Y}.ieee-globecom.org/",
        "pages": ["authors/", "authors/call-for-papers/", "call-for-papers/"],
    },
    {
        "abbr": "IEEE WCNC",
        "full": "IEEE Wireless Communications and Networking Conference",
        "area": "Wireless",
        "url_pattern": "https://wcnc{Y}.ieee-wcnc.org/",
        "pages": ["authors/call-for-papers/", "call-for-papers/", "authors/"],
    },
    {
        "abbr": "IEEE ICC",
        "full": "IEEE International Conference on Communications",
        "area": "Communications",
        "url_pattern": "https://icc{Y}.ieee-icc.org/",
        "pages": ["authors/", "authors/call-for-papers/", "call-for-papers/"],
    },
    {
        "abbr": "IEEE INFOCOM",
        "full": "IEEE International Conference on Computer Communications",
        "area": "Networking",
        "url_pattern": "https://infocom{Y}.ieee-infocom.org/",
        "pages": ["authors/", "authors/call-for-papers/", "call-for-papers/"],
    },
    {
        "abbr": "IEEE VTC",
        "full": "IEEE Vehicular Technology Conference",
        "area": "V2X / 5G",
        "url_pattern": "https://events.vtsociety.org/vtc{Y}-fall/",
        "pages": ["authors/", "call-for-papers/", ""],
        "alt_patterns": ["https://events.vtsociety.org/vtc{Y}-spring/"],
    },
    {
        "abbr": "IEEE PIMRC",
        "full": "IEEE Int. Symposium on Personal, Indoor and Mobile Radio Communications",
        "area": "Wireless",
        "url_pattern": "https://pimrc{Y}.ieee-pimrc.org/",
        "pages": ["authors/", "call-for-papers/", ""],
    },
    {
        "abbr": "IEEE IV",
        "full": "IEEE Intelligent Vehicles Symposium",
        "area": "ITS / V2X",
        "url_pattern": "https://iv{Y}.ieee-iv.org/",
        "pages": ["authors/", "call-for-papers/", ""],
    },
    {
        "abbr": "IEEE VNC",
        "full": "IEEE Vehicular Networking Conference",
        "area": "V2X / Networking",
        "url_pattern": "https://ieee-vnc.org/{Y}/",
        "pages": ["cfp/", "call-for-papers/", ""],
    },
    {
        "abbr": "IEEE ITSC",
        "full": "IEEE Int. Conference on Intelligent Transportation Systems",
        "area": "ITS",
        "url_pattern": "https://ieee-itsc.org/{Y}/",
        "pages": ["authors/", "call-for-papers/", "cfp/", ""],
    },
    {
        "abbr": "ITS World Congress",
        "full": "ITS World Congress",
        "area": "ITS",
        "url_pattern": "https://www.itsworldcongress.com/",
        "pages": ["call-for-papers/", ""],
    },
    {
        "abbr": "IEEE GCCE",
        "full": "IEEE Global Conference on Consumer Electronics",
        "area": "Consumer Electronics",
        "url_pattern": "https://www.ieee-gcce.org/{Y}/",
        "pages": ["authors/", "call-for-papers/", "cfp.html", ""],
    },
    {
        "abbr": "IEEE WFIoT",
        "full": "IEEE World Forum on Internet of Things",
        "area": "IoT",
        "url_pattern": "https://wfiot{Y}.iot.ieee.org/",
        "pages": ["authors/", "call-for-papers/", ""],
    },
    {
        "abbr": "IEEE CCNC",
        "full": "IEEE Consumer Communications and Networking Conference",
        "area": "Consumer / Networking",
        # CCNC は1月開催なので次年度のURLを先に試みる
        "url_pattern": "https://ccnc{Y}.ieee-ccnc.org/",
        "pages": ["authors/", "call-for-papers/", ""],
        "year_offset": 1,   # 現在年+1 を最初に試みる
    },
    {
        "abbr": "IEEE CTW",
        "full": "IEEE Communication Theory Workshop",
        "area": "Theory",
        "url_pattern": "https://ctw{Y}.ieee-ctw.org/",
        "pages": ["cfp/", "call-for-papers/", ""],
    },
    {
        "abbr": "APCC",
        "full": "Asia-Pacific Conference on Communications",
        "area": "Asia-Pacific",
        "url_pattern": "https://apcc{Y}.org/",
        "pages": ["authors/", "call-for-papers/", ""],
    },
    {
        "abbr": "ICOIN",
        "full": "International Conference on Information Networking",
        "area": "Networking",
        # ICOIN は1月開催 → 次年度を先に
        "url_pattern": "https://www.icoin.org/{Y}/",
        "pages": ["cfp/", "call-for-papers/", ""],
        "year_offset": 1,
    },
    {
        "abbr": "WPMC",
        "full": "Int. Symposium on Wireless Personal Multimedia Communications",
        "area": "Wireless",
        "url_pattern": "https://www.wpmc-conf.org/{Y}/",
        "pages": ["cfp/", "authors/", ""],
    },
    {
        "abbr": "ICETC",
        "full": "Int. Conference on Emerging Technologies for Communications",
        "area": "Emerging Tech",
        "url_pattern": "https://www.ieice.org/cs/icetc/{Y}/",
        "pages": ["cfp.html", "authors/", ""],
    },
    {
        "abbr": "ICNC",
        "full": "Int. Conference on Computing, Networking and Communications",
        "area": "Networking",
        # ICNC は2月開催 → 次年度を先に
        "url_pattern": "https://www.conf-icnc.org/{Y}/",
        "pages": ["cfp/", "authors/", ""],
        "year_offset": 1,
    },
]


# ─────────────────────────────────────────────
# 日付パーサー
# ─────────────────────────────────────────────

MONTH_MAP = {
    "january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
    "july":7,"august":8,"september":9,"october":10,"november":11,"december":12,
    "jan":1,"feb":2,"mar":3,"apr":4,"jun":6,
    "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
}

def parse_date(raw: str) -> str | None:
    if not raw:
        return None
    raw = raw.strip()
    # YYYY-MM-DD
    m = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # Month DD, YYYY  or  DD Month YYYY
    m = re.search(r"([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})", raw)
    if m:
        mon = MONTH_MAP.get(m.group(1).lower())
        if mon:
            return f"{m.group(3)}-{mon:02d}-{int(m.group(2)):02d}"
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", raw)
    if m:
        mon = MONTH_MAP.get(m.group(2).lower())
        if mon:
            return f"{m.group(3)}-{mon:02d}-{int(m.group(1)):02d}"
    return None

def parse_conf_dates(raw: str) -> tuple[str | None, str | None]:
    if not raw:
        return None, None
    # "May 18-21, 2026"
    m = re.search(r"([A-Za-z]+)\.?\s+(\d{1,2})\s*[-–]\s*(\d{1,2}),?\s+(\d{4})", raw)
    if m:
        mon = MONTH_MAP.get(m.group(1).lower())
        if mon:
            y = m.group(4)
            return f"{y}-{mon:02d}-{int(m.group(2)):02d}", f"{y}-{mon:02d}-{int(m.group(3)):02d}"
    # "May 18 – June 2, 2026"
    m = re.search(r"([A-Za-z]+)\.?\s+(\d{1,2})\s*[-–]\s*([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})", raw)
    if m:
        m1 = MONTH_MAP.get(m.group(1).lower())
        m2 = MONTH_MAP.get(m.group(3).lower())
        y  = m.group(5)
        if m1 and m2:
            return f"{y}-{m1:02d}-{int(m.group(2)):02d}", f"{y}-{m2:02d}-{int(m.group(4)):02d}"
    s = parse_date(raw)
    return s, s


# ─────────────────────────────────────────────
# 公式サイト スクレイパー
# ─────────────────────────────────────────────

def fetch_url(url: str) -> BeautifulSoup | None:
    """URL を取得して BeautifulSoup を返す。失敗時は None。"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=12, allow_redirects=True)
        if r.status_code == 200:
            return BeautifulSoup(r.text, "html.parser")
        log.debug("    HTTP %s: %s", r.status_code, url)
    except requests.RequestException as e:
        log.debug("    取得失敗: %s → %s", url, e)
    return None


def find_dates_in_soup(soup: BeautifulSoup) -> dict:
    """
    ページ内から締切日・通知日・開催日を正規表現で抽出する。

    IEEE 系サイトの "Important Dates" ページでは
    以下のようなパターンが多い:
      "Paper Submission Deadline: May 15, 2026"
      "Notification of Acceptance: August 1, 2026"
      "Conference Dates: October 5-8, 2026"
    """
    text = soup.get_text(" ", strip=True)
    result = {}

    # ── 締切日 ──────────────────────────────────────────────────────
    DEADLINE_PATTERNS = [
        r"(?:paper\s+)?submission\s+deadline[:\s]+([A-Za-z0-9 ,\-–/]+?\d{4})",
        r"(?:full\s+)?paper\s+due[:\s]+([A-Za-z0-9 ,\-–/]+?\d{4})",
        r"manuscript\s+(?:submission\s+)?deadline[:\s]+([A-Za-z0-9 ,\-–/]+?\d{4})",
        r"submission\s+of\s+(?:full\s+)?papers?[:\s]+([A-Za-z0-9 ,\-–/]+?\d{4})",
    ]
    for pat in DEADLINE_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            d = parse_date(m.group(1).strip())
            if d:
                result["deadline"] = d
                break

    # ── 通知日 ──────────────────────────────────────────────────────
    NOTIF_PATTERNS = [
        r"notification\s+(?:of\s+)?(?:acceptance|results?)[:\s]+([A-Za-z0-9 ,\-–/]+?\d{4})",
        r"author\s+notification[:\s]+([A-Za-z0-9 ,\-–/]+?\d{4})",
        r"acceptance\s+notification[:\s]+([A-Za-z0-9 ,\-–/]+?\d{4})",
    ]
    for pat in NOTIF_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            d = parse_date(m.group(1).strip())
            if d:
                result["notification"] = d
                break

    # ── 開催日 ──────────────────────────────────────────────────────
    CONF_PATTERNS = [
        r"conference\s+dates?[:\s]+([A-Za-z0-9 ,\-–]+?\d{4})",
        r"(?:symposium|workshop|congress)\s+dates?[:\s]+([A-Za-z0-9 ,\-–]+?\d{4})",
    ]
    for pat in CONF_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            s, e = parse_conf_dates(m.group(1).strip())
            if s:
                result["confDate"]    = s
                result["confDateEnd"] = e
                break

    # ── 開催地 ──────────────────────────────────────────────────────
    LOC_PATTERNS = [
        r"(?:held|taking place|venue)[:\s]+(?:in\s+)?([A-Z][^\n\.]{5,60}?(?:,\s*[A-Z][a-z]+)?)",
        r"(?:location|venue)[:\s]+([A-Z][^\n,\.]{3,50}(?:,\s*[A-Za-z ]+)?)",
    ]
    for pat in LOC_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            loc = m.group(1).strip().rstrip(",.")
            if 4 < len(loc) < 60:
                result["location"] = loc
                break

    return result


def scrape_official_site(target: dict) -> dict:
    """
    公式サイトの Important Dates ページを直接スクレイプする。
    今年度 → 来年度 → 前年度 の順で URL を試みる。
    """
    abbr         = target["abbr"]
    pattern      = target["url_pattern"]
    pages        = target.get("pages", [""])
    alt_patterns = target.get("alt_patterns", [])
    offset       = target.get("year_offset", 0)

    # 試みる年度リスト（offset があれば先に試みる）
    years_to_try = []
    if offset:
        years_to_try.append(CY + offset)
    years_to_try += [CY, CY + 1, CY - 1]
    years_to_try = list(dict.fromkeys(years_to_try))  # 重複除去・順序保持

    all_patterns = [pattern] + alt_patterns

    for year in years_to_try:
        for pat in all_patterns:
            base_url = pat.replace("{Y}", str(year))

            # まずトップページが存在するか確認
            soup = fetch_url(base_url)
            if soup is None:
                continue

            log.info("  ✓ 公式サイト応答: %s", base_url)

            # Important Dates ページを探す
            dates = {}

            # まずトップページ自体から探す
            dates = find_dates_in_soup(soup)

            # 見つからなければサブページを試みる
            if not dates.get("deadline"):
                for page in pages:
                    if not page:
                        continue
                    sub_url  = base_url.rstrip("/") + "/" + page
                    sub_soup = fetch_url(sub_url)
                    if sub_soup:
                        sub_dates = find_dates_in_soup(sub_soup)
                        if sub_dates.get("deadline"):
                            dates = sub_dates
                            log.info("    締切日取得: %s → %s", sub_url, dates.get("deadline"))
                            break
                    time.sleep(0.5)

                # サブページでも見つからなければ内部リンクから "dates" "important" ページを探す
                if not dates.get("deadline"):
                    for a_tag in soup.find_all("a", href=True)[:60]:
                        href = a_tag["href"].lower()
                        if any(kw in href for kw in ["date", "important", "cfp", "call-for", "author"]):
                            full_href = a_tag["href"]
                            if not full_href.startswith("http"):
                                full_href = base_url.rstrip("/") + "/" + full_href.lstrip("/")
                            sub_soup = fetch_url(full_href)
                            if sub_soup:
                                sub_dates = find_dates_in_soup(sub_soup)
                                if sub_dates.get("deadline"):
                                    dates = sub_dates
                                    log.info("    締切日取得（リンク経由）: %s → %s", full_href, dates.get("deadline"))
                                    break
                            time.sleep(0.5)

            if dates.get("deadline"):
                log.info("  締切日: %s", dates["deadline"])
            else:
                log.info("  締切日: 取得できず（サイトは存在）")

            return {
                "url":          base_url,
                "location":     dates.get("location"),
                "confDate":     dates.get("confDate"),
                "confDateEnd":  dates.get("confDateEnd"),
                "deadline":     dates.get("deadline"),
                "notification": dates.get("notification"),
                "data_source":  "official_site" if dates.get("deadline") else "official_site_no_dates",
                "source":       base_url,
            }

    log.info("  公式サイト: 全年度の URL が応答なし")
    return {}


# ─────────────────────────────────────────────
# overrides.json 読み込み
# ─────────────────────────────────────────────

def load_overrides() -> dict:
    path = REPO_ROOT / "overrides.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {k: v for k, v in data.items() if not k.startswith("_")}
    except Exception as e:
        log.warning("overrides.json 読み込み失敗: %s", e)
        return {}


def apply_override(entry: dict, override: dict) -> dict:
    """override の非 null フィールドで entry を上書きする。"""
    for field, value in override.items():
        if value is not None:
            entry[field] = value
    entry["data_source"] = "manual"
    return entry


# ─────────────────────────────────────────────
# メイン
# ─────────────────────────────────────────────

def main():
    log.info("======== 会議情報取得開始 (%d 件) ========", len(TARGET_CONFERENCES))

    overrides = load_overrides()
    log.info("overrides.json: %d 件", len(overrides))

    output_path = REPO_ROOT / "conferences.json"
    existing = {}
    if output_path.exists():
        try:
            old = json.loads(output_path.read_text(encoding="utf-8"))
            old_list = old.get("conferences", old) if isinstance(old, dict) else old
            existing = {c["abbr"]: c for c in old_list if isinstance(c, dict)}
            log.info("既存データ: %d 件", len(existing))
        except Exception as e:
            log.warning("既存データ読み込み失敗: %s", e)

    conferences = []

    for i, target in enumerate(TARGET_CONFERENCES, 1):
        abbr = target["abbr"]
        log.info("[%d/%d] %s", i, len(TARGET_CONFERENCES), abbr)

        try:
            # 1. 公式サイトをスクレイプ
            scraped = scrape_official_site(target)
            time.sleep(1.5)

            # ベースエントリを作成
            entry = {
                "abbr":         abbr,
                "full":         target["full"],
                "url":          scraped.get("url") or target.get("url_pattern", "").replace("{Y}", str(CY)),
                "area":         target["area"],
                "location":     scraped.get("location") or "TBD",
                "confDate":     scraped.get("confDate"),
                "confDateEnd":  scraped.get("confDateEnd"),
                "deadline":     scraped.get("deadline"),
                "notification": scraped.get("notification"),
                "source":       scraped.get("source"),
                "data_source":  scraped.get("data_source", "no_data"),
                "fetched_at":   datetime.utcnow().isoformat() + "Z",
            }

            # 2. スクレイプで取れなかった項目を既存データで補完
            old = existing.get(abbr, {})
            for field in ("deadline", "notification", "confDate", "confDateEnd", "location"):
                if not entry.get(field) and old.get(field):
                    entry[field] = old[field]
                    entry["data_source"] = "kept_previous"
                    log.info("    補完 [%s] ← 前回データ", field)

            # 3. overrides.json で上書き（最優先）
            if abbr in overrides:
                entry = apply_override(entry, overrides[abbr])
                log.info("    ✓ overrides.json 適用 (deadline=%s)", entry.get("deadline"))

        except Exception as e:
            log.error("エラー [%s]: %s", abbr, e)
            entry = existing.get(abbr) or {
                "abbr": abbr, "full": target["full"],
                "url": target.get("url_pattern","").replace("{Y}", str(CY)),
                "area": target["area"], "location": "TBD",
                "confDate": None, "confDateEnd": None,
                "deadline": None, "notification": None,
                "source": None, "data_source": "error",
                "fetched_at": datetime.utcnow().isoformat() + "Z",
            }
            if abbr in overrides:
                entry = apply_override(entry, overrides[abbr])

        conferences.append(entry)

    # 取得結果のサマリーを出力
    log.info("────────── 取得結果サマリー ──────────")
    for c in conferences:
        src = c.get("data_source", "?")
        dl  = c.get("deadline", "なし")
        log.info("  %-20s  deadline=%-12s  source=%s", c["abbr"], dl, src)

    output = {
        "updated_at":  datetime.utcnow().isoformat() + "Z",
        "conferences": conferences,
    }
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("======== 完了: %d 件 ========", len(conferences))


if __name__ == "__main__":
    main()
