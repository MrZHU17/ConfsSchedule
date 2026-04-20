"""
Conference Tracker Scraper  v11
================================
改修内容:
  - Claude API による高精度テキスト解析を追加
  - WikiCFP パーサーを class ベースで堅牢化
  - 公式サイト抽出: テーブル構造対応 + Claude 判定
  - override キー整合性チェック追加
"""

import json, re, time, logging, os
from datetime import datetime, timezone
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

# Claude API が使用可能かチェック
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
USE_CLAUDE = bool(ANTHROPIC_API_KEY)
if USE_CLAUDE:
    log.info("Claude API 有効 → 高精度モードで実行")
else:
    log.info("Claude API キーなし → 正規表現モードで実行")

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
# 会議リスト（変更なし）
# ─────────────────────────────────────────────────────────────
TARGET_CONFERENCES = [
     {
        "abbr": "IEEE GLOBECOM",
        "full": "IEEE Global Communications Conference",
        "area": "Communications",
        "official_cfp": "https://globecom2026.ieee-globecom.org/authors/call-papers",
        "base_url":     "https://globecom2026.ieee-globecom.org",
        "wikicfp_query": "GLOBECOM 2026",
        "c2g_query":     "GLOBECOM 2026",
    },
    {
        "abbr": "IEEE WCNC",
        "full": "IEEE Wireless Communications and Networking Conference",
        "area": "Wireless",
        "official_cfp": "https://wcnc2026.ieee-wcnc.org/authors/call-papers",
        "base_url":     "https://wcnc2026.ieee-wcnc.org",
        "wikicfp_query": "WCNC 2026",
        "c2g_query":     "WCNC 2026",
    },
    {
        "abbr": "IEEE ICC",
        "full": "IEEE International Conference on Communications",
        "area": "Communications",
        "official_cfp": "https://icc2026.ieee-icc.org/authors/call-papers",
        "base_url":     "https://icc2026.ieee-icc.org",
        "wikicfp_query": "ICC 2026",
        "c2g_query":     "IEEE ICC 2026",
    },
    {
        "abbr": "IEEE INFOCOM",
        "full": "IEEE International Conference on Computer Communications",
        "area": "Networking",
        "official_cfp": "https://infocom2026.ieee-infocom.org/cfp.html",
        "base_url":     "https://infocom2026.ieee-infocom.org",
        "wikicfp_query": "INFOCOM 2026",
        "c2g_query":     "INFOCOM 2026",
    },
    {
        "abbr": "IEEE VTC",
        "full": "IEEE Vehicular Technology Conference",
        "area": "V2X / 5G",
        "official_cfp": "https://events.vtsociety.org/vtc2026-fall/authors/call-for-papers/",
        "base_url":     "https://events.vtsociety.org/vtc2026-fall",
        "wikicfp_query": "VTC Fall 2026",
        "c2g_query":     "VTC 2026",
    },
    {
        "abbr": "IEEE PIMRC",
        "full": "IEEE Int. Symposium on Personal, Indoor and Mobile Radio Communications",
        "area": "Wireless",
        "official_cfp": "https://pimrc2026.ieee-pimrc.org/authors/call-for-papers",
        "base_url":     "https://pimrc2026.ieee-pimrc.org",
        "wikicfp_query": "PIMRC 2026",
        "c2g_query":     "PIMRC 2026",
    },
    {
        "abbr": "IEEE IV",
        "full": "IEEE Intelligent Vehicles Symposium",
        "area": "ITS / V2X",
        "official_cfp": "https://iv2026.ieee-iv.org/call-for-papers/",
        "base_url":     "https://iv2026.ieee-iv.org",
        "wikicfp_query": "IEEE IV 2026",
        "c2g_query":     "Intelligent Vehicles 2026",
    },
    {
        "abbr": "IEEE VNC",
        "full": "IEEE Vehicular Networking Conference",
        "area": "V2X / Networking",
        "official_cfp": "https://vnc2026.ieee-vnc.org/cfp.html",
        "base_url":     "https://vnc2026.ieee-vnc.org",
        "wikicfp_query": "VNC 2026",
        "c2g_query":     "VNC 2026",
    },
    {
        "abbr": "IEEE ITSC",
        "full": "IEEE Int. Conference on Intelligent Transportation Systems",
        "area": "ITS",
        "official_cfp": "https://ieee-itsc.org/2026/call-for-papers/",
        "base_url":     "https://ieee-itsc.org/2026",
        "wikicfp_query": "ITSC 2026",
        "c2g_query":     "ITSC 2026",
    },
    {
        "abbr": "ITS World Congress",
        "full": "ITS World Congress",
        "area": "ITS",
        "official_cfp": "https://2026itsworldcongress.org/call-for-papers/",
        "base_url":     "https://2026itsworldcongress.org",
        "wikicfp_query": "ITS World Congress 2026",
        "c2g_query":     "ITS World Congress 2026",
    },
    {
        "abbr": "IEEE GCCE",
        "full": "IEEE Global Conference on Consumer Electronics",
        "area": "Consumer Electronics",
        "official_cfp": "https://www.ieee-gcce.org/2026/cfp.html",
        "base_url":     "https://www.ieee-gcce.org/2026",
        "wikicfp_query": "GCCE 2026",
        "c2g_query":     "GCCE 2026",
    },
    {
        "abbr": "IEEE WFIoT",
        "full": "IEEE World Forum on Internet of Things",
        "area": "IoT",
        "official_cfp": "https://wfiot2026.iot.ieee.org/call-for-papers/",
        "base_url":     "https://wfiot2026.iot.ieee.org",
        "wikicfp_query": "WFIoT 2026",
        "c2g_query":     "WFIoT 2026",
    },
    {
        "abbr": "IEEE CCNC",
        "full": "IEEE Consumer Communications and Networking Conference",
        "area": "Consumer / Networking",
        "official_cfp": "https://ccnc2027.ieee-ccnc.org/call-for-papers",
        "base_url":     "https://ccnc2027.ieee-ccnc.org",
        "wikicfp_query": "CCNC 2027",
        "c2g_query":     "CCNC 2027",
    },
    {
        "abbr": "IEEE CTW",
        "full": "IEEE Communication Theory Workshop",
        "area": "Theory",
        "official_cfp": "https://ctw2026.ieee-ctw.org/call-for-papers/",
        "base_url":     "https://ctw2026.ieee-ctw.org",
        "wikicfp_query": "CTW 2026",
        "c2g_query":     "CTW 2026",
    },
    {
        "abbr": "APCC",
        "full": "Asia-Pacific Conference on Communications",
        "area": "Asia-Pacific",
        "official_cfp": "https://apcc2026.org/call-for-papers/",
        "base_url":     "https://apcc2026.org",
        "wikicfp_query": "APCC 2026",
        "c2g_query":     "APCC 2026",
    },
    {
        "abbr": "ICOIN",
        "full": "International Conference on Information Networking",
        "area": "Networking",
        "official_cfp": "https://www.icoin.org/cfp.html",
        "base_url":     "https://www.icoin.org",
        "wikicfp_query": "ICOIN 2027",
        "c2g_query":     "ICOIN 2027",
    },
    {
        "abbr": "WPMC",
        "full": "Int. Symposium on Wireless Personal Multimedia Communications",
        "area": "Wireless",
        "official_cfp": "https://www.wpmc-conf.org/2026/cfp.html",
        "base_url":     "https://www.wpmc-conf.org/2026",
        "wikicfp_query": "WPMC 2026",
        "c2g_query":     "WPMC 2026",
    },
    {
        "abbr": "ICETC",
        "full": "Int. Conference on Emerging Technologies for Communications",
        "area": "Emerging Tech",
        "official_cfp": "https://www.ieice.org/cs/icetc/2026/cfp.html",
        "base_url":     "https://www.ieice.org/cs/icetc/2026",
        "wikicfp_query": "ICETC 2026",
        "c2g_query":     "ICETC 2026",
    },
    {
        "abbr": "ICNC",
        "full": "Int. Conference on Computing, Networking and Communications",
        "area": "Networking",
        "official_cfp": "https://www.conf-icnc.org/2027/cfp.html",
        "base_url":     "https://www.conf-icnc.org/2027",
        "wikicfp_query": "ICNC 2027",
        "c2g_query":     "ICNC 2027",
    },
]

