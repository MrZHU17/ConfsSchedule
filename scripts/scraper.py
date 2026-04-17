"""
Conference Tracker Scraper  v5
==============================
取得戦略（優先順位）:
  1. requests + BeautifulSoup でHTMLテーブル・リスト構造をパース（高速・構造保持）
  2. Playwright（ヘッドレス）で JS レンダリング後にHTMLを再パース
  3. WikiCFP フォールバック
  4. 既存 conferences.json で補完

IEEEのauthorsページは通常 "Important Dates" テーブルまたはリストで
締切日を列挙しているため、テキスト変換前のHTML構造から直接抽出する。

主会議の識別:
  ✅ Call for Papers / Technical Papers / Symposium Papers
  ❌ Workshop / Tutorial / Industry / Demo / Poster は除外
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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ─────────────────────────────────────────────
# 会議リスト
# authors_paths: authors ページの候補パス（上から順に試行）
# ─────────────────────────────────────────────
TARGET_CONFERENCES = [
    {
        "abbr": "IEEE GLOBECOM",
        "full": "IEEE Global Communications Conference",
        "base_url": "https://globecom2026.ieee-globecom.org",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp", "/"],
        "area": "Communications",
        "wikicfp_search": "globecom 2026",
    },
    {
        "abbr": "IEEE WCNC",
        "full": "IEEE Wireless Communications and Networking Conference",
        "base_url": "https://wcnc2026.ieee-wcnc.org",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp", "/"],
        "area": "Wireless",
        "wikicfp_search": "wcnc 2026",
    },
    {
        "abbr": "IEEE ICC",
        "full": "IEEE International Conference on Communications",
        "base_url": "https://icc2026.ieee-icc.org",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp", "/"],
        "area": "Communications",
        "wikicfp_search": "icc 2026",
    },
    {
        "abbr": "IEEE INFOCOM",
        "full": "IEEE International Conference on Computer Communications",
        "base_url": "https://infocom2026.ieee-infocom.org",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp", "/"],
        "area": "Networking",
        "wikicfp_search": "infocom 2026",
    },
    {
        "abbr": "IEEE VTC",
        "full": "IEEE Vehicular Technology Conference",
        "base_url": "https://events.vtsociety.org/vtc2026-fall",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp", "/"],
        "area": "V2X / 5G",
        "wikicfp_search": "vtc 2026",
    },
    {
        "abbr": "IEEE PIMRC",
        "full": "IEEE Int. Symposium on Personal, Indoor and Mobile Radio Communications",
        "base_url": "https://pimrc2026.ieee-pimrc.org",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp", "/"],
        "area": "Wireless",
        "wikicfp_search": "pimrc 2026",
    },
    {
        "abbr": "IEEE IV",
        "full": "IEEE Intelligent Vehicles Symposium",
        "base_url": "https://iv2026.ieee-iv.org",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp", "/"],
        "area": "ITS / V2X",
        "wikicfp_search": "intelligent vehicles symposium 2026",
    },
    {
        "abbr": "IEEE VNC",
        "full": "IEEE Vehicular Networking Conference",
        "base_url": "https://ieee-vnc.org/2026",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp", "/"],
        "area": "V2X / Networking",
        "wikicfp_search": "vehicular networking 2026",
    },
    {
        "abbr": "IEEE ITSC",
        "full": "IEEE Int. Conference on Intelligent Transportation Systems",
        "base_url": "https://ieee-itsc.org/2026",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp", "/"],
        "area": "ITS",
        "wikicfp_search": "itsc 2026",
    },
    {
        "abbr": "ITS World Congress",
        "full": "ITS World Congress",
        "base_url": "https://www.itsworldcongress.com",
        "authors_paths": ["/call-for-papers", "/cfp", "/authors", "/"],
        "area": "ITS",
        "wikicfp_search": "its world congress 2026",
    },
    {
        "abbr": "IEEE GCCE",
        "full": "IEEE Global Conference on Consumer Electronics",
        "base_url": "https://www.ieee-gcce.org/2026",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp", "/"],
        "area": "Consumer Electronics",
        "wikicfp_search": "gcce 2026",
    },
    {
        "abbr": "IEEE WFIoT",
        "full": "IEEE World Forum on Internet of Things",
        "base_url": "https://wfiot2026.iot.ieee.org",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp", "/"],
        "area": "IoT",
        "wikicfp_search": "wfiot 2026",
    },
    {
        "abbr": "IEEE CCNC",
        "full": "IEEE Consumer Communications and Networking Conference",
        "base_url": "https://ccnc2027.ieee-ccnc.org",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp", "/"],
        "area": "Consumer / Networking",
        "wikicfp_search": "ccnc 2027",
    },
    {
        "abbr": "IEEE CTW",
        "full": "IEEE Communication Theory Workshop",
        "base_url": "https://ctw2026.ieee-ctw.org",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp", "/"],
        "area": "Theory",
        "wikicfp_search": "communication theory workshop 2026",
    },
    {
        "abbr": "APCC",
        "full": "Asia-Pacific Conference on Communications",
        "base_url": "https://apcc2026.org",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp", "/"],
        "area": "Asia-Pacific",
        "wikicfp_search": "apcc 2026",
    },
    {
        "abbr": "ICOIN",
        "full": "International Conference on Information Networking",
        "base_url": "https://www.icoin.org",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp", "/"],
        "area": "Networking",
        "wikicfp_search": "icoin 2026",
    },
    {
        "abbr": "WPMC",
        "full": "Int. Symposium on Wireless Personal Multimedia Communications",
        "base_url": "https://www.wpmc-conf.org/2026",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp", "/"],
        "area": "Wireless",
        "wikicfp_search": "wpmc 2026",
    },
    {
        "abbr": "ICETC",
        "full": "Int. Conference on Emerging Technologies for Communications",
        "base_url": "https://www.ieice.org/cs/icetc/2026",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp", "/"],
        "area": "Emerging Tech",
        "wikicfp_search": "icetc 2026",
    },
    {
        "abbr": "ICNC",
        "full": "Int. Conference on Computing, Networking and Communications",
        "base_url": "https://www.conf-icnc.org/2027",
        "authors_paths": ["/authors", "/authors/", "/call-for-papers", "/cfp", "/"],
        "area": "Networking",
        "wikicfp_search": "icnc 2027",
    },
]

# ─────────────────────────────────────────────
# 締切・通知日を示すキーワード
# ─────────────────────────────────────────────

DEADLINE_KEYWORDS = [
    "paper submission deadline",
    "deadline for paper submission",
    "full paper submission",
    "submission deadline",
    "paper submission",
    "abstract submission",
    "abstract deadline",
    "manuscript due",
    "paper due",
    "submission due",
]

NOTIFICATION_KEYWORDS = [
    "notification of acceptance",
    "acceptance notification",
    "author notification",
    "notification date",
    "notification",
]

# これらのキーワードを含むセクション・行は主会議対象外
SKIP_KEYWORDS = [
    "tutorial",
    "workshop",
    "industry forum",
    "panel",
    "demo",
    "demonstration",
    "poster",
    "special session",
    "satellite",
    "competition",
    "challenge",
    "camera ready",
    "camera-ready",
    "final paper",
    "registration",
    "copyright",
    "ieee copyright",
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
    # 括弧内（"(Firm Deadline!)" など）を除去
    raw = re.sub(r"\(.*?\)", "", raw).strip()
    # 複数の日付がある場合（延長前→延長後）は最後の日付を優先
    # "March 1 → March 15, 2026" のような表記に対応
    raw = re.sub(r".*[→⇒→>]", "", raw).strip()

    # YYYY-MM-DD / YYYY/MM/DD
    m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # DD Month YYYY
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", raw)
    if m:
        mon = MONTH_MAP.get(m.group(2).lower())
        if mon:
            return f"{m.group(3)}-{mon:02d}-{int(m.group(1)):02d}"
    # Month DD, YYYY / Month DD YYYY
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2})[,\s]+(\d{4})", raw)
    if m:
        mon = MONTH_MAP.get(m.group(1).lower())
        if mon:
            return f"{m.group(3)}-{mon:02d}-{int(m.group(2)):02d}"
    # Month YYYY（日付なし）は無視
    return None


def parse_conf_dates(raw: str) -> tuple[str | None, str | None]:
    """会議開催日の範囲を (start, end) で返す。"""
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
# HTMLからの日付抽出（構造パース）
# ─────────────────────────────────────────────

def _is_skip_context(text: str) -> bool:
    """スキップすべきセクション（ワークショップ・チュートリアル等）か判定。"""
    t = text.lower()
    return any(kw in t for kw in SKIP_KEYWORDS)


def extract_dates_from_soup(soup: BeautifulSoup) -> dict:
    """
    BeautifulSoup オブジェクトからHTML構造を利用して日付を抽出する。

    対応フォーマット:
      1. <table> の行（ラベル列 + 日付列）
      2. <dl><dt>...</dt><dd>...</dd></dl>
      3. <li> テキスト内の "ラベル: 日付" 形式
      4. 段落・テキストノードの "ラベル: 日付" 形式
    """
    result = {}

    def try_set(key: str, value_text: str, context: str = "") -> bool:
        """未設定のキーに日付をセット。成功したら True を返す。"""
        if key in result:
            return False
        if _is_skip_context(context):
            return False
        d = parse_date(value_text)
        if d:
            result[key] = d
            log.info("  [HTML] %s: %s ← \"%s\"", key, d, value_text[:60])
            return True
        return False

    def classify_label(label: str) -> str | None:
        """ラベルテキストを "deadline" / "notification" / None に分類。"""
        ll = label.lower()
        if _is_skip_context(ll):
            return None
        for kw in DEADLINE_KEYWORDS:
            if kw in ll:
                return "deadline"
        for kw in NOTIFICATION_KEYWORDS:
            if kw in ll:
                return "notification"
        return None

    # ── 1. テーブル行から抽出 ─────────────────────────────────────
    for table in soup.find_all("table"):
        # テーブル自体がスキップ対象か（前後の見出しで判断）
        prev = table.find_previous(["h1", "h2", "h3", "h4", "h5", "h6", "caption"])
        table_context = prev.get_text() if prev else ""

        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            label = cells[0].get_text(" ", strip=True)
            value = cells[1].get_text(" ", strip=True)
            # 3列以上の場合は2列目以降を結合して日付候補にする
            if len(cells) >= 3:
                value = " ".join(c.get_text(" ", strip=True) for c in cells[1:])

            key = classify_label(label)
            if key:
                try_set(key, value, context=table_context + label)

    # ── 2. <dl><dt><dd> から抽出 ─────────────────────────────────
    for dl in soup.find_all("dl"):
        terms = dl.find_all("dt")
        defs = dl.find_all("dd")
        for dt, dd in zip(terms, defs):
            label = dt.get_text(" ", strip=True)
            value = dd.get_text(" ", strip=True)
            key = classify_label(label)
            if key:
                try_set(key, value, context=label)

    # ── 3. <li> の "ラベル: 日付" 形式 ─────────────────────────────
    for li in soup.find_all("li"):
        text = li.get_text(" ", strip=True)
        # "Paper Submission Deadline: March 15, 2026" のような形式
        if ":" in text:
            parts = text.split(":", 1)
            label, value = parts[0], parts[1]
            key = classify_label(label)
            if key:
                try_set(key, value, context=label)
        # "Paper Submission Deadline – March 15, 2026" のような形式
        elif re.search(r"[-–—]", text):
            parts = re.split(r"[-–—]", text, 1)
            if len(parts) == 2:
                label, value = parts[0], parts[1]
                key = classify_label(label)
                if key:
                    try_set(key, value, context=label)

    # ── 4. 段落テキストの行単位スキャン ──────────────────────────
    if "deadline" not in result or "notification" not in result:
        full_text = soup.get_text("\n")
        _extract_from_text(full_text, result)

    return result


def _extract_from_text(text: str, result: dict) -> None:
    """
    プレーンテキストから締切・通知日を抽出して result に追記する。
    HTMLパースの補完として使用。
    """
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # "Important Dates" セクションを優先探索
    in_important_dates = False
    important_dates_lines: list[str] = []
    other_lines: list[str] = []

    for line in lines:
        ll = line.lower()
        if re.search(r"important\s+dates?|key\s+dates?|critical\s+dates?", ll):
            in_important_dates = True
            continue
        # 別のセクション見出しが来たら終了
        if in_important_dates and len(line) < 100 and re.match(r"[A-Z]", line) and line.endswith((".", ":")):
            in_important_dates = False
        if in_important_dates:
            important_dates_lines.append(line)
        else:
            other_lines.append(line)

    # Important Dates セクションを優先、なければ全テキスト
    target_lines = important_dates_lines if important_dates_lines else lines

    for i, line in enumerate(target_lines):
        ll = line.lower()
        if _is_skip_context(ll):
            continue

        # ラベル: 日付 または ラベル  日付 の形式
        key = None
        for kw in DEADLINE_KEYWORDS:
            if kw in ll and "deadline" not in result:
                key = "deadline"
                break
        if key is None:
            for kw in NOTIFICATION_KEYWORDS:
                if kw in ll and "notification" not in result:
                    key = "notification"
                    break
        if key is None:
            continue

        # 同じ行か次の1〜2行から日付を探す
        candidates = [line] + target_lines[i + 1: i + 3]
        for candidate in candidates:
            d = parse_date(candidate)
            if d:
                result[key] = d
                log.info("  [TEXT] %s: %s ← \"%s\"", key, d, line[:60])
                break


# ─────────────────────────────────────────────
# ページ取得（requests → Playwright の順）
# ─────────────────────────────────────────────

def fetch_with_requests(url: str) -> BeautifulSoup | None:
    """requests で取得して BeautifulSoup を返す。失敗時は None。"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200 and len(r.text) > 300:
            log.info("  [requests] 取得成功: %s", url)
            return BeautifulSoup(r.text, "html.parser")
        else:
            log.debug("  [requests] %s → HTTP %d", url, r.status_code)
    except Exception as e:
        log.debug("  [requests] %s → %s", url, e)
    return None


