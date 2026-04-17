"""
Conference Tracker Scraper  v4
==============================
各会議の公式サイト（/authors ページ等）から直接スクレイプする。
overrides.json は廃止。WikiCFP は補助的に使用。

優先順位:
  1. 公式サイト /authors ページ（メインの Symposium/Technical Paper 締切）
  2. WikiCFP
  3. 既存 conferences.json（前回データ保持）
"""

import json
import re
import time
import logging
from datetime import datetime, date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────
# 会議リスト
# url_template: {year} を実際の年に置換して使う
# authors_paths: /authors ページの候補パス（順に試す）
# ─────────────────────────────────────────────
TARGET_CONFERENCES = [
    {
        "abbr": "IEEE GLOBECOM",
        "url_template": "https://globecom{year}.ieee-globecom.org/",
        "authors_paths": ["/authors", "/call-for-papers", "/authors/"],
        "wikicfp": "globecom",
        "full": "IEEE Global Communications Conference",
        "area": "Communications",
    },
    {
        "abbr": "IEEE WCNC",
        "url_template": "https://wcnc{year}.ieee-wcnc.org/",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp"],
        "wikicfp": "wcnc",
        "full": "IEEE Wireless Communications and Networking Conference",
        "area": "Wireless",
    },
    {
        "abbr": "IEEE ICC",
        "url_template": "https://icc{year}.ieee-icc.org/",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp"],
        "wikicfp": "icc",
        "full": "IEEE International Conference on Communications",
        "area": "Communications",
    },
    {
        "abbr": "IEEE INFOCOM",
        "url_template": "https://infocom{year}.ieee-infocom.org/",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp"],
        "wikicfp": "infocom",
        "full": "IEEE International Conference on Computer Communications",
        "area": "Networking",
    },
    {
        "abbr": "IEEE VTC",
        # VTC は Spring/Fall があるため URL が特殊 → wikicfp のみ
        "url_template": "https://events.vtsociety.org/vtc{year}-fall/",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp", "/"],
        "wikicfp": "vtc",
        "full": "IEEE Vehicular Technology Conference",
        "area": "V2X / 5G",
    },
    {
        "abbr": "IEEE PIMRC",
        "url_template": "https://pimrc{year}.ieee-pimrc.org/",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp"],
        "wikicfp": "pimrc",
        "full": "IEEE Int. Symposium on Personal, Indoor and Mobile Radio Communications",
        "area": "Wireless",
    },
    {
        "abbr": "IEEE IV",
        "url_template": "https://iv{year}.ieee-iv.org/",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp"],
        "wikicfp": "intelligent vehicles",
        "full": "IEEE Intelligent Vehicles Symposium",
        "area": "ITS / V2X",
    },
    {
        "abbr": "IEEE VNC",
        "url_template": "https://ieee-vnc.org/{year}/",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp", "/"],
        "wikicfp": "vehicular networking",
        "full": "IEEE Vehicular Networking Conference",
        "area": "V2X / Networking",
    },
    {
        "abbr": "IEEE ITSC",
        "url_template": "https://ieee-itsc.org/{year}/",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp", "/"],
        "wikicfp": "itsc",
        "full": "IEEE Int. Conference on Intelligent Transportation Systems",
        "area": "ITS",
    },
    {
        "abbr": "ITS World Congress",
        "url_template": "https://itsworldcongress.org/",
        "authors_paths": ["/authors", "/call-for-papers", "/submit", "/"],
        "wikicfp": "its world congress",
        "full": "ITS World Congress",
        "area": "ITS",
    },
    {
        "abbr": "IEEE GCCE",
        "url_template": "https://www.ieee-gcce.org/{year}/",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp", "/"],
        "wikicfp": "gcce",
        "full": "IEEE Global Conference on Consumer Electronics",
        "area": "Consumer Electronics",
    },
    {
        "abbr": "IEEE WFIoT",
        "url_template": "https://wfiot{year}.iot.ieee.org/",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp"],
        "wikicfp": "wfiot",
        "full": "IEEE World Forum on Internet of Things",
        "area": "IoT",
    },
    {
        "abbr": "IEEE CCNC",
        "url_template": "https://ccnc{year}.ieee-ccnc.org/",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp"],
        "wikicfp": "ccnc",
        "full": "IEEE Consumer Communications and Networking Conference",
        "area": "Consumer / Networking",
    },
    {
        "abbr": "IEEE CTW",
        "url_template": "https://ctw{year}.ieee-ctw.org/",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp", "/"],
        "wikicfp": "communication theory workshop",
        "full": "IEEE Communication Theory Workshop",
        "area": "Theory",
    },
    {
        "abbr": "APCC",
        "url_template": "https://apcc{year}.org/",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp", "/"],
        "wikicfp": "apcc",
        "full": "Asia-Pacific Conference on Communications",
        "area": "Asia-Pacific",
    },
    {
        "abbr": "ICOIN",
        "url_template": "https://www.icoin.org/",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp", "/"],
        "wikicfp": "icoin",
        "full": "International Conference on Information Networking",
        "area": "Networking",
    },
    {
        "abbr": "WPMC",
        "url_template": "https://www.wpmc-conf.org/",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp", "/"],
        "wikicfp": "wpmc",
        "full": "Int. Symposium on Wireless Personal Multimedia Communications",
        "area": "Wireless",
    },
    {
        "abbr": "ICETC",
        "url_template": "https://www.ieice.org/cs/icetc/{year}/",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp", "/"],
        "wikicfp": "icetc",
        "full": "Int. Conference on Emerging Technologies for Communications",
        "area": "Emerging Tech",
    },
    {
        "abbr": "ICNC",
        "url_template": "https://www.conf-icnc.org/{year}/",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp", "/"],
        "wikicfp": "icnc",
        "full": "Int. Conference on Computing, Networking and Communications",
        "area": "Networking",
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).parent.parent
TODAY = date.today()
CURRENT_YEAR = TODAY.year


# ─────────────────────────────────────────────
# 日付パーサー
# ─────────────────────────────────────────────

MONTH_MAP = {
    "january":1, "february":2, "march":3, "april":4,
    "may":5, "june":6, "july":7, "august":8,
    "september":9, "october":10, "november":11, "december":12,
    "jan":1, "feb":2, "mar":3, "apr":4,
    "jun":6, "jul":7, "aug":8, "sep":9, "oct":10, "nov":11, "dec":12,
}

def parse_date(raw: str) -> str | None:
    if not raw:
        return None
    raw = raw.strip()
    # YYYY-MM-DD
    m = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # DD Month YYYY  or  Month DD, YYYY
    m = re.search(
        r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})"
        r"|([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})",
        raw,
    )
    if m:
        if m.group(1):
            day, mon_str, year = m.group(1), m.group(2), m.group(3)
        else:
            mon_str, day, year = m.group(4), m.group(5), m.group(6)
        mon = MONTH_MAP.get(mon_str.lower())
        if mon:
            return f"{year}-{mon:02d}-{int(day):02d}"
    return None


