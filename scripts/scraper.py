"""
Conference Tracker Scraper  v3
==============================
優先順位:
  1. overrides.json    （手動・最優先）
  2. WikiCFP スクレイプ（自動）
  3. FALLBACK_DB       （コード内定数）
  4. 既存 JSON          （前回取得データ保持）
"""

import json
import re
import time
import logging
from datetime import datetime, date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

TARGET_CONFERENCES = [
    {"abbr": "IEEE GLOBECOM", "search": "globecom",                    "full": "IEEE Global Communications Conference",                                   "url": "https://globecom2026.ieee-globecom.org/", "area": "Communications"},
    {"abbr": "IEEE WCNC",     "search": "wcnc",                        "full": "IEEE Wireless Communications and Networking Conference",                   "url": "https://wcnc2026.ieee-wcnc.org/",         "area": "Wireless"},
    {"abbr": "IEEE ICC",      "search": "icc",                         "full": "IEEE International Conference on Communications",                          "url": "https://icc2026.ieee-icc.org/",           "area": "Communications"},
    {"abbr": "IEEE INFOCOM",  "search": "infocom",                     "full": "IEEE International Conference on Computer Communications",                 "url": "https://infocom2026.ieee-infocom.org/",   "area": "Networking"},
    {"abbr": "IEEE VTC",      "search": "vtc",                         "full": "IEEE Vehicular Technology Conference",                                     "url": "https://events.vtsociety.org/",           "area": "V2X / 5G"},
    {"abbr": "IEEE PIMRC",    "search": "pimrc",                       "full": "IEEE Int. Symposium on Personal, Indoor and Mobile Radio Communications",  "url": "https://pimrc2026.ieee-pimrc.org/",       "area": "Wireless"},
    {"abbr": "IEEE IV",       "search": "intelligent vehicles",        "full": "IEEE Intelligent Vehicles Symposium",                                      "url": "https://iv2026.ieee-iv.org/",             "area": "ITS / V2X"},
    {"abbr": "IEEE VNC",      "search": "vehicular networking",        "full": "IEEE Vehicular Networking Conference",                                     "url": "https://ieee-vnc.org/2026/",              "area": "V2X / Networking"},
    {"abbr": "IEEE ITSC",     "search": "itsc",                        "full": "IEEE Int. Conference on Intelligent Transportation Systems",               "url": "https://ieee-itsc.org/2026/",             "area": "ITS"},
    {"abbr": "ITS World Congress","search": "its world congress",      "full": "ITS World Congress",                                                       "url": "https://www.itsworldcongress.com/",       "area": "ITS"},
    {"abbr": "IEEE GCCE",     "search": "gcce",                        "full": "IEEE Global Conference on Consumer Electronics",                           "url": "https://www.ieee-gcce.org/2026/",         "area": "Consumer Electronics"},
    {"abbr": "IEEE WFIoT",    "search": "wfiot",                       "full": "IEEE World Forum on Internet of Things",                                   "url": "https://wfiot2026.iot.ieee.org/",         "area": "IoT"},
    {"abbr": "IEEE CCNC",     "search": "ccnc",                        "full": "IEEE Consumer Communications and Networking Conference",                   "url": "https://ccnc2027.ieee-ccnc.org/",         "area": "Consumer / Networking"},
    {"abbr": "IEEE CTW",      "search": "communication theory workshop","full": "IEEE Communication Theory Workshop",                                      "url": "https://ctw2026.ieee-ctw.org/",           "area": "Theory"},
    {"abbr": "APCC",          "search": "apcc",                        "full": "Asia-Pacific Conference on Communications",                                "url": "https://apcc2026.org/",                   "area": "Asia-Pacific"},
    {"abbr": "ICOIN",         "search": "icoin",                       "full": "International Conference on Information Networking",                       "url": "https://www.icoin.org/",                  "area": "Networking"},
    {"abbr": "WPMC",          "search": "wpmc",                        "full": "Int. Symposium on Wireless Personal Multimedia Communications",            "url": "https://www.wpmc-conf.org/",              "area": "Wireless"},
    {"abbr": "ICETC",         "search": "icetc",                       "full": "Int. Conference on Emerging Technologies for Communications",              "url": "https://www.ieice.org/cs/icetc/",         "area": "Emerging Tech"},
    {"abbr": "ICNC",          "search": "icnc",                        "full": "Int. Conference on Computing, Networking and Communications",              "url": "https://www.conf-icnc.org/",              "area": "Networking"},
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


# ─────────────────────────────────────────────
# overrides.json 読み込み
# ─────────────────────────────────────────────

def load_overrides() -> dict:
    path = REPO_ROOT / "overrides.json"
    if not path.exists():
        log.info("overrides.json が見つかりません（スキップ）")
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        # _comment など _ 始まりのキーを除外
        return {k: v for k, v in data.items() if not k.startswith("_")}
    except Exception as e:
        log.warning("overrides.json 読み込み失敗: %s", e)
        return {}


def apply_override(entry: dict, override: dict) -> dict:
    """override の非 null フィールドで entry を上書きする。"""
    for field, value in override.items():
        if value is not None:
            entry[field] = value
    return entry


# ─────────────────────────────────────────────
# WikiCFP スクレイパー
# ─────────────────────────────────────────────

def wikicfp_call_list(keyword: str) -> list[dict]:
    url = f"http://www.wikicfp.com/cfp/call?conference={keyword}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except requests.RequestException as e:
        log.warning("  WikiCFP 検索失敗 [%s]: %s", keyword, e)
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
        eid = re.search(r"eventid=(\d+)", href)
        if not eid:
            continue
        title = link_tag.get_text(strip=True)
        when  = cells[1].get_text(strip=True)
        year_m = re.search(r"20(\d{2})", title + " " + when)
        year = int("20" + year_m.group(1)) if year_m else 0
        results.append({
            "event_id": eid.group(1),
            "title":    title,
            "when":     when,
            "where":    cells[2].get_text(strip=True),
            "deadline": cells[3].get_text(strip=True),
            "year":     year,
        })

    results.sort(key=lambda x: x["year"], reverse=True)
    return results


def wikicfp_detail(event_id: str) -> dict:
    url = f"http://www.wikicfp.com/cfp/servlet/event.showcfp?eventid={event_id}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except requests.RequestException as e:
        log.warning("  WikiCFP 詳細失敗 [%s]: %s", event_id, e)
        return {}

    soup = BeautifulSoup(r.text, "html.parser")
    info = {}

    h1 = soup.find("h1")
    if h1:
        info["full"] = h1.get_text(strip=True)

    for a in soup.select("a[href^='http']"):
        href = a.get("href", "")
        if "wikicfp" not in href and "." in href:
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
        elif "abstract" in label and "deadline_raw" not in info:
            info["deadline_raw"] = value
        elif "notification" in label:
            info["notification_raw"] = value
        elif "conference date" in label or ("when" in label and "confDate_raw" not in info):
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
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})", raw)
    if m:
        mon = MONTH_MAP.get(m.group(1)[:3].lower())
        if mon:
            return f"{m.group(3)}-{mon:02d}-{int(m.group(2)):02d}"
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})", raw)
    if m:
        mon = MONTH_MAP.get(m.group(2)[:3].lower())
        if mon:
            return f"{m.group(3)}-{mon:02d}-{int(m.group(1)):02d}"
    return None


