"""
Conference Tracker Scraper  v6
==============================
データソース優先順位:
  1. 名古屋大学 片山研究室 国際会議スケジュール（主ソース・高精度）
     http://katayama.nuee.nagoya-u.ac.jp/schedule/schedule_ic.php
  2. 公式サイト authors ページ（requests + BeautifulSoup → Playwright）
  3. WikiCFP
  4. 既存 conferences.json で補完
"""

import json
import re
import time
import logging
from datetime import datetime, date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).parent.parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

NAGOYA_BASE = "http://katayama.nuee.nagoya-u.ac.jp/schedule/schedule_ic.php"

# ─────────────────────────────────────────────
# 会議リスト
# match_keywords: 名古屋大学ページの会議名マッチング用キーワード（正規表現・小文字）
# ─────────────────────────────────────────────
TARGET_CONFERENCES = [
    {
        "abbr": "IEEE GLOBECOM",
        "full": "IEEE Global Communications Conference",
        "base_url": "https://globecom2026.ieee-globecom.org",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp"],
        "area": "Communications",
        "match_keywords": ["globecom"],
        "exclude_keywords": ["workshop"],
        "wikicfp_search": "globecom 2026",
    },
    {
        "abbr": "IEEE WCNC",
        "full": "IEEE Wireless Communications and Networking Conference",
        "base_url": "https://wcnc2026.ieee-wcnc.org",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp"],
        "area": "Wireless",
        "match_keywords": ["wcnc", "wireless communications and networking"],
        "exclude_keywords": ["workshop"],
        "wikicfp_search": "wcnc 2026",
    },
    {
        "abbr": "IEEE ICC",
        "full": "IEEE International Conference on Communications",
        "base_url": "https://icc2026.ieee-icc.org",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp"],
        "area": "Communications",
        "match_keywords": [r"\bicc\b"],
        "exclude_keywords": ["workshop"],
        "wikicfp_search": "icc 2026",
    },
    {
        "abbr": "IEEE INFOCOM",
        "full": "IEEE International Conference on Computer Communications",
        "base_url": "https://infocom2026.ieee-infocom.org",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp"],
        "area": "Networking",
        "match_keywords": ["infocom"],
        "exclude_keywords": [],
        "wikicfp_search": "infocom 2026",
    },
    {
        "abbr": "IEEE VTC",
        "full": "IEEE Vehicular Technology Conference",
        "base_url": "https://events.vtsociety.org/vtc2026-fall",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp"],
        "area": "V2X / 5G",
        "match_keywords": ["vtc-fall", "vtc fall"],
        "exclude_keywords": ["workshop"],
        "wikicfp_search": "vtc fall 2026",
    },
    {
        "abbr": "IEEE PIMRC",
        "full": "IEEE Int. Symposium on Personal, Indoor and Mobile Radio Communications",
        "base_url": "https://pimrc2026.ieee-pimrc.org",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp"],
        "area": "Wireless",
        "match_keywords": ["pimrc"],
        "exclude_keywords": [],
        "wikicfp_search": "pimrc 2026",
    },
    {
        "abbr": "IEEE IV",
        "full": "IEEE Intelligent Vehicles Symposium",
        "base_url": "https://iv2026.ieee-iv.org",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp"],
        "area": "ITS / V2X",
        "match_keywords": ["intelligent vehicles symposium"],
        "exclude_keywords": [],
        "wikicfp_search": "intelligent vehicles symposium 2026",
    },
    {
        "abbr": "IEEE VNC",
        "full": "IEEE Vehicular Networking Conference",
        "base_url": "https://vnc2026.ieee-vnc.org",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp"],
        "area": "V2X / Networking",
        "match_keywords": ["vehicular networking conference", r"\bvnc\b"],
        "exclude_keywords": [],
        "wikicfp_search": "vehicular networking 2026",
    },
    {
        "abbr": "IEEE ITSC",
        "full": "IEEE Int. Conference on Intelligent Transportation Systems",
        "base_url": "https://ieee-itsc.org/2026",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp"],
        "area": "ITS",
        "match_keywords": ["intelligent transportation systems", "itsc"],
        "exclude_keywords": [],
        "wikicfp_search": "itsc 2026",
    },
    {
        "abbr": "ITS World Congress",
        "full": "ITS World Congress",
        "base_url": "https://www.itsworldcongress.com",
        "authors_paths": ["/call-for-papers", "/cfp", "/authors", "/"],
        "area": "ITS",
        "match_keywords": ["its world congress"],
        "exclude_keywords": [],
        "wikicfp_search": "its world congress 2026",
    },
    {
        "abbr": "IEEE GCCE",
        "full": "IEEE Global Conference on Consumer Electronics",
        "base_url": "https://www.ieee-gcce.org/2026",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp"],
        "area": "Consumer Electronics",
        "match_keywords": ["gcce", "global conference on consumer electronics"],
        "exclude_keywords": [],
        "wikicfp_search": "gcce 2026",
    },
    {
        "abbr": "IEEE WFIoT",
        "full": "IEEE World Forum on Internet of Things",
        "base_url": "https://wfiot2026.iot.ieee.org",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp"],
        "area": "IoT",
        "match_keywords": ["wfiot", "world forum on internet of things"],
        "exclude_keywords": [],
        "wikicfp_search": "wfiot 2026",
    },
    {
        "abbr": "IEEE CCNC",
        "full": "IEEE Consumer Communications and Networking Conference",
        "base_url": "https://ccnc2027.ieee-ccnc.org",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp"],
        "area": "Consumer / Networking",
        "match_keywords": ["ccnc", "consumer communications"],
        "exclude_keywords": [],
        "wikicfp_search": "ccnc 2027",
    },
    {
        "abbr": "IEEE CTW",
        "full": "IEEE Communication Theory Workshop",
        "base_url": "https://ctw2026.ieee-ctw.org",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp"],
        "area": "Theory",
        "match_keywords": ["communication theory workshop", r"\bctw\b"],
        "exclude_keywords": [],
        "wikicfp_search": "communication theory workshop 2026",
    },
    {
        "abbr": "APCC",
        "full": "Asia-Pacific Conference on Communications",
        "base_url": "https://apcc2026.org",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp", "/"],
        "area": "Asia-Pacific",
        "match_keywords": ["asia-pacific conference on communications", r"\bapcc\b"],
        "exclude_keywords": [],
        "wikicfp_search": "apcc 2026",
    },
    {
        "abbr": "ICOIN",
        "full": "International Conference on Information Networking",
        "base_url": "https://www.icoin.org",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp", "/"],
        "area": "Networking",
        "match_keywords": ["information networking", r"\bicoin\b"],
        "exclude_keywords": [],
        "wikicfp_search": "icoin 2026",
    },
    {
        "abbr": "WPMC",
        "full": "Int. Symposium on Wireless Personal Multimedia Communications",
        "base_url": "https://www.wpmc-conf.org/2026",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp", "/"],
        "area": "Wireless",
        "match_keywords": ["wireless personal multimedia", r"\bwpmc\b"],
        "exclude_keywords": [],
        "wikicfp_search": "wpmc 2026",
    },
    {
        "abbr": "ICETC",
        "full": "Int. Conference on Emerging Technologies for Communications",
        "base_url": "https://www.ieice.org/cs/icetc/2026",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp", "/"],
        "area": "Emerging Tech",
        "match_keywords": ["emerging technologies for communications", r"\bicetc\b"],
        "exclude_keywords": [],
        "wikicfp_search": "icetc 2026",
    },
    {
        "abbr": "ICNC",
        "full": "Int. Conference on Computing, Networking and Communications",
        "base_url": "https://www.conf-icnc.org/2027",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp", "/"],
        "area": "Networking",
        "match_keywords": ["computing, networking and communications", r"\bicnc\b"],
        "exclude_keywords": [],
        "wikicfp_search": "icnc 2027",
    },
]