def parse_conf_dates(raw: str) -> tuple[str | None, str | None]:
    if not raw:
        return None, None
    # "May 18-21, 2026"  or  "18-21 May 2026"
    m = re.search(
        r"([A-Za-z]+)\s+(\d{1,2})\s*[-–]\s*(\d{1,2}),?\s+(\d{4})"
        r"|(\d{1,2})\s*[-–]\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})",
        raw,
    )
    if m:
        if m.group(1):
            mon_str, d1, d2, y = m.group(1), m.group(2), m.group(3), m.group(4)
        else:
            d1, d2, mon_str, y = m.group(5), m.group(6), m.group(7), m.group(8)
        mon = MONTH_MAP.get(mon_str.lower())
        if mon:
            return f"{y}-{mon:02d}-{int(d1):02d}", f"{y}-{mon:02d}-{int(d2):02d}"
    # "May 18 - June 2, 2026"
    m = re.search(
        r"([A-Za-z]+)\s+(\d{1,2})\s*[-–]\s*([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})",
        raw,
    )
    if m:
        mon1 = MONTH_MAP.get(m.group(1).lower())
        mon2 = MONTH_MAP.get(m.group(3).lower())
        y = m.group(5)
        if mon1 and mon2:
            return f"{y}-{mon1:02d}-{int(m.group(2)):02d}", f"{y}-{mon2:02d}-{int(m.group(4)):02d}"
    single = parse_date(raw)
    return single, single


# ─────────────────────────────────────────────
# 公式サイト スクレイパー
# ─────────────────────────────────────────────

# 対象セクションのキーワード（これらを含むセクションを「メイン論文トラック」とみなす）
MAIN_SECTION_KEYWORDS = [
    "symposium paper", "technical paper", "regular paper",
    "call for paper", "conference paper", "paper submission",
    "full paper", "research paper",
]