def parse_conf_dates(raw):
    if not raw:
        return None, None
    m = re.search(r"([A-Za-z]{3,9})\.?\s+(\d{1,2})\s*[-–]\s*(\d{1,2}),?\s+(\d{4})", raw)
    if m:
        mon = MONTH_MAP.get(m.group(1)[:3].lower())
        if mon:
            y = m.group(4)
            return f"{y}-{mon:02d}-{int(m.group(2)):02d}", f"{y}-{mon:02d}-{int(m.group(3)):02d}"
    m = re.search(r"([A-Za-z]{3,9})\.?\s+(\d{1,2})\s*[-–]\s*([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})", raw)
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
# ─────────────────────────────────────────────

def select_best_candidate(candidates: list[dict]) -> dict | None:
    today = date.today()
    cy = today.year
    # 締切が未来 かつ 今年・来年 を優先
    for yr in [cy, cy + 1]:
        for c in candidates:
            if c["year"] != yr:
                continue
            dl = parse_date(c.get("deadline"))
            if dl and date.fromisoformat(dl) >= today:
                return c
    # 締切過去でも今年・来年なら採用
    for yr in [cy, cy + 1]:
        for c in candidates:
            if c["year"] == yr:
                return c
    return candidates[0] if candidates else None


# ─────────────────────────────────────────────
# メイン処理
# ─────────────────────────────────────────────