def fetch_with_playwright(url: str) -> BeautifulSoup | None:
    """Playwright で JS レンダリングして BeautifulSoup を返す。失敗時は None。"""
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        log.warning("  Playwright が未インストール（スキップ）")
        return None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            locale="en-US",
        )
        page = ctx.new_page()
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=25000)
            if resp and resp.status == 200:
                page.wait_for_timeout(2500)  # JS レンダリング待機
                html = page.content()
                browser.close()
                if len(html) > 300:
                    log.info("  [playwright] 取得成功: %s", url)
                    return BeautifulSoup(html, "html.parser")
            else:
                log.debug("  [playwright] %s → HTTP %s", url, resp.status if resp else "?")
        except PWTimeout:
            log.debug("  [playwright] %s → タイムアウト", url)
        except Exception as e:
            log.debug("  [playwright] %s → %s", url, e)
        finally:
            try:
                browser.close()
            except Exception:
                pass
    return None


def fetch_authors_page(base_url: str, paths: list[str]) -> tuple[BeautifulSoup | None, str]:
    """
    authors ページを取得して (soup, final_url) を返す。
    requests で試みてコンテンツが薄い場合は Playwright にフォールバック。
    """
    for path in paths:
        url = base_url.rstrip("/") + path

        # Step A: requests（静的HTML）
        soup = fetch_with_requests(url)
        if soup:
            # 「Important Dates」「Submission」などのキーワードがページにあるか確認
            page_text = soup.get_text().lower()
            has_date_info = any(kw in page_text for kw in [
                "important dates", "submission deadline", "paper submission",
                "call for papers", "deadline",
            ])
            if has_date_info:
                return soup, url
            # コンテンツがあるがキーワードなし → JS レンダリングが必要かもしれない

        # Step B: Playwright（JS レンダリング）
        soup_pw = fetch_with_playwright(url)
        if soup_pw:
            page_text = soup_pw.get_text().lower()
            has_date_info = any(kw in page_text for kw in [
                "important dates", "submission deadline", "paper submission",
                "call for papers", "deadline",
            ])
            if has_date_info:
                return soup_pw, url

        # どちらも有効なコンテンツを返さなかった → 次のパスを試す
        log.debug("  %s → 有効なコンテンツなし", url)

    return None, ""