# スキップするセクションのキーワード
SKIP_SECTION_KEYWORDS = [
    "workshop", "tutorial", "industry", "demo", "panel",
    "poster", "doctoral", "student", "podium", "pitch",
    "exhibition", "invited", "special session",
]

# 締切を示すキーワード（優先順）
DEADLINE_KEYWORDS = [
    "paper submission",
    "submission deadline",
    "manuscript",
    "full paper",
    "abstract submission",
    "abstract deadline",
]

# 通知を示すキーワード
NOTIFICATION_KEYWORDS = [
    "notification",
    "acceptance notification",
    "paper acceptance",
    "decision",
]


def is_main_section(text: str) -> bool:
    t = text.lower()
    has_main = any(k in t for k in MAIN_SECTION_KEYWORDS)
    has_skip = any(k in t for k in SKIP_SECTION_KEYWORDS)
    return has_main and not has_skip


def extract_dates_from_page(soup: BeautifulSoup) -> dict:
    """
    ページから「主会議論文投稿締切」と「採否通知」を抽出する。

    戦略:
    1. セクション見出し（h2/h3/h4/strong）を走査
    2. "Call for Symposium Papers" 等のセクションを発見
    3. そのセクション直下のテキストから日付を抽出
    """
    result = {"deadline": None, "notification": None, "location": None, "confDate_raw": None}

    # ページ全テキストをフラットに取得（行単位）
    full_text = soup.get_text(separator="\n")
    lines = [l.strip() for l in full_text.splitlines() if l.strip()]

    # セクション境界を見つける
    # 見出しタグ候補
    section_tags = soup.find_all(
        lambda tag: tag.name in ["h1","h2","h3","h4","h5","strong","b","th","dt"]
        and len(tag.get_text(strip=True)) < 120
    )

    # 各セクション見出しとその後続テキストのペアを構築
    sections = []
    for tag in section_tags:
        heading_text = tag.get_text(strip=True)
        if not heading_text:
            continue
        # 後続兄弟要素のテキストを収集（最大 500 文字）
        body_parts = []
        for sib in tag.find_next_siblings():
            sib_text = sib.get_text(separator=" ", strip=True)
            if sib_text:
                body_parts.append(sib_text)
            if sum(len(p) for p in body_parts) > 500:
                break
            # 次のセクション見出しが来たら停止
            if sib.name in ["h2","h3","h4","h5"]:
                break
        sections.append({
            "heading": heading_text,
            "body": " ".join(body_parts),
        })

    # メインセクションから deadline / notification を抽出
    main_deadline    = None
    main_notification = None

    for sec in sections:
        heading = sec["heading"].lower()
        body    = sec["body"]

        if not is_main_section(heading + " " + body[:200]):
            continue

        log.info("    セクション発見: %s", sec["heading"][:60])

        # body 内から行を走査して日付を探す
        for line in body.split("  "):
            line = line.strip()
            ll = line.lower()

            # 締切
            if main_deadline is None:
                if any(k in ll for k in DEADLINE_KEYWORDS):
                    d = parse_date(line)
                    if d:
                        main_deadline = d
                        log.info("    締切: %s → %s", line[:80], d)

            # 通知
            if main_notification is None:
                if any(k in ll for k in NOTIFICATION_KEYWORDS):
                    d = parse_date(line)
                    if d:
                        main_notification = d
                        log.info("    通知: %s → %s", line[:80], d)

        if main_deadline:
            break  # メインセクションで取得できたら終了

    # セクション分割で取れなかった場合: ライン単位で直接スキャン
    if not main_deadline:
        log.info("    セクション抽出失敗 → 全行スキャン")
        in_skip = False
        for line in lines:
            ll = line.lower()
            # スキップセクションに入ったらフラグ
            if any(k in ll for k in SKIP_SECTION_KEYWORDS) and len(line) < 80:
                in_skip = True
            if any(k in ll for k in MAIN_SECTION_KEYWORDS) and len(line) < 80:
                in_skip = False

            if in_skip:
                continue

            if main_deadline is None and any(k in ll for k in DEADLINE_KEYWORDS):
                d = parse_date(line)
                if d:
                    main_deadline = d
                    log.info("    締切(scan): %s → %s", line[:80], d)

            if main_notification is None and any(k in ll for k in NOTIFICATION_KEYWORDS):
                d = parse_date(line)
                if d:
                    main_notification = d
                    log.info("    通知(scan): %s → %s", line[:80], d)

    result["deadline"]     = main_deadline
    result["notification"] = main_notification
    return result