def fetch_conference(target: dict) -> dict:
    keyword = target["search"]
    abbr    = target["abbr"]

    candidates = wikicfp_call_list(keyword)
    best = select_best_candidate(candidates) if candidates else None

    if best:
        log.info("  WikiCFP: %s (year=%s)", best["title"], best["year"])
        time.sleep(1.0)
        detail = wikicfp_detail(best["event_id"])
        conf_start, conf_end = parse_conf_dates(detail.get("confDate_raw") or best.get("when"))
        source = f"http://www.wikicfp.com/cfp/servlet/event.showcfp?eventid={best['event_id']}"
        data_source = "wikicfp"
    else:
        log.info("  WikiCFP: 候補なし")
        detail = {}
        conf_start = conf_end = None
        source = None
        data_source = "fallback"

    entry = {
        "abbr":         abbr,
        "full":         detail.get("full") or target.get("full", ""),
        "url":          detail.get("url")  or target.get("url", ""),
        "area":         target.get("area", ""),
        "location":     detail.get("location") or (best.get("where") if best else None) or "TBD",
        "confDate":     conf_start,
        "confDateEnd":  conf_end,
        "deadline":     parse_date(detail.get("deadline_raw")) or (parse_date(best.get("deadline")) if best else None),
        "notification": parse_date(detail.get("notification_raw")),
        "source":       source,
        "data_source":  data_source,
        "fetched_at":   datetime.utcnow().isoformat() + "Z",
    }
    return entry


def main():
    log.info("======== 会議情報取得開始 (%d 件) ========", len(TARGET_CONFERENCES))

    # overrides.json 読み込み
    overrides = load_overrides()
    log.info("overrides.json: %d 件の上書き設定", len(overrides))

    # 既存 conferences.json 読み込み
    output_path = REPO_ROOT / "conferences.json"
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
        abbr = target["abbr"]
        log.info("[%d/%d] %s", i, len(TARGET_CONFERENCES), abbr)

        try:
            entry = fetch_conference(target)

            # 取得できなかったフィールドを既存データで補完
            old = existing.get(abbr, {})
            for field in ("deadline", "notification", "confDate", "confDateEnd", "location", "url", "full"):
                if not entry.get(field) and old.get(field):
                    entry[field] = old[field]
                    log.info("    補完 [%s] ← 既存データ", field)

            # overrides.json で上書き（最優先）
            if abbr in overrides:
                entry = apply_override(entry, overrides[abbr])
                entry["data_source"] = "manual"
                log.info("    ✓ overrides.json 適用")

            conferences.append(entry)
            time.sleep(1.5)

        except Exception as e:
            log.error("取得エラー [%s]: %s", abbr, e)
            # エラー時: overrides → 既存データ の順で保持
            fallback_entry = _build_fallback(target)
            if abbr in overrides:
                fallback_entry = apply_override(fallback_entry, overrides[abbr])
                fallback_entry["data_source"] = "manual"
            elif abbr in existing:
                fallback_entry = existing[abbr]
            conferences.append(fallback_entry)

    output = {
        "updated_at":  datetime.utcnow().isoformat() + "Z",
        "conferences": conferences,
    }
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("======== 完了: %d 件 → %s ========", len(conferences), output_path)


def _build_fallback(target: dict) -> dict:
    return {
        "abbr": target["abbr"], "full": target.get("full", ""),
        "url": target.get("url", ""), "area": target.get("area", ""),
        "location": "TBD", "confDate": None, "confDateEnd": None,
        "deadline": None, "notification": None,
        "source": None, "data_source": "fallback",
        "fetched_at": datetime.utcnow().isoformat() + "Z",
    }


if __name__ == "__main__":
    main()