# ─────────────────────────────────────────────
# WikiCFP フォールバック
# ─────────────────────────────────────────────

def wikicfp_fetch(keyword: str) -> dict:
    """WikiCFP から会議情報を取得する（フォールバック用）。"""
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
            dl_parsed = parse_date(dl)
            if dl_parsed:
                best = {
                    "event_id": eid_m.group(1),
                    "title": title,
                    "when": when,
                    "where": where,
                    "deadline": dl,
                    "year": year,
                }
                break

    if not best:
        log.info("  WikiCFP: 有効なエントリなし")
        return {}

    # 詳細ページ取得
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
        log.info("  WikiCFP: deadline_raw=%s", info.get("deadline_raw"))
        return info
    except Exception as e:
        log.warning("  WikiCFP 詳細失敗: %s", e)
        return {"where": best["where"]}


# ─────────────────────────────────────────────
# メイン処理
# ─────────────────────────────────────────────

def process_conference(target: dict, existing: dict) -> dict:
    abbr = target["abbr"]
    log.info("  authors パスを試行: %s", target["authors_paths"])

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

    # ── Step 1: 公式 authors ページを HTML パース ──────────────────
    soup, page_url = fetch_authors_page(target["base_url"], target["authors_paths"])

    if soup:
        dates = extract_dates_from_soup(soup)
        if dates.get("deadline"):
            entry["deadline"]     = dates["deadline"]
            entry["notification"] = dates.get("notification")
            entry["source"]       = page_url
            entry["data_source"]  = "official"
            log.info("  ✓ 公式サイトから取得: deadline=%s, notification=%s",
                     entry["deadline"], entry["notification"])
        else:
            log.info("  公式サイト取得済みだが日付が見つからず")

    # ── Step 2: WikiCFP フォールバック ─────────────────────────────
    if not entry["deadline"]:
        log.info("  → WikiCFP フォールバック: %s", target["wikicfp_search"])
        wdata = wikicfp_fetch(target["wikicfp_search"])
        if wdata:
            dl = parse_date(wdata.get("deadline_raw", ""))
            nt = parse_date(wdata.get("notification_raw", ""))
            if dl:
                entry["deadline"]     = dl
                entry["notification"] = nt
                entry["location"]     = wdata.get("where", "TBD")
                entry["url"]          = wdata.get("url", entry["url"])
                start, end = parse_conf_dates(
                    wdata.get("confDate_raw") or wdata.get("when", "")
                )
                entry["confDate"]     = start
                entry["confDateEnd"]  = end
                entry["data_source"]  = "wikicfp"
                log.info("  ✓ WikiCFP から取得: deadline=%s", entry["deadline"])
        time.sleep(1.5)

    # ── Step 3: 既存データで補完 ────────────────────────────────────
    old = existing.get(abbr, {})
    for field in ("deadline", "notification", "confDate", "confDateEnd", "location", "url", "full"):
        if not entry.get(field) and old.get(field):
            entry[field] = old[field]
            log.info("  補完 [%s] ← 既存データ: %s", field, old[field])

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
            log.info("  完了: deadline=%s, source=%s", entry["deadline"], entry["data_source"])
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
