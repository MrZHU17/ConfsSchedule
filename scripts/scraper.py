"""
Conference Tracker Scraper  v7
==============================
Claude API + web_search ツールを使って各会議の最新締切日を取得する。

bot対策（HTTP 418 / IP制限）を完全に回避。
ウェブ検索で最新情報を取得するため、延長済みの締切にも自動対応。

データソース優先順位:
  1. Claude API + web_search（メイン）
  2. 既存 conferences.json で補完（API失敗時）
"""

import json
import re
import time
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).parent.parent
API_URL   = "https://api.anthropic.com/v1/messages"
MODEL     = "claude-sonnet-4-20250514"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# 会議リスト
# ─────────────────────────────────────────────
TARGET_CONFERENCES = [
    {
        "abbr": "IEEE GLOBECOM",
        "full": "IEEE Global Communications Conference",
        "base_url": "https://globecom2026.ieee-globecom.org",
        "area": "Communications",
        "search_query": "IEEE GLOBECOM 2026 paper submission deadline",
    },
    {
        "abbr": "IEEE WCNC",
        "full": "IEEE Wireless Communications and Networking Conference",
        "base_url": "https://wcnc2026.ieee-wcnc.org",
        "area": "Wireless",
        "search_query": "IEEE WCNC 2026 paper submission deadline",
    },
    {
        "abbr": "IEEE ICC",
        "full": "IEEE International Conference on Communications",
        "base_url": "https://icc2026.ieee-icc.org",
        "area": "Communications",
        "search_query": "IEEE ICC 2026 paper submission deadline",
    },
    {
        "abbr": "IEEE INFOCOM",
        "full": "IEEE International Conference on Computer Communications",
        "base_url": "https://infocom2026.ieee-infocom.org",
        "area": "Networking",
        "search_query": "IEEE INFOCOM 2026 paper submission deadline",
    },
    {
        "abbr": "IEEE VTC",
        "full": "IEEE Vehicular Technology Conference",
        "base_url": "https://events.vtsociety.org/vtc2026-fall",
        "area": "V2X / 5G",
        "search_query": "IEEE VTC Fall 2026 paper submission deadline",
    },
    {
        "abbr": "IEEE PIMRC",
        "full": "IEEE Int. Symposium on Personal, Indoor and Mobile Radio Communications",
        "base_url": "https://pimrc2026.ieee-pimrc.org",
        "area": "Wireless",
        "search_query": "IEEE PIMRC 2026 paper submission deadline",
    },
    {
        "abbr": "IEEE IV",
        "full": "IEEE Intelligent Vehicles Symposium",
        "base_url": "https://iv2026.ieee-iv.org",
        "area": "ITS / V2X",
        "search_query": "IEEE Intelligent Vehicles Symposium IV 2026 paper submission deadline",
    },
    {
        "abbr": "IEEE VNC",
        "full": "IEEE Vehicular Networking Conference",
        "base_url": "https://vnc2026.ieee-vnc.org",
        "area": "V2X / Networking",
        "search_query": "IEEE VNC Vehicular Networking Conference 2026 paper submission deadline",
    },
    {
        "abbr": "IEEE ITSC",
        "full": "IEEE Int. Conference on Intelligent Transportation Systems",
        "base_url": "https://ieee-itsc.org/2026",
        "area": "ITS",
        "search_query": "IEEE ITSC 2026 paper submission deadline",
    },
    {
        "abbr": "ITS World Congress",
        "full": "ITS World Congress",
        "base_url": "https://2026itsworldcongress.org",
        "area": "ITS",
        "search_query": "ITS World Congress 2026 paper submission deadline",
    },
    {
        "abbr": "IEEE GCCE",
        "full": "IEEE Global Conference on Consumer Electronics",
        "base_url": "https://www.ieee-gcce.org/2026",
        "area": "Consumer Electronics",
        "search_query": "IEEE GCCE 2026 paper submission deadline",
    },
    {
        "abbr": "IEEE WFIoT",
        "full": "IEEE World Forum on Internet of Things",
        "base_url": "https://wfiot2026.iot.ieee.org",
        "area": "IoT",
        "search_query": "IEEE WFIoT World Forum IoT 2026 paper submission deadline",
    },
    {
        "abbr": "IEEE CCNC",
        "full": "IEEE Consumer Communications and Networking Conference",
        "base_url": "https://ccnc2027.ieee-ccnc.org",
        "area": "Consumer / Networking",
        "search_query": "IEEE CCNC 2027 paper submission deadline",
    },
    {
        "abbr": "IEEE CTW",
        "full": "IEEE Communication Theory Workshop",
        "base_url": "https://ctw2026.ieee-ctw.org",
        "area": "Theory",
        "search_query": "IEEE CTW Communication Theory Workshop 2026 paper submission deadline",
    },
    {
        "abbr": "APCC",
        "full": "Asia-Pacific Conference on Communications",
        "base_url": "https://apcc2026.org",
        "area": "Asia-Pacific",
        "search_query": "APCC Asia-Pacific Conference on Communications 2026 paper submission deadline",
    },
    {
        "abbr": "ICOIN",
        "full": "International Conference on Information Networking",
        "base_url": "https://www.icoin.org",
        "area": "Networking",
        "search_query": "ICOIN International Conference Information Networking 2026 paper submission deadline",
    },
    {
        "abbr": "WPMC",
        "full": "Int. Symposium on Wireless Personal Multimedia Communications",
        "base_url": "https://www.wpmc-conf.org/2026",
        "area": "Wireless",
        "search_query": "WPMC 2026 Wireless Personal Multimedia Communications paper submission deadline",
    },
    {
        "abbr": "ICETC",
        "full": "Int. Conference on Emerging Technologies for Communications",
        "base_url": "https://www.ieice.org/cs/icetc/2026",
        "area": "Emerging Tech",
        "search_query": "ICETC 2026 Emerging Technologies Communications paper submission deadline",
    },
    {
        "abbr": "ICNC",
        "full": "Int. Conference on Computing, Networking and Communications",
        "base_url": "https://www.conf-icnc.org/2027",
        "area": "Networking",
        "search_query": "ICNC 2027 Computing Networking Communications paper submission deadline",
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
    if not raw:
        return None
    raw = re.sub(r"\(.*?\)", "", raw).strip()
    # 「旧日付 → 新日付」の延長表記は最後の日付（最新）を使う
    if re.search(r"[→⇒>]", raw):
        raw = re.split(r"[→⇒>]", raw)[-1].strip()
    else:
        raw = re.sub(r">.*", "", raw).strip()

    m = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", raw)
    if m:
        mon = MONTH_MAP.get(m.group(2).lower())
        if mon:
            return f"{m.group(3)}-{mon:02d}-{int(m.group(1)):02d}"
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2})[,\s]+(\d{4})", raw)
    if m:
        mon = MONTH_MAP.get(m.group(1).lower())
        if mon:
            return f"{m.group(3)}-{mon:02d}-{int(m.group(2)):02d}"
    return None


