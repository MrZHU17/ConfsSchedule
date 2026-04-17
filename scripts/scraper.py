"""
Conference Tracker Scraper  v4
==============================
Playwright（ヘッドレスブラウザ）で公式サイトの authors ページを取得し、
主会議（Symposium/Technical Papers）の締切日だけを抽出する。

取得優先順位（フィールドごと）:
  1. 公式サイト authors ページ（Playwright）
  2. WikiCFP
  3. 既存 conferences.json

主会議の識別ロジック:
  ✅ "Call for Symposium Papers" / "Call for Technical Papers" / "Call for Papers"
  ❌ Tutorial / Workshop / Industry / Panel / Demo / Poster は除外
"""

import json
import re
import time
import logging
from datetime import datetime, date
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# 会議リスト
# authors_paths: authors ページの候補パス（上から順に試行）
# ─────────────────────────────────────────────
TARGET_CONFERENCES = [
    {
        "abbr": "IEEE GLOBECOM",
        "full": "IEEE Global Communications Conference",
        "base_url": "https://globecom2026.ieee-globecom.org",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp"],
        "area": "Communications",
        "wikicfp_search": "globecom",
    },
    {
        "abbr": "IEEE WCNC",
        "full": "IEEE Wireless Communications and Networking Conference",
        "base_url": "https://wcnc2026.ieee-wcnc.org",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp"],
        "area": "Wireless",
        "wikicfp_search": "wcnc",
    },
    {
        "abbr": "IEEE ICC",
        "full": "IEEE International Conference on Communications",
        "base_url": "https://icc2026.ieee-icc.org",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp"],
        "area": "Communications",
        "wikicfp_search": "icc",
    },
    {
        "abbr": "IEEE INFOCOM",
        "full": "IEEE International Conference on Computer Communications",
        "base_url": "https://infocom2026.ieee-infocom.org",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp"],
        "area": "Networking",
        "wikicfp_search": "infocom",
    },
    {
        "abbr": "IEEE VTC",
        "full": "IEEE Vehicular Technology Conference",
        "base_url": "https://events.vtsociety.org/vtc2026-fall",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp"],
        "area": "V2X / 5G",
        "wikicfp_search": "vtc",
    },
    {
        "abbr": "IEEE PIMRC",
        "full": "IEEE Int. Symposium on Personal, Indoor and Mobile Radio Communications",
        "base_url": "https://pimrc2026.ieee-pimrc.org",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp"],
        "area": "Wireless",
        "wikicfp_search": "pimrc",
    },
    {
        "abbr": "IEEE IV",
        "full": "IEEE Intelligent Vehicles Symposium",
        "base_url": "https://iv2026.ieee-iv.org",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp"],
        "area": "ITS / V2X",
        "wikicfp_search": "intelligent vehicles",
    },
    {
        "abbr": "IEEE VNC",
        "full": "IEEE Vehicular Networking Conference",
        "base_url": "https://ieee-vnc.org/2026",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp", "/"],
        "area": "V2X / Networking",
        "wikicfp_search": "vehicular networking",
    },
    {
        "abbr": "IEEE ITSC",
        "full": "IEEE Int. Conference on Intelligent Transportation Systems",
        "base_url": "https://ieee-itsc.org/2026",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp"],
        "area": "ITS",
        "wikicfp_search": "itsc",
    },
    {
        "abbr": "ITS World Congress",
        "full": "ITS World Congress",
        "base_url": "https://www.itsworldcongress.com",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp", "/"],
        "area": "ITS",
        "wikicfp_search": "its world congress",
    },
    {
        "abbr": "IEEE GCCE",
        "full": "IEEE Global Conference on Consumer Electronics",
        "base_url": "https://www.ieee-gcce.org/2026",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp"],
        "area": "Consumer Electronics",
        "wikicfp_search": "gcce",
    },
    {
        "abbr": "IEEE WFIoT",
        "full": "IEEE World Forum on Internet of Things",
        "base_url": "https://wfiot2026.iot.ieee.org",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp"],
        "area": "IoT",
        "wikicfp_search": "wfiot",
    },
    {
        "abbr": "IEEE CCNC",
        "full": "IEEE Consumer Communications and Networking Conference",
        "base_url": "https://ccnc2027.ieee-ccnc.org",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp"],
        "area": "Consumer / Networking",
        "wikicfp_search": "ccnc",
    },
    {
        "abbr": "IEEE CTW",
        "full": "IEEE Communication Theory Workshop",
        "base_url": "https://ctw2026.ieee-ctw.org",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp", "/"],
        "area": "Theory",
        "wikicfp_search": "communication theory workshop",
    },
    {
        "abbr": "APCC",
        "full": "Asia-Pacific Conference on Communications",
        "base_url": "https://apcc2026.org",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp", "/"],
        "area": "Asia-Pacific",
        "wikicfp_search": "apcc",
    },
    {
        "abbr": "ICOIN",
        "full": "International Conference on Information Networking",
        "base_url": "https://www.icoin.org",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp", "/"],
        "area": "Networking",
        "wikicfp_search": "icoin",
    },
    {
        "abbr": "WPMC",
        "full": "Int. Symposium on Wireless Personal Multimedia Communications",
        "base_url": "https://www.wpmc-conf.org/2026",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp", "/"],
        "area": "Wireless",
        "wikicfp_search": "wpmc",
    },
    {
        "abbr": "ICETC",
        "full": "Int. Conference on Emerging Technologies for Communications",
        "base_url": "https://www.ieice.org/cs/icetc/2026",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp", "/"],
        "area": "Emerging Tech",
        "wikicfp_search": "icetc",
    },
    {
        "abbr": "ICNC",
        "full": "Int. Conference on Computing, Networking and Communications",
        "base_url": "https://www.conf-icnc.org/2027",
        "authors_paths": ["/authors", "/call-for-papers", "/cfp", "/"],
        "area": "Networking",
        "wikicfp_search": "icnc",
    },
]