# ─────────────────────────────────────────────
# 日付パーサー
# ─────────────────────────────────────────────

MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4,
    "june": 6, "july": 7, "august": 8, "september": 9,
    "october": 10, "november": 11, "december": 12,
}


def parse_date(raw: str) -> str | None:
    """文字列から ISO 形式 (YYYY-MM-DD) の日付を抽出する。"""
    if not raw:
        return None
    raw = re.sub(r"\(.*?\)", "", raw).strip()   # (extended), (firm) などを除去
    raw = re.sub(r"[→⇒>].*", "", raw).strip()   # 延長前の日付を除去

    # YYYY/MM/DD or YYYY-MM-DD
    m = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # DD Month YYYY
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", raw)
    if m:
        mon = MONTH_MAP.get(m.group(2).lower())
        if mon:
            return f"{m.group(3)}-{mon:02d}-{int(m.group(1)):02d}"
    # Month DD, YYYY
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2})[,\s]+(\d{4})", raw)
    if m:
        mon = MONTH_MAP.get(m.group(1).lower())
        if mon:
            return f"{m.group(3)}-{mon:02d}-{int(m.group(2)):02d}"
    return None


def parse_conf_date_range(raw: str) -> tuple[str | None, str | None]:
    """
    名古屋大学ページの開催日形式をパースする。
    "2026/6/8-10"（同月） / "2026/5/24-6/3"（月またぎ） / "2026/6/9"（単日）
    """
    if not raw:
        return None, None
    raw = raw.strip()

    # YYYY/MM/DD-DD（同月）
    m = re.match(r"(\d{4})/(\d{1,2})/(\d{1,2})-(\d{1,2})$", raw)
    if m:
        y, mo, d1, d2 = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))
        return f"{y}-{mo:02d}-{d1:02d}", f"{y}-{mo:02d}-{d2:02d}"

    # YYYY/MM/DD-MM/DD（月またぎ）
    m = re.match(r"(\d{4})/(\d{1,2})/(\d{1,2})-(\d{1,2})/(\d{1,2})$", raw)
    if m:
        y = m.group(1)
        m1, d1 = int(m.group(2)), int(m.group(3))
        m2, d2 = int(m.group(4)), int(m.group(5))
        return f"{y}-{m1:02d}-{d1:02d}", f"{y}-{m2:02d}-{d2:02d}"

    # 単日 YYYY/MM/DD
    single = parse_date(raw)
    return single, single