# ─────────────────────────────────────────────
# Claude API 呼び出し（web_search ツール付き）
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a research assistant that finds academic conference submission deadlines.
When given a conference name and year, search the web and return ONLY a JSON object.

Rules:
- Search for the LATEST / most current deadline (including any extensions).
- Focus on the MAIN paper submission deadline (not workshop/tutorial/demo).
- Return ONLY valid JSON, no markdown fences, no extra text.
- If a date is unknown, use null.
- Dates must be in ISO format: "YYYY-MM-DD".
- For conference dates with ranges, use the start date for confDate and end date for confDateEnd.

JSON schema:
{
  "deadline": "YYYY-MM-DD or null",
  "notification": "YYYY-MM-DD or null",
  "confDate": "YYYY-MM-DD or null",
  "confDateEnd": "YYYY-MM-DD or null",
  "location": "City, Country or null",
  "url": "official website URL or null",
  "confidence": "high | medium | low"
}
"""


def fetch_conference_info(abbr: str, search_query: str) -> dict:
    """
    Claude API + web_search で会議情報を取得する。
    返り値: {"deadline": ..., "notification": ..., ...} または {}
    """
    payload = {
        "model": MODEL,
        "max_tokens": 1024,
        "system": SYSTEM_PROMPT,
        "tools": [{"type": "web_search_20250305", "name": "web_search"}],
        "messages": [
            {
                "role": "user",
                "content": (
                    f"Find the latest paper submission deadline for: {abbr}\n"
                    f"Search query: {search_query}\n\n"
                    f"Return ONLY the JSON object."
                ),
            }
        ],
    }

    try:
        r = requests.post(API_URL, json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.error("  API呼び出し失敗: %s", e)
        return {}

    # レスポンスからテキストブロックを結合
    text = ""
    for block in data.get("content", []):
        if block.get("type") == "text":
            text += block.get("text", "")

    # JSON抽出（コードフェンスがある場合も対応）
    text = re.sub(r"```(?:json)?", "", text).strip()
    # 最初の { から最後の } までを抜き出す
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        log.warning("  JSONが見つかりません: %s", text[:200])
        return {}

    try:
        result = json.loads(m.group())
        log.info("  API結果: deadline=%s, conf=%s, confidence=%s",
                 result.get("deadline"), result.get("confDate"), result.get("confidence"))
        return result
    except json.JSONDecodeError as e:
        log.warning("  JSONパース失敗: %s | %s", e, m.group()[:200])
        return {}


# ─────────────────────────────────────────────
# メイン処理
# ─────────────────────────────────────────────

def process_conference(target: dict, existing: dict) -> dict:
    abbr = target["abbr"]
    now  = datetime.now(timezone.utc).isoformat()

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
        "fetched_at":   now,
    }

    # ── Step 1: Claude API + web_search ────────────────────────────
    info = fetch_conference_info(abbr, target["search_query"])

    if info:
        if info.get("deadline"):
            entry["deadline"] = parse_date(info["deadline"]) or info["deadline"]
        if info.get("notification"):
            entry["notification"] = parse_date(info["notification"]) or info["notification"]
        if info.get("confDate"):
            entry["confDate"] = parse_date(info["confDate"]) or info["confDate"]
        if info.get("confDateEnd"):
            entry["confDateEnd"] = parse_date(info["confDateEnd"]) or info["confDateEnd"]
        if info.get("location"):
            entry["location"] = info["location"]
        if info.get("url"):
            entry["url"] = info["url"]
        entry["data_source"] = "api_search"
        entry["source"]      = target["search_query"]

    # ── Step 2: 既存データで補完 ────────────────────────────────────
    old = existing.get(abbr, {})
    for field in ("deadline", "notification", "confDate", "confDateEnd", "location", "url", "full"):
        if not entry.get(field) and old.get(field):
            entry[field] = old[field]
            log.info("  補完 [%s] ← 既存: %s", field, old[field])

    return entry


def main() -> None:
    log.info("======== 会議情報取得開始 (%d 件) ========", len(TARGET_CONFERENCES))

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

    conferences = []
    for i, target in enumerate(TARGET_CONFERENCES, 1):
        log.info("[%d/%d] %s", i, len(TARGET_CONFERENCES), target["abbr"])
        try:
            entry = process_conference(target, existing)
            conferences.append(entry)
            log.info("  完了: deadline=%s, location=%s",
                     entry["deadline"], entry["location"])
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
                "fetched_at":  datetime.now(timezone.utc).isoformat(),
            })

        # API レート制限に配慮
        time.sleep(2)

    output = {
        "updated_at":  datetime.now(timezone.utc).isoformat(),
        "conferences": conferences,
    }
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("======== 完了: %d 件 → %s ========", len(conferences), output_path)


if __name__ == "__main__":
    main()
