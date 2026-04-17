"""
Conference Tracker Scraper
==========================
WikiCFP から指定した会議の投稿締切・開催情報を取得し、
conferences.json に書き出す。

使い方:
    pip install requests beautifulsoup4
    python scripts/scraper.py
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
# 追跡したい会議リスト
# abbr     : 表示名（略称）
# search   : WikiCFP の検索キーワード
# full     : 正式名称（WikiCFP から取得できない場合の fallback）
# url      : 公式サイト（WikiCFP から取得できない場合の fallback）
# area     : 研究分野タグ
# ─────────────────────────────────────────────
TARGET_CONFERENCES = [
    {
        "abbr": "INFOCOM",
        "search": "INFOCOM",
        "full": "IEEE International Conference on Computer Communications",
        "url": "https://infocom2026.ieee-infocom.org/",
        "area": "Networking",
    },
    {
        "abbr": "GLOBECOM",
        "search": "GLOBECOM",
        "full": "IEEE Global Communications Conference",
        "url": "https://globecom2026.ieee-globecom.org/",
        "area": "Communications",
    },
    {
        "abbr": "VTC",
        "search": "VTC",
        "full": "IEEE Vehicular Technology Conference",
        "url": "https://events.vtsociety.org/",
        "area": "V2X / 5G",
    },
    {
        "abbr": "ICC",
        "search": "ICC",
        "full": "IEEE International Conference on Communications",
        "url": "https://icc2027.ieee-icc.org/",
        "area": "Communications",
    },
    {
        "abbr": "WCNC",
        "search": "WCNC",
        "full": "IEEE Wireless Communications and Networking Conference",
        "url": "https://wcnc2026.ieee-wcnc.org/",
        "area": "Wireless",
    },
    {
        "abbr": "MobiCom",
        "search": "MobiCom",
        "full": "ACM Annual International Conference on Mobile Computing and Networking",
        "url": "https://www.sigmobile.org/mobicom/",
        "area": "Wireless",
    },
    {
        "abbr": "PIMRC",
        "search": "PIMRC",
        "full": "IEEE International Symposium on Personal, Indoor and Mobile Radio Communications",
        "url": "https://pimrc2025.ieee-pimrc.org/",
        "area": "Wireless",
    },
    {
        "abbr": "ICCV",
        "search": "ICCV",
        "full": "IEEE/CVF International Conference on Computer Vision",
        "url": "https://iccv2025.thecvf.com/",
        "area": "Computer Vision",
    },
]

WIKICFP_SEARCH = "http://www.wikicfp.com/cfp/search"
WIKICFP_EVENT  = "http://www.wikicfp.com/cfp/servlet/event.showcfp"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; ConferenceTrackerBot/1.0; "
        "+https://github.com/YOUR_USERNAME/conf-tracker)"
    )
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# WikiCFP ユーティリティ
# ─────────────────────────────────────────────

def wikicfp_search(keyword: str, max_results: int = 5) -> list[dict]:
    """WikiCFP を keyword で検索し、候補イベントのリストを返す。"""
    try:
        r = requests.get(
            WIKICFP_SEARCH,
            params={"q": keyword, "year": "f"},  # year=f → 未来のイベントを優先
            headers=HEADERS,
            timeout=15,
        )
        r.raise_for_status()
    except requests.RequestException as e:
        log.warning("検索失敗 [%s]: %s", keyword, e)
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    results = []

    # WikiCFP の検索結果テーブル
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
    """WikiCFP イベント詳細ページから情報を取得する。"""
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

    # タイトル・公式URL
    h1 = soup.find("h1")
    if h1:
        info["full"] = h1.get_text(strip=True)

    link_tags = soup.select("span.conURL a")
    if link_tags:
        info["url"] = link_tags[0]["href"]

    # 会議名テーブルから各フィールドを抽出
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


# ─────────────────────────────────────────────
# 日付パーサー
# ─────────────────────────────────────────────

MONTH_MAP = {
    "jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
    "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
}

def parse_date(raw: str | None) -> str | None:
    """
    WikiCFP の日付文字列を YYYY-MM-DD に変換する。
    例: "Jul 24, 2025" → "2025-07-24"
         "2025-07-24"   → "2025-07-24"
    """
    if not raw:
        return None
    raw = raw.strip()

    # YYYY-MM-DD
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    # Month DD, YYYY  or  DD Month YYYY
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


def parse_conf_dates(raw: str | None) -> tuple[str | None, str | None]:
    """
    "May 18-21, 2026" → ("2026-05-18", "2026-05-21")
    """
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
            start = f"{year}-{mon:02d}-{int(day_start):02d}"
            end   = f"{year}-{mon:02d}-{int(day_end):02d}"
            return start, end

    # 単日
    single = parse_date(raw)
    return single, single


# ─────────────────────────────────────────────
# メイン処理
# ─────────────────────────────────────────────

def fetch_conference(target: dict) -> dict:
    """1件の会議情報を WikiCFP から取得して返す。"""
    keyword = target["search"]
    log.info("検索中: %s", keyword)

    candidates = wikicfp_search(keyword, max_results=8)
    if not candidates:
        log.warning("候補なし: %s", keyword)
        return _fallback(target)

    # 今年・来年のイベントを優先（過去イベントを除外）
    today = date.today()
    best = None
    for cand in candidates:
        # タイトルにキーワードが含まれるものを選ぶ
        if keyword.lower() not in cand["title"].lower():
            continue
        # 締切が過去のものは後回し
        dl_str = parse_date(cand.get("deadline"))
        if dl_str:
            dl = date.fromisoformat(dl_str)
            if dl > today:
                best = cand
                break
        if best is None:
            best = cand  # 見つからなければ最初の一致を使用

    if best is None:
        best = candidates[0]

    log.info("  → 選択: %s (event_id=%s)", best["title"], best["event_id"])
    time.sleep(1.0)  # 礼儀正しいクローリング

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
    """WikiCFP で取得できなかった場合の fallback エントリ。"""
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
    log.info("======== 会議情報取得開始 ========")

    # 既存データを読み込んで fallback に使用
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
    for target in TARGET_CONFERENCES:
        try:
            entry = fetch_conference(target)

            # WikiCFP で取得できなかったフィールドは既存データで補完
            old = existing.get(target["abbr"], {})
            for field in ("deadline", "notification", "confDate", "confDateEnd", "location"):
                if not entry.get(field) and old.get(field):
                    entry[field] = old[field]
                    log.info("  補完 [%s.%s] ← 既存データ", target["abbr"], field)

            conferences.append(entry)
            time.sleep(1.5)

        except Exception as e:
            log.error("取得エラー [%s]: %s", target["abbr"], e)
            # エラーでも既存データを保持する
            if target["abbr"] in existing:
                conferences.append(existing[target["abbr"]])
                log.info("  既存データを維持: %s", target["abbr"])

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