# ─────────────────────────────────────────────
# 名古屋大学ページの全件取得
# ─────────────────────────────────────────────

def fetch_nagoya_all() -> list[dict]:
    """
    名古屋大学 片山研究室の国際会議スケジュールページを全件取得する。
    ページネーションを自動処理（offset=0, 50, 100, ...）。
    """
    all_rows: list[dict] = []
    offset = 0
    page_size = 50

    while True:
        url = f"{NAGOYA_BASE}?offset={offset}&mode=0"
        log.info("  [名古屋大学] 取得中: %s", url)
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            r.encoding = "utf-8"
        except Exception as e:
            log.warning("  [名古屋大学] 取得失敗 (offset=%d): %s", offset, e)
            break

        soup = BeautifulSoup(r.text, "html.parser")
        table = soup.find("table", class_="style_table")
        if not table:
            log.warning("  [名古屋大学] テーブルが見つかりません (offset=%d)", offset)
            break

        rows = table.find_all("tr")[1:]  # ヘッダー行をスキップ
        if not rows:
            break

        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 4:
                continue
            conf_date_raw = cells[0].get_text(strip=True)
            name_cell     = cells[1]
            name          = name_cell.get_text(strip=True)
            link          = name_cell.find("a")
            conf_url      = link["href"].strip() if link and link.get("href") else ""
            location      = cells[2].get_text(strip=True)
            deadline_raw  = cells[3].get_text(strip=True)

            all_rows.append({
                "conf_date_raw": conf_date_raw,
                "name":          name,
                "url":           conf_url,
                "location":      location,
                "deadline_raw":  deadline_raw,
            })

        log.info("  [名古屋大学] offset=%d: %d 行取得（累計 %d 件）",
                 offset, len(rows), len(all_rows))

        # 次ページの有無を確認
        has_next = (
            len(rows) >= page_size
            and f"offset={offset + page_size}" in r.text
        )
        if not has_next:
            break

        offset += page_size
        time.sleep(1.0)

    log.info("  [名古屋大学] 合計 %d 件取得完了", len(all_rows))
    return all_rows


