"""
Conference Tracker Scraper  v12
================================
新設計:
  - conferences.override.json が唯一の正式データソース
  - override に deadline がある会議 → スクレイピングを完全スキップ
  - override に deadline がない会議 → スクレイピングで補完を試みる
  - 修正は conferences.override.json だけ編集すれば OK
"""

import json, re, time, logging, os
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).parent.parent
OVERRIDE_PATH = REPO_ROOT / "conferences.override.json"
OUTPUT_PATH   = REPO_ROOT / "conferences.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
USE_CLAUDE = bool(ANTHROPIC_API_KEY)

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
})

# ─────────────────────────────────────────────────────────────
# スクレイピング対象の URL リスト（deadline が null の場合のみ使用）
# ─────────────────────────────────────────────────────────────
SCRAPE_TARGETS = {
    "ITS World Congress": {
        "official_cfp": "https://2026itsworldcongress.org/call-for-papers/",
        "wikicfp_query": "ITS World Congress 2026",
    },
    "WPMC": {
        "official_cfp": "https://www.wpmc-conf.org/2026/cfp.html",
        "wikicfp_query": "WPMC 2026",
    },
    "ICETC": {
        "official_cfp": "https://www.ieice.org/cs/icetc/2026/cfp.html",
        "wikicfp_query": "ICETC 2026",
    },
}

# ─────────────────────────────────────────────────────────────
# 日付パーサー
# ─────────────────────────────────────────────────────────────
MONTH_MAP = {
    "jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
    "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
    "january":1,"february":2,"march":3,"april":4,
    "june":6,"july":7,"august":8,"september":9,
    "october":10,"november":11,"december":12,
}

def parse_date(raw: str) -> str | None:
    if not raw:
        return None
    raw = re.sub(r"\(.*?\)", "", raw).strip()
    # 延長日付は最新を使用
    for sep in ("→", "⇒", "->", "extended to", "Extended to"):
        if sep in raw:
            raw = raw.split(sep)[-1].strip()
            break
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


def _safe_get(url: str, timeout: int = 12) -> BeautifulSoup | None:
    try:
        r = SESSION.get(url, timeout=timeout)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        log.warning("    GET失敗 [%s]: %s", url, e)
        return None


# ─────────────────────────────────────────────────────────────
# Claude API による日付抽出（オプション）
# ─────────────────────────────────────────────────────────────

def extract_with_claude(page_text: str, conf_name: str) -> dict:
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        truncated = page_text[:4000]
        prompt = f"""You are extracting conference scheduling information from a CFP page.
Conference: {conf_name}

Return ONLY a valid JSON object. Use the LATEST date if extended.
Fields:
- "deadline": paper submission deadline (YYYY-MM-DD or null)
- "notification": author notification date (YYYY-MM-DD or null)
- "confDate": first day of conference (YYYY-MM-DD or null)
- "confDateEnd": last day of conference (YYYY-MM-DD or null)
- "location": city and country (string or null)

Text:
{truncated}"""
        resp = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        raw = re.sub(r"^```json\s*|^```\s*|\s*```$", "", raw, flags=re.M).strip()
        return json.loads(raw)
    except Exception as e:
        log.warning("    Claude 抽出失敗: %s", e)
        return {}


# ─────────────────────────────────────────────────────────────
# 正規表現による日付抽出（フォールバック）
# ─────────────────────────────────────────────────────────────

_DEADLINE_KW = re.compile(
    r"(paper\s+submission|submission\s+deadline|manuscript\s+due"
    r"|abstract\s+deadline|full\s+paper|camera[- ]ready)", re.I)
_NOTIF_KW = re.compile(
    r"(notification|acceptance\s+notice|author\s+notification)", re.I)
_CONF_KW = re.compile(
    r"(conference\s+date|symposium\s+date|event\s+date)", re.I)

def extract_with_regex(soup: BeautifulSoup) -> dict:
    result = {"deadline": None, "notification": None, "confDate": None, "location": None}

    # テーブル構造
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in row.find_all(["td","th"])]
            if len(cells) < 2:
                continue
            label, value = cells[0].lower(), cells[-1]
            date = parse_date(value)
            if not date:
                continue
            if _DEADLINE_KW.search(label) and not result["deadline"]:
                result["deadline"] = date
            elif _NOTIF_KW.search(label) and not result["notification"]:
                result["notification"] = date

    # テキスト行スキャン
    if not result["deadline"]:
        lines = [l.strip() for l in soup.get_text("\n").splitlines() if l.strip()]
        date_lines = [(i, parse_date(l)) for i, l in enumerate(lines) if parse_date(l)]
        def nearest(kw_re, window=8):
            for i, line in enumerate(lines):
                if kw_re.search(line):
                    for j, d in date_lines:
                        if abs(j-i) <= window:
                            return d
            return None
        result["deadline"]     = result["deadline"]     or nearest(_DEADLINE_KW)
        result["notification"] = result["notification"] or nearest(_NOTIF_KW)

    # 開催地
    loc_pat = re.compile(
        r"(?:venue|location|city|held\s+in|taking\s+place\s+in)[:\s]+([^\n<]{4,60})", re.I)
    for elem in soup.find_all(string=loc_pat):
        m = loc_pat.search(str(elem))
        if m:
            loc = m.group(1).strip().rstrip(".,;")
            if loc.lower() not in ("tbd","tba","n/a",""):
                result["location"] = loc
                break

    return result