def try_fetch_url(url: str) -> requests.Response | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        if r.status_code == 200:
            return r
        log.info("    [%d] %s", r.status_code, url)
    except requests.RequestException as e:
        log.info("    [ERR] %s: %s", url, e)
    return None


def scrape_official_site(target: dict) -> dict | None:
    """
    公式サイトの authors ページをスクレイプする。
    今年 → 来年 → 前年 の順で URL を試す。
    見つかったら {"deadline", "notification", "base_url"} を返す。
    """
    template = target["url_template"]
    paths    = target.get("authors_paths", ["/authors"])

    for year_delta in [0, 1, -1]:
        year = CURRENT_YEAR + year_delta
        base_url = template.replace("{year}", str(year))

        for path in paths:
            url = base_url.rstrip("/") + path
            log.info("    試行: %s", url)
            resp = try_fetch_url(url)
            if resp is None:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            dates = extract_dates_from_page(soup)

            if dates["deadline"]:
                log.info("  ✓ 公式サイト取得成功: %s", url)
                dates["base_url"] = base_url
                dates["source_url"] = url

                # 会議日程・開催地をトップページから取得
                home_resp = try_fetch_url(base_url)
                if home_resp:
                    home_soup = BeautifulSoup(home_resp.text, "html.parser")
                    conf_info = extract_conf_info(home_soup)
                    dates.update(conf_info)

                return dates

    log.info("  ✗ 公式サイト: 締切取得できず")
    return None


def extract_conf_info(soup: BeautifulSoup) -> dict:
    """
    トップページから開催日程・開催地を抽出する。
    """
    result = {"location": None, "confDate_raw": None}
    text = soup.get_text(separator="\n")
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    LOCATION_HINTS = ["venue", "location", "held in", "held at", "taking place in"]
    DATE_HINTS     = ["conference date", "conference will be held", "december", "november",
                      "october", "september", "august", "july", "june", "may"]

    for line in lines[:200]:
        ll = line.lower()
        if result["location"] is None and any(h in ll for h in LOCATION_HINTS):
            if len(line) < 100:
                result["location"] = line
        if result["confDate_raw"] is None and any(h in ll for h in DATE_HINTS):
            if re.search(r"20\d{2}", line) and len(line) < 80:
                result["confDate_raw"] = line

    return result


# ─────────────────────────────────────────────
# WikiCFP 補助スクレイパー（公式サイト失敗時）
# ─────────────────────────────────────────────