def match_nagoya_entry(
    target: dict,
    nagoya_rows: list[dict],
    target_year: int,
) -> dict | None:
    """
    TARGET_CONFERENCES の1件に対して名古屋大学データから最適な行を選ぶ。
    """
    today_str = date.today().isoformat()
    candidates = []

    for row in nagoya_rows:
        name_lower = row["name"].lower()

        # exclude チェック
        if any(ex in name_lower for ex in target.get("exclude_keywords", [])):
            continue

        # keyword マッチ（正規表現）
        matched = any(
            re.search(kw, name_lower)
            for kw in target["match_keywords"]
        )
        if not matched:
            continue

        # 開催年チェック
        conf_start, _ = parse_conf_date_range(row["conf_date_raw"])
        if not conf_start:
            continue
        if int(conf_start[:4]) < target_year:
            continue

        candidates.append((conf_start, row))

    if not candidates:
        return None

    # 最も近い将来の開催を優先、なければ最新の過去
    future = [(s, r) for s, r in candidates if s >= today_str]
    if future:
        future.sort(key=lambda x: x[0])
        return future[0][1]
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


# ─────────────────────────────────────────────
# 公式サイトフォールバック
# ─────────────────────────────────────────────

DEADLINE_KEYWORDS = [
    "paper submission deadline", "deadline for paper submission",
    "full paper submission", "submission deadline", "paper submission",
    "abstract submission", "abstract deadline", "manuscript due", "paper due",
]
NOTIFICATION_KEYWORDS = [
    "notification of acceptance", "acceptance notification",
    "author notification", "notification date", "notification",
]
SKIP_KEYWORDS = [
    "tutorial", "workshop", "industry forum", "panel", "demo",
    "poster", "special session", "camera ready", "camera-ready",
    "final paper", "registration",
]


def _is_skip(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in SKIP_KEYWORDS)


def extract_dates_from_soup(soup: BeautifulSoup) -> dict:
    """BeautifulSoup から締切・通知日を抽出する。"""
    result: dict = {}

    def try_set(key: str, value: str, ctx: str = "") -> bool:
        if key in result or _is_skip(ctx):
            return False
        d = parse_date(value)
        if d:
            result[key] = d
            log.info("    [HTML] %s: %s ← \"%s\"", key, d, value[:50])
            return True
        return False

    def classify(label: str) -> str | None:
        ll = label.lower()
        if _is_skip(ll):
            return None
        for kw in DEADLINE_KEYWORDS:
            if kw in ll:
                return "deadline"
        for kw in NOTIFICATION_KEYWORDS:
            if kw in ll:
                return "notification"
        return None

    # テーブル
    for table in soup.find_all("table"):
        prev = table.find_previous(["h1","h2","h3","h4","h5","h6","caption"])
        ctx = prev.get_text() if prev else ""
        for row in table.find_all("tr"):
            cells = row.find_all(["td","th"])
            if len(cells) < 2:
                continue
            label = cells[0].get_text(" ", strip=True)
            value = " ".join(c.get_text(" ", strip=True) for c in cells[1:])
            key = classify(label)
            if key:
                try_set(key, value, ctx + label)

    # dl/dt/dd
    for dl in soup.find_all("dl"):
        for dt, dd in zip(dl.find_all("dt"), dl.find_all("dd")):
            key = classify(dt.get_text(" ", strip=True))
            if key:
                try_set(key, dd.get_text(" ", strip=True))

    # li
    for li in soup.find_all("li"):
        text = li.get_text(" ", strip=True)
        for sep in [":", "–", "-", "—"]:
            if sep in text:
                parts = text.split(sep, 1)
                key = classify(parts[0])
                if key:
                    try_set(key, parts[1])
                    break

    # テキストスキャン（補完）
    if "deadline" not in result or "notification" not in result:
        lines = soup.get_text("\n").split("\n")
        for i, line in enumerate(lines):
            if _is_skip(line):
                continue
            key = classify(line)
            if key and key not in result:
                for cand in [line] + lines[i+1:i+3]:
                    d = parse_date(cand)
                    if d:
                        result[key] = d
                        log.info("    [TEXT] %s: %s", key, d)
                        break

    return result