# ─────────────────────────────────────────────
# 主会議セクションの識別キーワード
# ─────────────────────────────────────────────

# これらのキーワードを含むセクションが「主会議」
MAIN_SECTION_KEYWORDS = [
    "call for symposium papers",
    "call for technical papers",
    "call for regular papers",
    "call for full papers",
    "call for papers",
    "paper submission",
    "technical program",
    "main track",
    "conference papers",
]

# これらのキーワードを含むセクションは除外
SKIP_SECTION_KEYWORDS = [
    "tutorial",
    "workshop",
    "industry",
    "panel",
    "demo",
    "poster",
    "special session",
    "satellite",
    "exhibit",
    "competition",
    "challenge",
    "summary",
    "camera ready",
    "final paper",
    "registration",
]

# 締切日を示すキーワード
DEADLINE_KEYWORDS = [
    "deadline for paper submission",
    "paper submission deadline",
    "submission deadline",
    "abstract deadline",
    "abstract submission",
    "paper due",
    "manuscript",
]

# 通知日を示すキーワード
NOTIFICATION_KEYWORDS = [
    "notification of acceptance",
    "notification date",
    "acceptance notification",
    "author notification",
    "notification",
]


# ─────────────────────────────────────────────
# 日付パーサー
# ─────────────────────────────────────────────

MONTH_MAP = {
    "jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
    "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
    "january":1,"february":2,"march":3,"april":4,"june":6,
    "july":7,"august":8,"september":9,"october":10,"november":11,"december":12,
}

def parse_date(raw: str) -> str | None:
    if not raw:
        return None
    raw = re.sub(r"\(.*?\)", "", raw).strip()  # "(Firm Deadline!)" などを除去
    # YYYY-MM-DD
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # DD Month YYYY or Month DD, YYYY
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", raw)
    if m:
        mon = MONTH_MAP.get(m.group(2).lower())
        if mon:
            return f"{m.group(3)}-{mon:02d}-{int(m.group(1)):02d}"
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", raw)
    if m:
        mon = MONTH_MAP.get(m.group(1).lower())
        if mon:
            return f"{m.group(3)}-{mon:02d}-{int(m.group(2)):02d}"
    return None