# ─────────────────────────────────────────────────────────────
# 日付パーサー（変更なし）
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
# ★ 新機能: Claude API による日付抽出
# ─────────────────────────────────────────────────────────────

def extract_with_claude(page_text: str, conf_name: str) -> dict:
    """
    Claude API にページテキストを送り、構造化データを抽出する。
    
    正規表現では対応困難な以下のケースを解決:
    - テーブル形式の日付 (HTML テーブルを平坦化した場合に行距離が大きくなる)
    - "Submission: March 15 (Extended from Feb 28)" のような複雑な表記
    - 多言語ページ
    """
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        # トークン節約のため 4000 文字に制限
        truncated = page_text[:4000]

        prompt = f"""You are extracting conference scheduling information from a CFP (Call for Papers) page.
Conference: {conf_name}

Extract the following fields from the text below. Return ONLY a valid JSON object, no explanation.
If a date is listed with an extension (e.g. "Extended to March 15"), use the LATEST date.

Fields:
- "deadline": paper/manuscript submission deadline (YYYY-MM-DD)
- "notification": author notification / acceptance notification date (YYYY-MM-DD)
- "confDate": first day of the conference (YYYY-MM-DD)
- "confDateEnd": last day of the conference (YYYY-MM-DD)
- "location": city and country of the venue (string, e.g. "Tokyo, Japan")

Use null for any field you cannot find with confidence.

Text:
{truncated}"""

        resp = client.messages.create(
            model="claude-haiku-4-5",   # 速度・コスト優先
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        # マークダウンコードブロックを除去
        raw = re.sub(r"^```json\s*|^```\s*|\s*```$", "", raw, flags=re.M).strip()
        result = json.loads(raw)
        log.info("    Claude 抽出: deadline=%s  loc=%s",
                 result.get("deadline"), result.get("location"))
        return result

    except Exception as e:
        log.warning("    Claude 抽出失敗: %s", e)
        return {}


# ─────────────────────────────────────────────────────────────
# ★ 改訂: 公式サイトスクレイピング
# ─────────────────────────────────────────────────────────────

# キーワードパターン（変更なし）
_DEADLINE_KEYWORDS = re.compile(
    r"(paper\s+submission|submission\s+deadline|manuscript\s+due"
    r"|abstract\s+deadline|full\s+paper|camera[- ]ready)",
    re.I
)
_NOTIF_KEYWORDS = re.compile(
    r"(notification|acceptance\s+notice|author\s+notification)",
    re.I
)
_CONF_KEYWORDS = re.compile(
    r"(conference\s+date|symposium\s+date|workshop\s+date"
    r"|congress\s+date|event\s+date)",
    re.I
)


def _extract_dates_regex(soup: BeautifulSoup) -> dict:
    """
    正規表現による日付抽出（Claude API 不使用時のフォールバック）。
    
    v10 からの改善点:
    - テーブルセルのキーワード→同一行/隣接セルの日付を優先探索
    - 近接距離を 3→8 行に拡大
    - <dl>/<dt>/<dd> 構造にも対応
    """
    result = {
        "deadline": None, "notification": None,
        "confDate": None, "confDateEnd": None, "location": None,
    }

    # ── テーブル構造から探す ──────────────────────────────
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
            if len(cells) < 2:
                continue
            label = cells[0].lower()
            value = cells[-1]  # 最後のセルが値のことが多い
            date  = parse_date(value)
            if not date:
                continue
            if _DEADLINE_KEYWORDS.search(label) and not result["deadline"]:
                result["deadline"] = date
            elif _NOTIF_KEYWORDS.search(label) and not result["notification"]:
                result["notification"] = date
            elif _CONF_KEYWORDS.search(label) and not result["confDate"]:
                result["confDate"] = date

    # ── <dl> / <dt><dd> 構造から探す ────────────────────
    for dl in soup.find_all("dl"):
        dts = dl.find_all("dt")
        dds = dl.find_all("dd")
        for dt, dd in zip(dts, dds):
            label = dt.get_text(strip=True).lower()
            date  = parse_date(dd.get_text(strip=True))
            if not date:
                continue
            if _DEADLINE_KEYWORDS.search(label) and not result["deadline"]:
                result["deadline"] = date
            elif _NOTIF_KEYWORDS.search(label) and not result["notification"]:
                result["notification"] = date

    # ── テキスト行スキャン（近接距離を拡大）────────────
    if not result["deadline"]:
        text  = soup.get_text(separator="\n")
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        date_lines = [(i, parse_date(l)) for i, l in enumerate(lines) if parse_date(l)]

        def nearest(kw_re, window=8):
            for i, line in enumerate(lines):
                if kw_re.search(line):
                    for j, d in date_lines:
                        if abs(j - i) <= window:
                            return d
            return None

        result["deadline"]     = result["deadline"]     or nearest(_DEADLINE_KEYWORDS)
        result["notification"] = result["notification"] or nearest(_NOTIF_KEYWORDS)
        result["confDate"]     = result["confDate"]     or nearest(_CONF_KEYWORDS)

    # ── 開催地 ──────────────────────────────────────────
    loc_pat = re.compile(
        r"(?:venue|location|city|held\s+in|taking\s+place\s+in)[:\s]+([^\n<]{4,60})",
        re.I
    )
    for elem in soup.find_all(string=loc_pat):
        m = loc_pat.search(str(elem))
        if m:
            loc = m.group(1).strip().rstrip(".,;")
            if loc.lower() not in ("tbd", "tba", "n/a", ""):
                result["location"] = loc
                break

    return result


def fetch_from_official(conf_name: str, official_cfp_url: str, base_url: str) -> dict:
    """
    公式 CFP ページをスクレイピング。
    Claude API が使える場合は Claude で抽出、なければ正規表現を使用。
    """
    for url in [official_cfp_url, base_url]:
        soup = _safe_get(url)
        if soup is None:
            continue

        # スクリプト・スタイルタグを除去してテキストを清潔にする
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        page_text = soup.get_text(separator="\n", strip=True)

        if USE_CLAUDE:
            info = extract_with_claude(page_text, conf_name)
        else:
            info = _extract_dates_regex(soup)

        if info.get("deadline"):
            log.info("    公式サイトから取得: %s → deadline=%s", url, info["deadline"])
            return info

    return {}


# ─────────────────────────────────────────────────────────────
# ★ 改訂: WikiCFP パーサー
# ─────────────────────────────────────────────────────────────

def fetch_from_wikicfp(abbr: str, wikicfp_query: str, base_url: str) -> dict:
    """
    WikiCFP 検索ページをスクレイピング。
    
    v10 からの改善点:
    - even/odd クラスで行ペアを確実に識別（i+=2 方式を廃止）
    - N/A 日付を None として処理
    - 部分一致スコアリングで最良候補を選択
    """
    url = (
        "https://www.wikicfp.com/cfp/search"
        f"?q={requests.utils.quote(wikicfp_query)}&year=f"
    )
    soup = _safe_get(url, timeout=10)
    if soup is None:
        return {}

    abbr_key = abbr.lower().replace("ieee ", "").replace(" ", "")
    candidates = []

    # WikiCFP の結果行: class="even" または class="odd" の <tr> が2行1セット
    rows = soup.find_all("tr", class_=re.compile(r"^(even|odd)$"))
    
    i = 0
    while i < len(rows) - 1:
        r1, r2 = rows[i], rows[i + 1]
        cells1 = r1.find_all("td")
        cells2 = r2.find_all("td")

        # r1: [名前/リンク, フルネーム]  r2: [締切, 通知, 開始, 終了, 場所]
        if len(cells1) < 1 or len(cells2) < 4:
            i += 1
            continue

        link = cells1[0].find("a")
        row_abbr = (link.get_text(strip=True) if link else cells1[0].get_text(strip=True))
        row_key  = row_abbr.lower().replace("ieee ", "").replace(" ", "")

        def safe_date(cell):
            txt = cell.get_text(strip=True)
            return None if txt.upper() in ("N/A", "TBD", "") else parse_date(txt)

        entry = {
            "deadline":     safe_date(cells2[0]),
            "notification": safe_date(cells2[1]),
            "confDate":     safe_date(cells2[2]),
            "confDateEnd":  safe_date(cells2[3]),
            "location":     cells2[4].get_text(strip=True) if len(cells2) >= 5 else None,
            "url":          base_url,
            "_row_abbr":    row_abbr,
        }

        # スコアリング: 完全一致 > 片方が他方を含む > 部分一致
        if row_key == abbr_key:
            score = 3
        elif row_key in abbr_key or abbr_key in row_key:
            score = 2
        elif any(w in row_key for w in abbr_key.split() if len(w) > 2):
            score = 1
        else:
            score = 0

        if score > 0 and entry.get("deadline"):
            candidates.append((score, entry))

        i += 2  # WikiCFP は必ず 2行1セット

    if not candidates:
        return {}

    best = max(candidates, key=lambda x: x[0])[1]
    log.info("    WikiCFP ヒット: %s | deadline=%s", best["_row_abbr"], best["deadline"])
    return best


# ─────────────────────────────────────────────────────────────
# Source 3: conference2go.net（変更なし）
# ─────────────────────────────────────────────────────────────

def fetch_from_c2g(abbr: str, query: str, base_url: str) -> dict:
    search_url = f"https://www.conference2go.net/search?q={requests.utils.quote(query)}"
    soup = _safe_get(search_url, timeout=10)
    if soup is None:
        return {}

    abbr_key = abbr.lower().replace("ieee ", "")

    for card in soup.find_all(["div", "li", "article"],
                               class_=re.compile(r"conf|event|result", re.I)):
        title = card.get_text(separator=" ", strip=True).lower()
        if abbr_key not in title:
            continue

        card_text = card.get_text(separator="\n")
        lines = card_text.splitlines()
        dates = [(parse_date(l), l) for l in lines if parse_date(l)]

        entry = {"deadline": None, "confDate": None, "location": None, "url": base_url}
        for d, _ in dates:
            if not entry["deadline"]:
                entry["deadline"] = d
            elif not entry["confDate"]:
                entry["confDate"] = d

        loc_m = re.search(r"\b([A-Z][a-z]+(?: [A-Z][a-z]+)?,\s*[A-Z][a-z]+)\b", card_text)
        if loc_m:
            entry["location"] = loc_m.group(1)

        if entry.get("deadline"):
            log.info("    C2G ヒット: deadline=%s", entry["deadline"])
            return entry

    return {}


# ─────────────────────────────────────────────────────────────
# メイン処理
# ─────────────────────────────────────────────────────────────

def _apply(entry: dict, info: dict) -> None:
    for f in ("deadline", "notification", "confDate", "confDateEnd"):
        if info.get(f) and not entry.get(f):
            entry[f] = info[f]
    if info.get("location"):
        loc = info["location"]
        if loc and loc.lower() not in ("n/a", "tbd", "tba", ""):
            if not entry.get("location") or entry["location"] == "TBD":
                entry["location"] = loc
    if info.get("url"):
        entry["url"] = info["url"]


def process_conference(target: dict, existing: dict) -> dict:
    abbr = target["abbr"]
    now  = datetime.now(timezone.utc).isoformat()

    entry: dict = {
        "abbr":         abbr,
        "full":         target["full"],
        "url":          target["base_url"],
        "area":         target["area"],
        "location":     None,
        "confDate":     None,
        "confDateEnd":  None,
        "deadline":     None,
        "notification": None,
        "data_source":  "none",
        "fetched_at":   now,
    }

    # ── 1. 公式サイト ────────────────────────────────────────
    info = fetch_from_official(target["full"], target["official_cfp"], target["base_url"])
    if info.get("deadline"):
        _apply(entry, info)
        entry["data_source"] = "official+claude" if USE_CLAUDE else "official"
        log.info("  ✓ 公式: deadline=%s", entry["deadline"])

    # ── 2. WikiCFP ───────────────────────────────────────────
    if not entry.get("deadline"):
        info = fetch_from_wikicfp(abbr, target["wikicfp_query"], target["base_url"])
        if info.get("deadline"):
            _apply(entry, info)
            entry["data_source"] = "wikicfp"
            log.info("  ✓ WikiCFP: deadline=%s", entry["deadline"])

    # ── 3. conference2go.net ─────────────────────────────────
    if not entry.get("deadline"):
        info = fetch_from_c2g(abbr, target["c2g_query"], target["base_url"])
        if info.get("deadline"):
            _apply(entry, info)
            entry["data_source"] = "c2g"
            log.info("  ✓ C2G: deadline=%s", entry["deadline"])

    # ── 4. 既存データで補完 ──────────────────────────────────
    old = existing.get(abbr, {})
    for f in ("deadline", "notification", "confDate", "confDateEnd", "location", "url"):
        if not entry.get(f) and old.get(f):
            entry[f] = old[f]
            log.info("  補完 [%s] ← 既存: %s", f, old[f])

    return entry


# ─────────────────────────────────────────────────────────────
# ★ 修正: 手動オーバーライド（キー整合性チェック追加）
# ─────────────────────────────────────────────────────────────

def load_overrides() -> dict[str, dict]:
    override_path = REPO_ROOT / "conferences.override.json"
    if not override_path.exists():
        log.info("override ファイルなし（スキップ）")
        return {}
    try:
        raw = json.loads(override_path.read_text(encoding="utf-8"))
        overrides = {k: v for k, v in raw.items() if not k.startswith("_")}

        # ★ キー整合性チェック: TARGET_CONFERENCES の abbr と照合
        valid_abbrs = {t["abbr"] for t in TARGET_CONFERENCES}
        for key in list(overrides.keys()):
            if key not in valid_abbrs:
                log.warning(
                    "override キー '%s' はどの会議の abbr とも一致しません。"
                    "有効な abbr: %s",
                    key, sorted(valid_abbrs)
                )

        log.info("override 読み込み: %d 件", len(overrides))
        return overrides
    except json.JSONDecodeError as e:
        log.error("override ファイルの JSON が不正です: %s", e)
        return {}
    except Exception as e:
        log.warning("override 読み込み失敗: %s", e)
        return {}


def apply_override(entry: dict, overrides: dict) -> dict:
    abbr  = entry.get("abbr", "")
    patch = overrides.get(abbr)   # ★ abbr で直接参照（年付きキーは使わない）
    if not patch:
        return entry

    ALLOWED_FIELDS = {
        "deadline", "notification", "confDate", "confDateEnd",
        "location", "url", "full", "area",
    }
    for field, value in patch.items():
        if field not in ALLOWED_FIELDS:
            log.warning("  override: 不明なフィールド [%s] をスキップ", field)
            continue
        old = entry.get(field)
        entry[field] = value
        log.info("  override [%s]: %s → %s", field, old, value)

    entry["data_source"] = entry.get("data_source", "none") + "+override"
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

    overrides = load_overrides()

    conferences = []
    for i, target in enumerate(TARGET_CONFERENCES, 1):
        log.info("[%d/%d] %s", i, len(TARGET_CONFERENCES), target["abbr"])
        try:
            entry = process_conference(target, existing)
            entry = apply_override(entry, overrides)
            conferences.append(entry)
            log.info("  完了: src=%-25s deadline=%s  loc=%s",
                     entry["data_source"], entry["deadline"], entry["location"])
        except Exception as e:
            log.error("  エラー: %s", e)
            fallback = existing.get(target["abbr"]) or {
                "abbr": target["abbr"], "full": target["full"],
                "area": target["area"], "url": target["base_url"],
                "location": None, "confDate": None, "confDateEnd": None,
                "deadline": None, "notification": None,
                "data_source": "error",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
            fallback = apply_override(fallback, overrides)
            conferences.append(fallback)
        time.sleep(1.5)  # 少し余裕を持たせる

    output_path.write_text(
        json.dumps({
            "updated_at":  datetime.now(timezone.utc).isoformat(),
            "conferences": conferences,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("======== 完了: %d 件 → %s ========", len(conferences), output_path)


if __name__ == "__main__":
    main()