def fetch_official(base_url: str, paths: list[str]) -> tuple[dict, str]:
    """公式サイトから締切・通知日を取得。(dates_dict, source_url) を返す。"""
    for path in paths:
        url = base_url.rstrip("/") + path

        # requests
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200 and len(r.text) > 300:
                soup = BeautifulSoup(r.text, "html.parser")
                text = soup.get_text().lower()
                if any(kw in text for kw in ["deadline", "important dates", "submission"]):
                    dates = extract_dates_from_soup(soup)
                    if dates.get("deadline"):
                        return dates, url
        except Exception as e:
            log.debug("    requests: %s → %s", url, e)

        # Playwright（JS レンダリング）
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                ctx = browser.new_context(user_agent=HEADERS["User-Agent"], locale="en-US")
                page = ctx.new_page()
                try:
                    resp = page.goto(url, wait_until="domcontentloaded", timeout=25000)
                    if resp and resp.status == 200:
                        page.wait_for_timeout(2500)
                        html = page.content()
                        soup = BeautifulSoup(html, "html.parser")
                        text = soup.get_text().lower()
                        if any(kw in text for kw in ["deadline", "important dates", "submission"]):
                            dates = extract_dates_from_soup(soup)
                            if dates.get("deadline"):
                                browser.close()
                                return dates, url
                finally:
                    browser.close()
        except ImportError:
            log.debug("    Playwright 未インストール")
        except Exception as e:
            log.debug("    playwright: %s → %s", url, e)

    return {}, ""


# ─────────────────────────────────────────────
# WikiCFP フォールバック
# ─────────────────────────────────────────────

def wikicfp_fetch(keyword: str) -> dict:
    url = f"http://www.wikicfp.com/cfp/call?conference={requests.utils.quote(keyword)}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        log.warning("  WikiCFP 失敗: %s", e)
        return {}

    soup = BeautifulSoup(r.text, "html.parser")
    today = date.today()
    best = None

    for row in soup.select("table.oveAli tr")[1:10]:
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        link = cells[0].find("a")
        if not link:
            continue
        eid_m = re.search(r"eventid=(\d+)", link.get("href", ""))
        if not eid_m:
            continue
        title = link.get_text(strip=True)
        when  = cells[1].get_text(strip=True)
        where = cells[2].get_text(strip=True)
        dl    = cells[3].get_text(strip=True)
        yr_m  = re.search(r"20(\d{2})", title + " " + when)
        year  = int("20" + yr_m.group(1)) if yr_m else 0

        if year >= today.year:
            best = {"event_id": eid_m.group(1), "when": when, "where": where, "deadline": dl}
            break

    if not best:
        return {}

    time.sleep(1.0)
    try:
        r2 = requests.get(
            f"http://www.wikicfp.com/cfp/servlet/event.showcfp?eventid={best['event_id']}",
            headers=HEADERS, timeout=15,
        )
        soup2 = BeautifulSoup(r2.text, "html.parser")
        info: dict = {"where": best["where"], "when": best["when"]}
        for row2 in soup2.select("table.gg tr"):
            cells2 = row2.find_all("td")
            if len(cells2) < 2:
                continue
            lbl = cells2[0].get_text(strip=True).lower()
            val = cells2[1].get_text(strip=True)
            if "submission deadline" in lbl:
                info["deadline_raw"] = val
            elif "notification" in lbl and "submission" not in lbl:
                info["notification_raw"] = val
            elif "conference date" in lbl or "when" in lbl:
                info["confDate_raw"] = val
            elif "location" in lbl or "where" in lbl:
                info["where"] = val
        for a in soup2.select("a[href^='http']"):
            href = a.get("href", "")
            if "wikicfp" not in href:
                info["url"] = href
                break
        return info
    except Exception as e:
        log.warning("  WikiCFP 詳細失敗: %s", e)
        return {"where": best["where"]}


# ─────────────────────────────────────────────
# メイン処理
# ─────────────────────────────────────────────