def parse_conf_dates(raw: str) -> tuple[str | None, str | None]:
    if not raw:
        return None, None
    # "May 18-21, 2026"
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2})\s*[-–]\s*(\d{1,2}),?\s+(\d{4})", raw)
    if m:
        mon = MONTH_MAP.get(m.group(1).lower())
        if mon:
            y = m.group(4)
            return f"{y}-{mon:02d}-{int(m.group(2)):02d}", f"{y}-{mon:02d}-{int(m.group(3)):02d}"
    # "May 18 - June 2, 2026"
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2})\s*[-–]\s*([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", raw)
    if m:
        m1 = MONTH_MAP.get(m.group(1).lower())
        m2 = MONTH_MAP.get(m.group(3).lower())
        y = m.group(5)
        if m1 and m2:
            return f"{y}-{m1:02d}-{int(m.group(2)):02d}", f"{y}-{m2:02d}-{int(m.group(4)):02d}"
    single = parse_date(raw)
    return single, single


# ─────────────────────────────────────────────
# テキストから主会議の締切を抽出
# ─────────────────────────────────────────────

def extract_main_paper_dates(text: str) -> dict:
    """
    ページテキストから主会議の締切・通知日を抽出する。

    ロジック:
    1. ページを「セクション」に分割（見出し行で区切る）
    2. SKIP_SECTION_KEYWORDS を含むセクションを除外
    3. MAIN_SECTION_KEYWORDS を含むセクション、またはそれらがなければ
       最初の有効なセクションから締切を抽出
    """
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # セクションに分割（大文字の見出し行、または "Call for" で始まる行）
    sections = []
    current_section_title = ""
    current_section_lines = []

    for line in lines:
        is_heading = (
            line.lower().startswith("call for") or
            line.lower().startswith("important date") or
            (len(line) < 80 and line[0].isupper() and
             any(kw in line.lower() for kw in ["paper", "proposal", "submission", "author", "dates"]))
        )
        if is_heading and current_section_lines:
            sections.append((current_section_title, current_section_lines))
            current_section_title = line
            current_section_lines = []
        else:
            if is_heading:
                current_section_title = line
            else:
                current_section_lines.append(line)

    if current_section_lines:
        sections.append((current_section_title, current_section_lines))

    # セクションがない場合は全テキストを1セクションとして扱う
    if not sections:
        sections = [("", lines)]

    log.debug("  セクション数: %d", len(sections))
    for title, _ in sections:
        log.debug("    セクション: %s", title[:60])

    def score_section(title: str) -> int:
        """セクションの優先スコアを返す。高いほど主会議らしい。"""
        t = title.lower()
        # スキップセクションは -1
        if any(kw in t for kw in SKIP_SECTION_KEYWORDS):
            return -1
        # 主会議セクションはスコア加算
        score = 0
        for i, kw in enumerate(MAIN_SECTION_KEYWORDS):
            if kw in t:
                score += (len(MAIN_SECTION_KEYWORDS) - i)  # 前の方が高スコア
        return score

    # スコア順でソート（スキップ除外）
    scored = [(score_section(title), title, lines) for title, lines in sections]
    valid = [(s, t, l) for s, t, l in scored if s >= 0]
    valid.sort(key=lambda x: x[0], reverse=True)

    if not valid:
        log.warning("  有効なセクションが見つかりません")
        return {}

    # 上位セクションから締切・通知日を探す
    result = {}
    for _, section_title, section_lines in valid[:3]:
        log.debug("  解析中セクション: %s", section_title[:60])
        full_section = "\n".join(section_lines)

        if "deadline" not in result:
            for i, line in enumerate(section_lines):
                ll = line.lower()
                if any(kw in ll for kw in DEADLINE_KEYWORDS):
                    # 同じ行か次の行に日付がある
                    date_candidates = [line] + section_lines[i+1:i+3]
                    for dc in date_candidates:
                        d = parse_date(dc)
                        if d:
                            result["deadline"] = d
                            log.info("  締切日発見: %s ← \"%s\"", d, line[:60])
                            break
                    if "deadline" in result:
                        break

        if "notification" not in result:
            for i, line in enumerate(section_lines):
                ll = line.lower()
                if any(kw in ll for kw in NOTIFICATION_KEYWORDS):
                    date_candidates = [line] + section_lines[i+1:i+3]
                    for dc in date_candidates:
                        d = parse_date(dc)
                        if d:
                            result["notification"] = d
                            log.info("  通知日発見: %s ← \"%s\"", d, line[:60])
                            break
                    if "notification" in result:
                        break

        if "deadline" in result and "notification" in result:
            break

    return result


# ─────────────────────────────────────────────
# Playwright で公式サイトを取得
# ─────────────────────────────────────────────

def fetch_official_page(base_url: str, paths: list[str]) -> tuple[str, str]:
    """
    Playwright でページを取得し (page_text, final_url) を返す。
    失敗した場合は ("", "") を返す。
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        log.warning("  Playwright が未インストール（スキップ）")
        return "", ""

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )
        page = ctx.new_page()

        for path in paths:
            url = base_url.rstrip("/") + path
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=20000)
                if resp and resp.status == 200:
                    # JS レンダリングを待つ
                    page.wait_for_timeout(2000)
                    text = page.inner_text("body")
                    if len(text) > 200:
                        log.info("  公式サイト取得成功: %s", url)
                        browser.close()
                        return text, url
                else:
                    log.debug("  %s → HTTP %s", url, resp.status if resp else "?")
            except PWTimeout:
                log.debug("  %s → タイムアウト", url)
            except Exception as e:
                log.debug("  %s → %s", url, e)

        browser.close()
    return "", ""


# ─────────────────────────────────────────────
# WikiCFP フォールバック
# ─────────────────────────────────────────────

def wikicfp_fetch(keyword: str) -> dict:
    """WikiCFP から会議情報を取得する（フォールバック用）。"""
    import requests
    from bs4 import BeautifulSoup

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }

    url = f"http://www.wikicfp.com/cfp/call?conference={keyword}"
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
            dl_parsed = parse_date(dl)
            if dl_parsed and date.fromisoformat(dl_parsed) >= today:
                best = {"event_id": eid_m.group(1), "title": title,
                        "when": when, "where": where, "deadline": dl, "year": year}
                break

    if not best:
        return {}

    # 詳細ページ取得
    time.sleep(1.0)
    try:
        r2 = requests.get(
            f"http://www.wikicfp.com/cfp/servlet/event.showcfp?eventid={best['event_id']}",
            headers=HEADERS, timeout=15
        )
        soup2 = BeautifulSoup(r2.text, "html.parser")
        info = {"where": best["where"], "when": best["when"]}
        for row2 in soup2.select("table.gg tr"):
            cells2 = row2.find_all("td")
            if len(cells2) < 2:
                continue
            lbl = cells2[0].get_text(strip=True).lower()
            val = cells2[1].get_text(strip=True)
            if "submission deadline" in lbl:
                info["deadline_raw"] = val
            elif "notification" in lbl and "deadline_raw" in info:
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

def process_conference(target: dict, existing: dict) -> dict:
    abbr = target["abbr"]

    entry = {
        "abbr":        abbr,
        "full":        target["full"],
        "url":         target["base_url"],
        "area":        target["area"],
        "location":    "TBD",
        "confDate":    None,
        "confDateEnd": None,
        "deadline":    None,
        "notification": None,
        "source":      None,
        "data_source": "none",
        "fetched_at":  datetime.utcnow().isoformat() + "Z",
    }

    # ── Step 1: 公式サイト authors ページから取得 ──────────────────
    page_text, page_url = fetch_official_page(
        target["base_url"], target["authors_paths"]
    )

    if page_text:
        dates = extract_main_paper_dates(page_text)
        if dates.get("deadline"):
            entry["deadline"]     = dates["deadline"]
            entry["notification"] = dates.get("notification")
            entry["source"]       = page_url
            entry["data_source"]  = "official"
            log.info("  ✓ 公式サイトから取得: deadline=%s", entry["deadline"])

    # ── Step 2: WikiCFP フォールバック ─────────────────────────────
    if not entry["deadline"]:
        log.info("  → WikiCFP フォールバック")
        wdata = wikicfp_fetch(target["wikicfp_search"])
        if wdata:
            entry["deadline"]     = parse_date(wdata.get("deadline_raw")) or entry["deadline"]
            entry["notification"] = parse_date(wdata.get("notification_raw")) or entry["notification"]
            entry["location"]     = wdata.get("where", "TBD")
            entry["url"]          = wdata.get("url", entry["url"])
            start, end = parse_conf_dates(wdata.get("confDate_raw") or wdata.get("when", ""))
            entry["confDate"]     = start
            entry["confDateEnd"]  = end
            entry["data_source"]  = "wikicfp"
            time.sleep(1.5)

    # ── Step 3: 既存データで補完 ────────────────────────────────────
    old = existing.get(abbr, {})
    for field in ("deadline", "notification", "confDate", "confDateEnd", "location", "url", "full"):
        if not entry.get(field) and old.get(field):
            entry[field] = old[field]
            log.info("  補完 [%s] ← 既存データ", field)

    return entry


def main():
    log.info("======== 会議情報取得開始 (%d 件) ========", len(TARGET_CONFERENCES))

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
        log.info("[%d/%d] %s", i, len(TARGET_CONFERENCES), target["abbr"])
        try:
            entry = process_conference(target, existing)
            conferences.append(entry)
            log.info("  完了: deadline=%s, source=%s", entry["deadline"], entry["data_source"])
        except Exception as e:
            log.error("  エラー: %s", e)
            old_entry = existing.get(target["abbr"])
            conferences.append(old_entry if old_entry else {
                "abbr": target["abbr"], "full": target["full"],
                "url": target["base_url"], "area": target["area"],
                "location": "TBD", "confDate": None, "confDateEnd": None,
                "deadline": None, "notification": None,
                "data_source": "error", "fetched_at": datetime.utcnow().isoformat() + "Z",
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
