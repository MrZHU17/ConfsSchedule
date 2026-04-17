"""
Conference Tracker Scraper  v2
==============================
WikiCFP から会議情報を取得し conferences.json に書き出す。

修正点:
- WikiCFP URL を /cfp/call?conference= に変更（year=f 廃止対応）
- 現在年度 → 前年度 の優先ロジックを追加
- 取得失敗時のハードコード fallback DB を追加
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
# 追跡会議リスト
# ─────────────────────────────────────────────
TARGET_CONFERENCES = [
    # ── 通信・ネットワーク フラッグシップ ──────────────────────────
    {"abbr": "IEEE GLOBECOM", "search": "globecom",   "full": "IEEE Global Communications Conference",                                            "url": "https://globecom2026.ieee-globecom.org/", "area": "Communications"},
    {"abbr": "IEEE WCNC",     "search": "wcnc",       "full": "IEEE Wireless Communications and Networking Conference",                            "url": "https://wcnc2026.ieee-wcnc.org/",         "area": "Wireless"},
    {"abbr": "IEEE ICC",      "search": "icc",        "full": "IEEE International Conference on Communications",                                   "url": "https://icc2026.ieee-icc.org/",           "area": "Communications"},
    {"abbr": "IEEE INFOCOM",  "search": "infocom",    "full": "IEEE International Conference on Computer Communications",                          "url": "https://infocom2026.ieee-infocom.org/",   "area": "Networking"},
    {"abbr": "IEEE VTC",      "search": "vtc",        "full": "IEEE Vehicular Technology Conference",                                             "url": "https://events.vtsociety.org/",           "area": "V2X / 5G"},
    {"abbr": "IEEE PIMRC",    "search": "pimrc",      "full": "IEEE Int. Symposium on Personal, Indoor and Mobile Radio Communications",           "url": "https://pimrc2026.ieee-pimrc.org/",       "area": "Wireless"},
    # ── 車両・ITS・V2X ──────────────────────────────────────────────
    {"abbr": "IEEE IV",       "search": "intelligent vehicles symposium", "full": "IEEE Intelligent Vehicles Symposium",                           "url": "https://iv2026.ieee-iv.org/",             "area": "ITS / V2X"},
    {"abbr": "IEEE VNC",      "search": "vehicular networking conference","full": "IEEE Vehicular Networking Conference",                           "url": "https://www.ieeevnc.org/",                "area": "V2X / Networking"},
    {"abbr": "IEEE ITSC",     "search": "itsc",       "full": "IEEE Int. Conference on Intelligent Transportation Systems",                        "url": "https://ieee-itsc.org/",                  "area": "ITS"},
    {"abbr": "ITS World Congress","search": "its world congress","full": "ITS World Congress",                                                    "url": "https://www.itsworldcongress.org/",       "area": "ITS"},
    # ── コンシューマ・IoT ───────────────────────────────────────────
    {"abbr": "IEEE GCCE",     "search": "gcce",       "full": "IEEE Global Conference on Consumer Electronics",                                   "url": "https://www.ieee-gcce.org/",              "area": "Consumer Electronics"},
    {"abbr": "IEEE WFIoT",    "search": "wfiot",      "full": "IEEE World Forum on Internet of Things",                                           "url": "https://wfiot2025.iot.ieee.org/",         "area": "IoT"},
    {"abbr": "IEEE CCNC",     "search": "ccnc",       "full": "IEEE Consumer Communications and Networking Conference",                            "url": "https://ccnc2026.ieee-ccnc.org/",         "area": "Consumer / Networking"},
    # ── 理論・ワークショップ ────────────────────────────────────────
    {"abbr": "IEEE CTW",      "search": "communication theory workshop","full": "IEEE Communication Theory Workshop",                              "url": "https://ctw2025.ieee-ctw.org/",           "area": "Theory"},
    # ── アジア太平洋・地域 ──────────────────────────────────────────
    {"abbr": "APCC",          "search": "apcc",       "full": "Asia-Pacific Conference on Communications",                                        "url": "https://apcc2025.org/",                   "area": "Asia-Pacific"},
    {"abbr": "ICOIN",         "search": "icoin",      "full": "International Conference on Information Networking",                               "url": "https://www.icoin.org/",                  "area": "Networking"},
    {"abbr": "WPMC",          "search": "wpmc",       "full": "Int. Symposium on Wireless Personal Multimedia Communications",                    "url": "https://www.wpmc-conf.org/",              "area": "Wireless"},
    {"abbr": "ICETC",         "search": "icetc",      "full": "International Conference on Emerging Technologies for Communications",             "url": "https://www.ieice.org/cs/icetc/",         "area": "Emerging Tech"},
    # ── 北米・一般 ──────────────────────────────────────────────────
    {"abbr": "ICNC",          "search": "icnc",       "full": "International Conference on Computing, Networking and Communications",             "url": "https://www.conf-icnc.org/",              "area": "Networking"},
]

# ─────────────────────────────────────────────
# 主要会議のハードコード fallback DB
# WikiCFP で取得できなかった場合に使用
# ─────────────────────────────────────────────
FALLBACK_DB = {
    "IEEE GLOBECOM": {
        "location": "Cape Town, South Africa",
        "confDate": "2026-12-07", "confDateEnd": "2026-12-11",
        "deadline": "2026-05-11", "notification": "2026-08-22",
    },
    "IEEE WCNC": {
        "location": "Milan, Italy",
        "confDate": "2026-03-24", "confDateEnd": "2026-03-27",
        "deadline": "2025-09-15", "notification": "2025-12-20",
    },
    "IEEE ICC": {
        "location": "Glasgow, UK",
        "confDate": "2026-06-01", "confDateEnd": "2026-06-05",
        "deadline": "2025-10-15", "notification": "2026-01-20",
    },
    "IEEE INFOCOM": {
        "location": "London, UK",
        "confDate": "2026-05-18", "confDateEnd": "2026-05-21",
        "deadline": "2025-07-24", "notification": "2025-12-01",
    },
    "IEEE VTC": {
        "location": "Tokyo, Japan",
        "confDate": "2026-10-05", "confDateEnd": "2026-10-08",
        "deadline": "2026-05-01", "notification": "2026-07-15",
    },
    "IEEE PIMRC": {
        "location": "TBD",
        "confDate": "2026-09-01", "confDateEnd": "2026-09-04",
        "deadline": "2026-04-15", "notification": "2026-06-30",
    },
    "IEEE GCCE": {
        "location": "Osaka, Japan",
        "confDate": "2026-10-20", "confDateEnd": "2026-10-23",
        "deadline": "2026-06-01", "notification": "2026-08-01",
    },
    "IEEE CCNC": {
        "location": "Las Vegas, USA",
        "confDate": "2027-01-10", "confDateEnd": "2027-01-13",
        "deadline": "2026-07-15", "notification": "2026-10-01",
    },
    "IEEE ITSC": {
        "location": "TBD",
        "confDate": "2026-09-20", "confDateEnd": "2026-09-24",
        "deadline": "2026-03-31", "notification": "2026-06-15",
    },
    "IEEE IV": {
        "location": "TBD",
        "confDate": "2026-06-15", "confDateEnd": "2026-06-18",
        "deadline": "2026-02-28", "notification": "2026-04-30",
    },
    "IEEE VNC": {
        "location": "TBD",
        "confDate": "2026-11-01", "confDateEnd": "2026-11-03",
        "deadline": "2026-07-01", "notification": "2026-09-01",
    },
    "ICNC": {
        "location": "Hawaii, USA",
        "confDate": "2027-02-17", "confDateEnd": "2027-02-20",
        "deadline": "2026-08-01", "notification": "2026-10-15",
    },
}

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

CURRENT_YEAR = datetime.utcnow().year


# ─────────────────────────────────────────────
# WikiCFP スクレイパー（修正版）
# URL: /cfp/call?conference=<keyword>
# ─────────────────────────────────────────────

def wikicfp_call_list(keyword: str) -> list[dict]:
    """
    WikiCFP の /cfp/call?conference= エンドポイントを使って
    会議一覧を取得する。年度の新しい順に返す。
    """
    url = f"http://www.wikicfp.com/cfp/call?conference={keyword}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except requests.RequestException as e:
        log.warning("WikiCFP call list 失敗 [%s]: %s", keyword, e)
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    results = []

    for row in soup.select("table.oveAli tr")[1:]:
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        link_tag = cells[0].find("a")
        if not link_tag:
            continue
        href = link_tag.get("href", "")
        event_id_m = re.search(r"eventid=(\d+)", href)
        if not event_id_m:
            continue

        title = link_tag.get_text(strip=True)
        when  = cells[1].get_text(strip=True)
        where = cells[2].get_text(strip=True)
        dl    = cells[3].get_text(strip=True)

        # タイトルに年が含まれていれば抽出
        year_m = re.search(r"20(\d{2})", title + " " + when)
        year = int("20" + year_m.group(1)) if year_m else 0

        results.append({
            "event_id": event_id_m.group(1),
            "title":    title,
            "when":     when,
            "where":    where,
            "deadline": dl,
            "year":     year,
        })

    # 年度の新しい順にソート
    results.sort(key=lambda x: x["year"], reverse=True)
    return results


def wikicfp_detail(event_id: str) -> dict:
    """WikiCFP イベント詳細ページから情報を取得する。"""
    url = f"http://www.wikicfp.com/cfp/servlet/event.showcfp?eventid={event_id}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except requests.RequestException as e:
        log.warning("詳細取得失敗 [%s]: %s", event_id, e)
        return {}

    soup = BeautifulSoup(r.text, "html.parser")
    info = {}

    h1 = soup.find("h1")
    if h1:
        info["full"] = h1.get_text(strip=True)

    for a in soup.select("span.conURL a, a[href^='http']"):
        href = a.get("href", "")
        if href.startswith("http") and "wikicfp" not in href:
            info["url"] = href
            break

    for row in soup.select("table.gg tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        label = cells[0].get_text(strip=True).lower()
        value = cells[1].get_text(strip=True)

        if "submission deadline" in label:
            info["deadline_raw"] = value
        elif "abstract" in label and "deadline" in label:
            if "deadline_raw" not in info:
                info["deadline_raw"] = value
        elif "notification" in label:
            info["notification_raw"] = value
        elif "conference date" in label or "when" in label:
            info["confDate_raw"] = value
        elif "location" in label or "where" in label:
            info["location"] = value

    return info


# ─────────────────────────────────────────────
# 日付パーサー
# ─────────────────────────────────────────────

MONTH_MAP = {
    "jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
    "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
}

def parse_date(raw):
    if not raw:
        return None
    raw = raw.strip()
    # YYYY-MM-DD
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # Month DD, YYYY
    m = re.search(r"([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})", raw)
    if m:
        mon = MONTH_MAP.get(m.group(1)[:3].lower())
        if mon:
            return f"{m.group(3)}-{mon:02d}-{int(m.group(2)):02d}"
    # DD Month YYYY
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})", raw)
    if m:
        mon = MONTH_MAP.get(m.group(2)[:3].lower())
        if mon:
            return f"{m.group(3)}-{mon:02d}-{int(m.group(1)):02d}"
    return None


def parse_conf_dates(raw):
    if not raw:
        return None, None
    # "May 18-21, 2026"
    m = re.search(
        r"([A-Za-z]{3,9})\.?\s+(\d{1,2})\s*[-–]\s*(\d{1,2}),?\s+(\d{4})", raw
    )
    if m:
        mon = MONTH_MAP.get(m.group(1)[:3].lower())
        if mon:
            y = m.group(4)
            return f"{y}-{mon:02d}-{int(m.group(2)):02d}", f"{y}-{mon:02d}-{int(m.group(3)):02d}"
    # "May 18 - Jun 2, 2026"
    m = re.search(
        r"([A-Za-z]{3,9})\.?\s+(\d{1,2})\s*[-–]\s*([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})", raw
    )
    if m:
        mon1 = MONTH_MAP.get(m.group(1)[:3].lower())
        mon2 = MONTH_MAP.get(m.group(3)[:3].lower())
        y = m.group(5)
        if mon1 and mon2:
            return f"{y}-{mon1:02d}-{int(m.group(2)):02d}", f"{y}-{mon2:02d}-{int(m.group(4)):02d}"
    single = parse_date(raw)
    return single, single


# ─────────────────────────────────────────────
# 年度選択ロジック
# 優先順: 今年 → 来年 → 前年 （締切が未来のものを優先）
# ─────────────────────────────────────────────

def select_best_candidate(candidates: list[dict]) -> dict | None:
    today = date.today()
    current_year = today.year

    # 締切が未来 かつ 現在年度以降のものを優先
    for preferred_year in [current_year, current_year + 1, current_year - 1]:
        for cand in candidates:
            if cand["year"] != preferred_year:
                continue
            dl = parse_date(cand.get("deadline"))
            if dl and date.fromisoformat(dl) >= today:
                return cand

    # 締切が過去でも現在年度以降なら採用
    for preferred_year in [current_year, current_year + 1]:
        for cand in candidates:
            if cand["year"] == preferred_year:
                return cand

    # 最後の手段：最新年度の最初の候補
    return candidates[0] if candidates else None


# ─────────────────────────────────────────────
# メイン処理
# ─────────────────────────────────────────────

def fetch_conference(target: dict) -> dict:
    keyword = target["search"]
    log.info("検索中: %s (keyword=%s)", target["abbr"], keyword)

    candidates = wikicfp_call_list(keyword)

    if not candidates:
        log.warning("  WikiCFP: 候補なし → fallback DB 使用")
        return _build_entry(target, {}, None)

    best = select_best_candidate(candidates)
    if best is None:
        return _build_entry(target, {}, None)

    log.info("  → 選択: %s (year=%s, event_id=%s)", best["title"], best["year"], best["event_id"])
    time.sleep(1.2)

    detail = wikicfp_detail(best["event_id"])
    conf_start, conf_end = parse_conf_dates(detail.get("confDate_raw") or best.get("when"))

    return _build_entry(target, detail, best, conf_start, conf_end)


def _build_entry(target, detail, best, conf_start=None, conf_end=None):
    abbr = target["abbr"]
    fb = FALLBACK_DB.get(abbr, {})

    location = (
        detail.get("location")
        or (best.get("where") if best else None)
        or fb.get("location", "TBD")
    )
    deadline = (
        parse_date(detail.get("deadline_raw"))
        or (parse_date(best.get("deadline")) if best else None)
        or fb.get("deadline")
    )
    notification = (
        parse_date(detail.get("notification_raw"))
        or fb.get("notification")
    )
    conf_start = conf_start or fb.get("confDate")
    conf_end   = conf_end   or fb.get("confDateEnd")

    source = None
    if best:
        source = f"http://www.wikicfp.com/cfp/servlet/event.showcfp?eventid={best['event_id']}"

    return {
        "abbr":         abbr,
        "full":         detail.get("full") or target.get("full", ""),
        "url":          detail.get("url")  or target.get("url", ""),
        "area":         target.get("area", ""),
        "location":     location,
        "confDate":     conf_start,
        "confDateEnd":  conf_end,
        "deadline":     deadline,
        "notification": notification,
        "source":       source,
        "fetched_at":   datetime.utcnow().isoformat() + "Z",
    }


def main():
    log.info("======== 会議情報取得開始 (%d 件) ========", len(TARGET_CONFERENCES))

    output_path = Path(__file__).parent.parent / "conferences.json"
    existing = {}
    if output_path.exists():
        try:
            old = json.loads(output_path.read_text(encoding="utf-8"))
            old_list = old.get("conferences", old) if isinstance(old, dict) else old
            existing = {c["abbr"]: c for c in old_list if isinstance(c, dict)}
            log.info("既存データ読み込み: %d 件", len(existing))
        except Exception as e:
            log.warning("既存データ読み込み失敗: %s", e)

    conferences = []
    for i, target in enumerate(TARGET_CONFERENCES, 1):
        log.info("[%d/%d] %s", i, len(TARGET_CONFERENCES), target["abbr"])
        try:
            entry = fetch_conference(target)

            # WikiCFP + fallback DB でも取得できなかったフィールドは既存データで補完
            old = existing.get(target["abbr"], {})
            for field in ("deadline", "notification", "confDate", "confDateEnd", "location", "url"):
                if not entry.get(field) and old.get(field):
                    entry[field] = old[field]
                    log.info("    補完 [%s] ← 既存データ", field)

            conferences.append(entry)
            time.sleep(1.5)

        except Exception as e:
            log.error("取得エラー [%s]: %s", target["abbr"], e)
            if target["abbr"] in existing:
                conferences.append(existing[target["abbr"]])
                log.info("    既存データを維持: %s", target["abbr"])
            else:
                conferences.append(_build_entry(target, {}, None))

    output = {
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "conferences": conferences,
    }

    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("======== 完了: %d 件 → %s ========", len(conferences), output_path)


if __name__ == "__main__":
    main()