def process_conference(
    target: dict,
    nagoya_rows: list[dict],
    existing: dict,
    target_year: int,
) -> dict:
    abbr = target["abbr"]

    entry: dict = {
        "abbr":         abbr,
        "full":         target["full"],
        "url":          target["base_url"],
        "area":         target["area"],
        "location":     "TBD",
        "confDate":     None,
        "confDateEnd":  None,
        "deadline":     None,
        "notification": None,
        "source":       None,
        "data_source":  "none",
        "fetched_at":   datetime.utcnow().isoformat() + "Z",
    }

    # ── Step 1: 名古屋大学ページからマッチング ─────────────────────
    nagoya_row = match_nagoya_entry(target, nagoya_rows, target_year)
    if nagoya_row:
        conf_start, conf_end = parse_conf_date_range(nagoya_row["conf_date_raw"])
        dl = parse_date(nagoya_row["deadline_raw"])
        entry["confDate"]    = conf_start
        entry["confDateEnd"] = conf_end
        entry["location"]    = nagoya_row["location"] or "TBD"
        if nagoya_row["url"]:
            entry["url"] = nagoya_row["url"]
        if dl:
            entry["deadline"]    = dl
            entry["source"]      = NAGOYA_BASE
            entry["data_source"] = "nagoya"
            log.info("  ✓ 名古屋大学: deadline=%s, conf=%s, location=%s",
                     dl, nagoya_row["conf_date_raw"], nagoya_row["location"])
        else:
            log.info("  名古屋大学: 会議情報あり（締切未記載）conf=%s",
                     nagoya_row["conf_date_raw"])

    # ── Step 2: 公式サイト（締切が未取得の場合） ───────────────────
    if not entry["deadline"]:
        log.info("  → 公式サイト取得試行: %s", target["base_url"])
        dates, page_url = fetch_official(target["base_url"], target["authors_paths"])
        if dates.get("deadline"):
            entry["deadline"]     = dates["deadline"]
            entry["notification"] = dates.get("notification")
            entry["source"]       = page_url
            entry["data_source"]  = "official"
            log.info("  ✓ 公式サイト: deadline=%s", entry["deadline"])

    # ── Step 3: WikiCFP フォールバック ─────────────────────────────
    if not entry["deadline"]:
        log.info("  → WikiCFP: %s", target["wikicfp_search"])
        wdata = wikicfp_fetch(target["wikicfp_search"])
        if wdata:
            dl = parse_date(wdata.get("deadline_raw", ""))
            if dl:
                entry["deadline"]     = dl
                entry["notification"] = parse_date(wdata.get("notification_raw", ""))
                entry["location"]     = wdata.get("where", entry["location"])
                entry["url"]          = wdata.get("url", entry["url"])
                entry["data_source"]  = "wikicfp"
                log.info("  ✓ WikiCFP: deadline=%s", dl)
        time.sleep(1.5)

    # ── Step 4: 既存データで補完 ────────────────────────────────────
    old = existing.get(abbr, {})
    for field in ("deadline", "notification", "confDate", "confDateEnd", "location", "url", "full"):
        if not entry.get(field) and old.get(field):
            entry[field] = old[field]
            log.info("  補完 [%s] ← 既存: %s", field, old[field])

    return entry


def main() -> None:
    today = date.today()
    target_year = today.year

    log.info("======== 会議情報取得開始 (%d 件, 対象年: %d〜) ========",
             len(TARGET_CONFERENCES), target_year)

    # 既存データ読み込み
    output_path = REPO_ROOT / "conferences.json"
    existing: dict[str, dict] = {}
    if output_path.exists():
        try:
            old = json.loads(output_path.read_text(encoding="utf-8"))
            old_list = old.get("conferences", old) if isinstance(old, dict) else old
            existing = {c["abbr"]: c for c in old_list if isinstance(c, dict)}
            log.info("既存データ読み込み: %d 件", len(existing))
        except Exception as e:
            log.warning("既存データ読み込み失敗: %s", e)

    # 名古屋大学ページを全件取得（共通ソース）
    log.info("── 名古屋大学スケジュールページ取得 ──")
    nagoya_rows = fetch_nagoya_all()

    # 各会議を処理
    conferences = []
    for i, target in enumerate(TARGET_CONFERENCES, 1):
        log.info("[%d/%d] %s", i, len(TARGET_CONFERENCES), target["abbr"])
        try:
            entry = process_conference(target, nagoya_rows, existing, target_year)
            conferences.append(entry)
            log.info("  完了: deadline=%s, source=%s",
                     entry["deadline"], entry["data_source"])
        except Exception as e:
            log.error("  エラー: %s", e)
            old_entry = existing.get(target["abbr"])
            conferences.append(old_entry if old_entry else {
                "abbr":        target["abbr"],
                "full":        target["full"],
                "url":         target["base_url"],
                "area":        target["area"],
                "location":    "TBD",
                "confDate":    None,
                "confDateEnd": None,
                "deadline":    None,
                "notification": None,
                "data_source": "error",
                "fetched_at":  datetime.utcnow().isoformat() + "Z",
            })

    output = {
        "updated_at":  datetime.utcnow().isoformat() + "Z",
        "conferences": conferences,
    }
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("======== 完了: %d 件 → %s ========", len(conferences), output_path)


if __name__ == "__main__":
    main()