def wikicfp_fetch(keyword: str) -> dict:
    url = f"http://www.wikicfp.com/cfp/call?conference={keyword}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except requests.RequestException as e:
        log.warning("  WikiCFP 失敗 [%s]: %s", keyword, e)
        return {}

    soup = BeautifulSoup(r.text, "html.parser")
    rows = soup.select("table.oveAli tr")[1:]
    if not rows:
        return {}

    # 今年・来年のエントリを優先
    best = None
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        link = cells[0].find("a")
        if not link:
            continue
        eid = re.search(r"eventid=(\d+)", link.get("href", ""))
        if not eid:
            continue
        title = link.get_text(strip=True)
        when  = cells[1].get_text(strip=True)
        where = cells[2].get_text(strip=True)
        dl    = cells[3].get_text(strip=True)
        year_m = re.search(r"20(\d{2})", title + " " + when)
        year = int("20" + year_m.group(1)) if year_m else 0
        if year >= CURRENT_YEAR:
            dl_date = parse_date(dl)
            if dl_date and date.fromisoformat(dl_date) >= TODAY:
                best = {"event_id": eid.group(1), "where": where,
                        "when": when, "deadline_raw": dl, "year": year}
                break
    if best is None and rows:
        cells = rows[0].find_all("td")
        link  = cells[0].find("a") if cells else None
        eid   = re.search(r"eventid=(\d+)", link.get("href","")) if link else None
        if eid:
            best = {"event_id": eid.group(1),
                    "where": cells[2].get_text(strip=True) if len(cells) > 2 else "",
                    "when": cells[1].get_text(strip=True) if len(cells) > 1 else "",
                    "deadline_raw": cells[3].get_text(strip=True) if len(cells) > 3 else "",
                    "year": 0}

    if not best:
        return {}

    time.sleep(1.0)
    detail_url = f"http://www.wikicfp.com/cfp/servlet/event.showcfp?eventid={best['event_id']}"
    try:
        r2 = requests.get(detail_url, headers=HEADERS, timeout=15)
        detail_soup = BeautifulSoup(r2.text, "html.parser")
        for row in detail_soup.select("table.gg tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            label = cells[0].get_text(strip=True).lower()
            value = cells[1].get_text(strip=True)
            if "submission deadline" in label and "deadline_detail" not in best:
                best["deadline_detail"] = value
            elif "notification" in label and "notification_raw" not in best:
                best["notification_raw"] = value
            elif ("conference date" in label or "when" in label) and "when_detail" not in best:
                best["when_detail"] = value
            elif "location" in label and "where_detail" not in best:
                best["where_detail"] = value
        official_url = None
        for a in detail_soup.select("a[href^='http']"):
            href = a.get("href","")
            if "wikicfp" not in href:
                official_url = href
                break
        if official_url:
            best["official_url"] = official_url
    except Exception:
        pass

    return best


# ─────────────────────────────────────────────
# メイン処理
# ─────────────────────────────────────────────

def fetch_conference(target: dict) -> dict:
    abbr = target["abbr"]

    # ── 1. 公式サイトから取得 ──────────────────────────────────
    official = scrape_official_site(target)

    if official:
        conf_start, conf_end = parse_conf_dates(official.get("confDate_raw") or "")
        return {
            "abbr":         abbr,
            "full":         target["full"],
            "url":          official.get("base_url") or target["url_template"].replace("{year}", str(CURRENT_YEAR)),
            "area":         target["area"],
            "location":     official.get("location") or "TBD",
            "confDate":     conf_start,
            "confDateEnd":  conf_end,
            "deadline":     official["deadline"],
            "notification": official.get("notification"),
            "source":       official.get("source_url"),
            "data_source":  "official",
            "fetched_at":   datetime.utcnow().isoformat() + "Z",
        }

    # ── 2. WikiCFP にフォールバック ────────────────────────────
    log.info("  WikiCFP フォールバック: %s", target.get("wikicfp",""))
    wiki = wikicfp_fetch(target.get("wikicfp", ""))
    conf_start, conf_end = parse_conf_dates(wiki.get("when_detail") or wiki.get("when",""))

    return {
        "abbr":         abbr,
        "full":         target["full"],
        "url":          wiki.get("official_url") or target["url_template"].replace("{year}", str(CURRENT_YEAR)),
        "area":         target["area"],
        "location":     wiki.get("where_detail") or wiki.get("where") or "TBD",
        "confDate":     conf_start,
        "confDateEnd":  conf_end,
        "deadline":     parse_date(wiki.get("deadline_detail") or wiki.get("deadline_raw","")),
        "notification": parse_date(wiki.get("notification_raw","")),
        "source":       f"http://www.wikicfp.com/cfp/servlet/event.showcfp?eventid={wiki['event_id']}" if wiki.get("event_id") else None,
        "data_source":  "wikicfp" if wiki else "none",
        "fetched_at":   datetime.utcnow().isoformat() + "Z",
    }


def main():
    log.info("======== 会議情報取得開始 (%d 件) ========", len(TARGET_CONFERENCES))

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
            entry = fetch_conference(target)

            # 取得できなかったフィールドを既存データで補完
            old = existing.get(abbr, {})
            for field in ("deadline","notification","confDate","confDateEnd","location","url"):
                if not entry.get(field) and old.get(field):
                    entry[field] = old[field]
                    log.info("    補完 [%s] ← 既存データ", field)

            conferences.append(entry)
            time.sleep(2.0)

        except Exception as e:
            log.error("取得エラー [%s]: %s", abbr, e)
            entry = existing.get(abbr, {
                "abbr": abbr, "full": target["full"], "area": target["area"],
                "url": target["url_template"].replace("{year}", str(CURRENT_YEAR)),
                "location":"TBD","confDate":None,"confDateEnd":None,
                "deadline":None,"notification":None,
                "source":None,"data_source":"error",
                "fetched_at": datetime.utcnow().isoformat()+"Z",
            })
            conferences.append(entry)

    output = {
        "updated_at":  datetime.utcnow().isoformat() + "Z",
        "conferences": conferences,
    }
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("======== 完了: %d 件 ========", len(conferences))

    # サマリー表示
    log.info("─── 取得結果サマリー ───")
    for c in conferences:
        src = c.get("data_source","?")
        dl  = c.get("deadline","(なし)")
        log.info("  %-20s  %-8s  締切: %s", c["abbr"], src, dl)


if __name__ == "__main__":
    main()