# ─────────────────────────────────────────────────────────────
# 公式サイトからのスクレイピング
# ─────────────────────────────────────────────────────────────

def scrape_official(conf_name: str, cfp_url: str, base_url: str) -> dict:
    for url in [cfp_url, base_url]:
        soup = _safe_get(url)
        if soup is None:
            continue
        for tag in soup(["script","style","nav","footer","header"]):
            tag.decompose()
        page_text = soup.get_text(separator="\n", strip=True)
        info = extract_with_claude(page_text, conf_name) if USE_CLAUDE else extract_with_regex(soup)
        if info.get("deadline"):
            log.info("    公式サイトから取得: %s → deadline=%s", url, info["deadline"])
            return info
    return {}


# ─────────────────────────────────────────────────────────────
# WikiCFP スクレイピング
# ─────────────────────────────────────────────────────────────

def scrape_wikicfp(abbr: str, query: str, base_url: str) -> dict:
    url = f"https://www.wikicfp.com/cfp/search?q={requests.utils.quote(query)}&year=f"
    soup = _safe_get(url, timeout=10)
    if soup is None:
        return {}

    abbr_key = abbr.lower().replace("ieee ","").replace(" ","")
    candidates = []
    rows = soup.find_all("tr", class_=re.compile(r"^(even|odd)$"))

    i = 0
    while i < len(rows)-1:
        r1, r2 = rows[i], rows[i+1]
        c1 = r1.find_all("td")
        c2 = r2.find_all("td")
        if len(c1) < 1 or len(c2) < 4:
            i += 1
            continue
        link = c1[0].find("a")
        row_abbr = (link.get_text(strip=True) if link else c1[0].get_text(strip=True))
        row_key  = row_abbr.lower().replace("ieee ","").replace(" ","")

        def safe_date(cell):
            t = cell.get_text(strip=True)
            return None if t.upper() in ("N/A","TBD","") else parse_date(t)

        entry = {
            "deadline":    safe_date(c2[0]),
            "notification":safe_date(c2[1]),
            "confDate":    safe_date(c2[2]),
            "confDateEnd": safe_date(c2[3]),
            "location":    c2[4].get_text(strip=True) if len(c2)>=5 else None,
        }

        score = (3 if row_key==abbr_key
                 else 2 if (row_key in abbr_key or abbr_key in row_key)
                 else 0)
        if score > 0 and entry.get("deadline"):
            candidates.append((score, entry))
        i += 2

    if not candidates:
        return {}
    best = max(candidates, key=lambda x: x[0])[1]
    log.info("    WikiCFP ヒット: deadline=%s", best["deadline"])
    return best


# ─────────────────────────────────────────────────────────────
# メイン処理
# ─────────────────────────────────────────────────────────────

def load_override() -> dict:
    if not OVERRIDE_PATH.exists():
        log.error("conferences.override.json が見つかりません")
        return {}
    try:
        raw = json.loads(OVERRIDE_PATH.read_text(encoding="utf-8"))
        data = {k: v for k, v in raw.items() if not k.startswith("_")}
        log.info("override 読み込み: %d 件", len(data))
        return data
    except json.JSONDecodeError as e:
        log.error("override の JSON が不正です: %s", e)
        return {}


def main() -> None:
    overrides = load_override()
    if not overrides:
        log.error("override が空です。処理を中断します。")
        return

    now = datetime.now(timezone.utc).isoformat()
    conferences = []

    for abbr, ov in overrides.items():
        log.info("処理中: %s", abbr)

        entry = {
            "abbr":         abbr,
            "society":      ov.get("society", "Other"),
            "full":         ov.get("full", ""),
            "area":         ov.get("area", ""),
            "url":          ov.get("url", ""),
            "location":     ov.get("location"),
            "confDate":     ov.get("confDate"),
            "confDateEnd":  ov.get("confDateEnd"),
            "deadline":     ov.get("deadline"),
            "notification": ov.get("notification"),
            "data_source":  "manual",
            "fetched_at":   now,
        }

        # ── deadline がある → スクレイピング不要 ──────────
        if entry["deadline"]:
            log.info("  ✓ 手動データ使用 (スクレイピングスキップ): deadline=%s", entry["deadline"])
            conferences.append(entry)
            continue

        # ── deadline が null → スクレイピングを試みる ────
        scrape_cfg = SCRAPE_TARGETS.get(abbr, {})
        scraped = {}

        if scrape_cfg.get("official_cfp"):
            scraped = scrape_official(
                abbr,
                scrape_cfg["official_cfp"],
                ov.get("url",""),
            )

        if not scraped.get("deadline") and scrape_cfg.get("wikicfp_query"):
            scraped = scrape_wikicfp(abbr, scrape_cfg["wikicfp_query"], ov.get("url",""))

        # スクレイピング結果をマージ（null フィールドのみ上書き）
        for f in ("deadline","notification","confDate","confDateEnd","location"):
            if scraped.get(f) and not entry.get(f):
                entry[f] = scraped[f]

        if entry["deadline"]:
            entry["data_source"] = "scraped"
            log.info("  ✓ スクレイピング成功: deadline=%s", entry["deadline"])
        else:
            log.info("  △ 日程未定 (取得できず)")

        conferences.append(entry)
        time.sleep(1.0)

    OUTPUT_PATH.write_text(
        json.dumps({
            "updated_at":  now,
            "conferences": conferences,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("完了: %d 件 → %s", len(conferences), OUTPUT_PATH)


if __name__ == "__main__":
    main()
