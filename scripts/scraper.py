"""
Conference Tracker Scraper
==========================
WikiCFP から指定した会議の投稿締切・開催情報を取得し、
conferences.json に書き出す。
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

    # ── 通信・ネットワーク 主要フラッグシップ ──────────────────────────
    {
        "abbr": "IEEE GLOBECOM",
        "search": "GLOBECOM",
        "full": "IEEE Global Communications Conference",
        "url": "https://globecom2025.ieee-globecom.org/",
        "area": "Communications",
    },
    {
        "abbr": "IEEE WCNC",
        "search": "WCNC",
        "full": "IEEE Wireless Communications and Networking Conference",
        "url": "https://wcnc2026.ieee-wcnc.org/",
        "area": "Wireless",
    },
    {
        "abbr": "IEEE ICC",
        "search": "ICC",
        "full": "IEEE International Conference on Communications",
        "url": "https://icc2026.ieee-icc.org/",
        "area": "Communications",
    },
    {
        "abbr": "IEEE INFOCOM",
        "search": "INFOCOM",
        "full": "IEEE International Conference on Computer Communications",
        "url": "https://infocom2026.ieee-infocom.org/",
        "area": "Networking",
    },
    {
        "abbr": "IEEE VTC",
        "search": "VTC",
        "full": "IEEE Vehicular Technology Conference",
        "url": "https://events.vtsociety.org/",
        "area": "V2X / 5G",
    },
    {
        "abbr": "IEEE PIMRC",
        "search": "PIMRC",
        "full": "IEEE International Symposium on Personal, Indoor and Mobile Radio Communications",
        "url": "https://pimrc2025.ieee-pimrc.org/",
        "area": "Wireless",
    },

    # ── 車両・ITS・V2X ─────────────────────────────────────────────────
    {
        "abbr": "IEEE IV",
        "search": "Intelligent Vehicles Symposium",
        "full": "IEEE Intelligent Vehicles Symposium",
        "url": "https://iv2025.ieee-iv.org/",
        "area": "ITS / V2X",
    },
    {
        "abbr": "IEEE VNC",
        "search": "Vehicular Networking Conference",
        "full": "IEEE Vehicular Networking Conference",
        "url": "https://www.ieeevnc.org/",
        "area": "V2X / Networking",
    },
    {
        "abbr": "IEEE ITSC",
        "search": "ITSC",
        "full": "IEEE International Conference on Intelligent Transportation Systems",
        "url": "https://ieee-itsc.org/",
        "area": "ITS",
    },
    {
        "abbr": "ITS World Congress",
        "search": "ITS World Congress",
        "full": "ITS World Congress",
        "url": "https://www.itsworldcongress.org/",
        "area": "ITS",
    },

    # ── コンシューマエレクトロニクス・IoT ─────────────────────────────
    {
        "abbr": "IEEE GCCE",
        "search": "GCCE",
        "full": "IEEE Global Conference on Consumer Electronics",
        "url": "https://www.ieee-gcce.org/",
        "area": "Consumer Electronics",
    },
    {
        "abbr": "IEEE WFIoT",
        "search": "WFIoT",
        "full": "IEEE World Forum on Internet of Things",
        "url": "https://wfiot2025.iot.ieee.org/",
        "area": "IoT",
    },
    {
        "abbr": "IEEE CCNC",
        "search": "CCNC",
        "full": "IEEE Consumer Communications and Networking Conference",
        "url": "https://ccnc2026.ieee-ccnc.org/",
        "area": "Consumer / Networking",
    },

    # ── 理論・ワークショップ ───────────────────────────────────────────
    {
        "abbr": "IEEE CTW",
        "search": "Communication Theory Workshop",
        "full": "IEEE Communication Theory Workshop",
        "url": "https://ctw2025.ieee-ctw.org/",
        "area": "Theory",
    },

    # ── アジア太平洋・地域会議 ────────────────────────────────────────
    {
        "abbr": "APCC",
        "search": "APCC",
        "full": "Asia-Pacific Conference on Communications",
        "url": "https://apcc2025.org/",
        "area": "Asia-Pacific",
    },
    {
        "abbr": "ICOIN",
        "search": "ICOIN",
        "full": "International Conference on Information Networking",
        "url": "https://www.icoin.org/",
        "area": "Networking",
    },
    {
        "abbr": "WPMC",
        "search": "WPMC",
        "full": "International Symposium on Wireless Personal Multimedia Communications",
        "url": "https://www.wpmc-conf.org/",
        "area": "Wireless",
    },
    {
        "abbr": "ICETC",
        "search": "ICETC",
        "full": "International Conference on Emerging Technologies for Communications",
        "url": "https://www.ieice.org/cs/icetc/",
        "area": "Emerging Technologies",
    },

    # ── 北米・一般 ────────────────────────────────────────────────────
    {
        "abbr": "ICNC",
        "search": "ICNC",
        "full": "International Conference on Computing, Networking and Communications",
        "url": "https://www.conf-icnc.org/",
        "area": "Networking",
    },
]

WIKICFP_SEARCH = "http://www.wikicfp.com/cfp/search"
WIKICFP_EVENT  = "http://www.wikicfp.com/cfp/servlet/event.showcfp"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; ConferenceTrackerBot/1.0; "
        "+https://github.com/MrZHU17/ConfsSchedule)"
    )
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def wikicfp_search(keyword: str, max_results: int = 8) -> list[dict]:
    try:
        r = requests.get(
            WIKICFP_SEARCH,
            params={"q": keyword, "year": "f"},
            headers=HEADERS,
            timeout=15,
        )
        r.raise_for_status()
    except requests.RequestException as e:
        log.warning("検索失敗 [%s]: %s", keyword, e)
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    results = []

    for row in soup.select("table.oveAli tr")[1:max_results + 1]:
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        link_tag = cells[0].find("a")
        if not link_tag:
            continue
        href = link_tag.get("href", "")
        event_id = re.search(r"eventid=(\d+)", href)
        if not event_id:
            continue
        results.append({
            "event_id": event_id.group(1),
            "title": link_tag.get_text(strip=True),
            "when": cells[1].get_text(strip=True),
            "where": cells[2].get_text(strip=True),
            "deadline": cells[3].get_text(strip=True),
        })

    return results


def wikicfp_detail(event_id: str) -> dict:
    try:
        r = requests.get(
            WIKICFP_EVENT,
            params={"eventid": event_id},
            headers=HEADERS,
            timeout=15,
        )
        r.raise_for_status()
    except requests.RequestException as e:
        log.warning("詳細取得失敗 [event_id=%s]: %s", event_id, e)
        return {}

    soup = BeautifulSoup(r.text, "html.parser")
    info = {}

    h1 = soup.find("h1")
    if h1:
        info["full"] = h1.get_text(strip=True)

    link_tags = soup.select("span.conURL a")
    if link_tags:
        info["url"] = link_tags[0]["href"]

    for row in soup.select("table.gg tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        label = cells[0].get_text(strip=True).lower()
        value = cells[1].get_text(strip=True)

        if "submission deadline" in label or "abstract" in label:
            info["deadline_raw"] = value
        elif "notification" in label:
            info["notification_raw"] = value
        elif "conference date" in label or "when" in label:
            info["confDate_raw"] = value
        elif "location" in label or "where" in label:
            info["location"] = value

    return info


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
    m = re.search(
        r"(?:(\d{1,2})\s+)?([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})",
        raw,
    )
    if m:
        day_pre, month_str, day, year = m.groups()
        day = day_pre if day_pre else day
        mon = MONTH_MAP.get(month_str[:3].lower())
        if mon:
            return f"{year}-{mon:02d}-{int(day):02d}"
    return None


def parse_conf_dates(raw):
    if not raw:
        return None, None
    m = re.search(
        r"([A-Za-z]{3,9})\.?\s+(\d{1,2})\s*[-–]\s*(\d{1,2}),?\s+(\d{4})",
        raw,
    )
    if m:
        mon_str, day_start, day_end, year = m.groups()
        mon = MONTH_MAP.get(mon_str[:3].lower())
        if mon:
            return (
                f"{year}-{mon:02d}-{int(day_start):02d}",
                f"{year}-{mon:02d}-{int(day_end):02d}",
            )
    single = parse_date(raw)
    return single, single


def fetch_conference(target: dict) -> dict:
    keyword = target["search"]
    log.info("検索中: %s", keyword)

    candidates = wikicfp_search(keyword, max_results=8)
    if not candidates:
        log.warning("候補なし: %s", keyword)
        return _fallback(target)

    today = date.today()
    best = None
    for cand in candidates:
        if keyword.split()[0].lower() not in cand["title"].lower():
            continue
        dl_str = parse_date(cand.get("deadline"))
        if dl_str and date.fromisoformat(dl_str) > today:
            best = cand
            break

    if best is None:
        best = candidates[0]

    log.info("  → 選択: %s (event_id=%s)", best["title"], best["event_id"])
    time.sleep(1.2)

    detail = wikicfp_detail(best["event_id"])
    conf_start, conf_end = parse_conf_dates(
        detail.get("confDate_raw") or best.get("when")
    )

    return {
        "abbr":         target["abbr"],
        "full":         detail.get("full") or target.get("full", ""),
        "url":          detail.get("url") or target.get("url", ""),
        "area":         target.get("area", ""),
        "location":     detail.get("location") or best.get("where", "TBD"),
        "confDate":     conf_start,
        "confDateEnd":  conf_end,
        "deadline":     parse_date(detail.get("deadline_raw")) or parse_date(best.get("deadline")),
        "notification": parse_date(detail.get("notification_raw")),
        "source":       f"https://www.wikicfp.com/cfp/servlet/event.showcfp?eventid={best['event_id']}",
        "fetched_at":   datetime.utcnow().isoformat() + "Z",
    }


def _fallback(target: dict) -> dict:
    return {
        "abbr":         target["abbr"],
        "full":         target.get("full", ""),
        "url":          target.get("url", ""),
        "area":         target.get("area", ""),
        "location":     "TBD",
        "confDate":     None,
        "confDateEnd":  None,
        "deadline":     None,
        "notification": None,
        "source":       None,
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
            old = existing.get(target["abbr"], {})
            for field in ("deadline", "notification", "confDate", "confDateEnd", "location"):
                if not entry.get(field) and old.get(field):
                    entry[field] = old[field]
                    log.info("    補完 [%s] ← 既存データ", field)
            conferences.append(entry)
            time.sleep(1.5)
        except Exception as e:
            log.error("取得エラー [%s]: %s", target["abbr"], e)
            if target["abbr"] in existing:
                conferences.append(existing[target["abbr"]])
            else:
                conferences.append(_fallback(target))

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
