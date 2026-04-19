"""
Conference Tracker Scraper  v10
================================
API キー不要。純粋なWebスクレイピングのみ。

取得元（優先順）:
  1. 各会議の公式 CFP ページ
  2. WikiCFP
  3. conference2go.net
  4. 既存 conferences.json で補完
"""

import json, re, time, logging
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
# 会議リスト
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
    # 延長表記「旧 → 新」は最後を使う
    for sep in ("→", "⇒", "->", "extended to", "Extended to"):
        if sep in raw:
            raw = raw.split(sep)[-1].strip()
            break
    # YYYY-MM-DD
    m = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # DD Mon YYYY  (e.g. "15 March 2026")
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", raw)
    if m:
        mon = MONTH_MAP.get(m.group(2).lower())
        if mon:
            return f"{m.group(3)}-{mon:02d}-{int(m.group(1)):02d}"
    # Mon DD, YYYY  (e.g. "March 15, 2026")
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2})[,\s]+(\d{4})", raw)
    if m:
        mon = MONTH_MAP.get(m.group(1).lower())
        if mon:
            return f"{m.group(3)}-{mon:02d}-{int(m.group(2)):02d}"
    return None


def _safe_get(url: str, timeout: int = 12) -> BeautifulSoup | None:
    """GETリクエストを実行し BeautifulSoup を返す。失敗時は None。"""
    try:
        r = SESSION.get(url, timeout=timeout)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        log.warning("    GET失敗 [%s]: %s", url, e)
        return None


# ─────────────────────────────────────────────────────────────
# Source 1: 公式サイト CFP ページ
# ─────────────────────────────────────────────────────────────

# 締切日を示すキーワードパターン
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

def _extract_dates_from_soup(soup: BeautifulSoup) -> dict:
    """
    CFP ページの HTML から締切・通知・会議日程・開催地を抽出。
    キーワードの近くにある日付文字列を探す。
    """
    result = {
        "deadline": None,
        "notification": None,
        "confDate": None,
        "confDateEnd": None,
        "location": None,
    }

    text = soup.get_text(separator="\n")
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # 日付を含む行を全部抽出してインデックスを記録
    date_lines: list[tuple[int, str, str]] = []  # (行番号, 行テキスト, パース済み日付)
    for idx, line in enumerate(lines):
        d = parse_date(line)
        if d:
            date_lines.append((idx, line, d))

    def nearest_date(keyword_re, start_range=3):
        """キーワードに近い行から日付を見つける。"""
        for idx, line in enumerate(lines):
            if keyword_re.search(line):
                # キーワード行の前後 start_range 行以内の日付を返す
                for dl_idx, dl_line, dl_date in date_lines:
                    if abs(dl_idx - idx) <= start_range:
                        return dl_date
        return None

    result["deadline"]     = nearest_date(_DEADLINE_KEYWORDS)
    result["notification"] = nearest_date(_NOTIF_KEYWORDS)
    result["confDate"]     = nearest_date(_CONF_KEYWORDS)

    # 開催地: "Location:", "Venue:", "City," などのパターン
    loc_pat = re.compile(
        r"(venue|location|city|held\s+in|taking\s+place)[:\s]+([^\n]{3,60})",
        re.I
    )
    for line in lines:
        m = loc_pat.search(line)
        if m:
            loc = m.group(2).strip().rstrip(".,")
            if len(loc) > 3 and loc.lower() not in ("tbd", "tba", "n/a"):
                result["location"] = loc
                break

    return result


def fetch_from_official(official_cfp_url: str, base_url: str) -> dict:
    """公式 CFP ページをスクレイピング。失敗時はトップページを試みる。"""
    for url in [official_cfp_url, base_url]:
        soup = _safe_get(url)
        if soup is None:
            continue
        info = _extract_dates_from_soup(soup)
        if info.get("deadline"):
            log.info("    公式サイトから取得: %s → deadline=%s", url, info["deadline"])
            return info
    return {}


# ─────────────────────────────────────────────────────────────
# Source 2: WikiCFP
# ─────────────────────────────────────────────────────────────

def fetch_from_wikicfp(abbr: str, wikicfp_query: str, base_url: str) -> dict:
    """WikiCFP 検索ページをスクレイピング。"""
    url = f"https://www.wikicfp.com/cfp/search?q={requests.utils.quote(wikicfp_query)}&year=f"
    soup = _safe_get(url, timeout=10)
    if soup is None:
        return {}

    abbr_key = abbr.lower().replace("ieee ", "")
    best = {}

    # WikiCFP の結果テーブルをパース
    for table in soup.find_all("table", attrs={"cellpadding": "3"}):
        rows = table.find_all("tr")
        i = 0
        while i < len(rows) - 1:
            r1, r2 = rows[i], rows[i + 1]
            cols1 = r1.find_all("td")
            cols2 = r2.find_all("td")

            if len(cols1) < 2 or len(cols2) < 4:
                i += 1
                continue

            link     = cols1[0].find("a")
            row_abbr = (link.get_text(strip=True) if link else cols1[0].get_text(strip=True)).lower()
            row_abbr = row_abbr.replace("ieee ", "")

            entry = {
                "deadline":    parse_date(cols2[0].get_text(strip=True)),
                "notification": parse_date(cols2[1].get_text(strip=True)),
                "confDate":    parse_date(cols2[2].get_text(strip=True)),
                "confDateEnd": parse_date(cols2[3].get_text(strip=True)),
                "location":    cols2[4].get_text(strip=True) if len(cols2) >= 5 else None,
                "url":         base_url,
            }

            if abbr_key in row_abbr or row_abbr in abbr_key:
                log.info("    WikiCFP ヒット: %s | deadline=%s", row_abbr, entry["deadline"])
                return entry  # 完全一致
            if not best and entry.get("deadline"):
                best = entry   # 最初のヒットを保持

            i += 2

    if best:
        log.info("    WikiCFP 先頭使用: deadline=%s", best.get("deadline"))
    return best


# ─────────────────────────────────────────────────────────────
# Source 3: conference2go.net
# ─────────────────────────────────────────────────────────────

def fetch_from_c2g(abbr: str, query: str, base_url: str) -> dict:
    """conference2go.net をスクレイピング（WikiCFP の代替）。"""
    search_url = f"https://www.conference2go.net/search?q={requests.utils.quote(query)}"
    soup = _safe_get(search_url, timeout=10)
    if soup is None:
        return {}

    abbr_key = abbr.lower().replace("ieee ", "")

    for card in soup.find_all(["div", "li", "article"], class_=re.compile(r"conf|event|result", re.I)):
        title = card.get_text(separator=" ", strip=True).lower()
        if abbr_key not in title:
            continue

        # カード内から日付文字列を探す
        card_text = card.get_text(separator="\n")
        lines = card_text.splitlines()
        dates = [(parse_date(l), l) for l in lines if parse_date(l)]

        entry = {"deadline": None, "confDate": None, "location": None, "url": base_url}
        for d, raw in dates:
            if not entry["deadline"]:
                entry["deadline"] = d
            elif not entry["confDate"]:
                entry["confDate"] = d

        # 開催地
        loc_m = re.search(r"\b([A-Z][a-z]+(?: [A-Z][a-z]+)?,\s*[A-Z][a-z]+)\b", card_text)
        if loc_m:
            entry["location"] = loc_m.group(1)

        if entry.get("deadline"):
            log.info("    C2G ヒット: deadline=%s", entry["deadline"])
            return entry

    return {}


# ─────────────────────────────────────────────────────────────
# メイン処理（優先順位: 公式 → WikiCFP → C2G → 既存データ）
# ─────────────────────────────────────────────────────────────

def _apply(entry: dict, info: dict) -> None:
    """info の値を entry に適用する（既存値は上書きしない）。"""
    for f in ("deadline", "notification", "confDate", "confDateEnd"):
        if info.get(f) and not entry.get(f):
            entry[f] = info[f]
    if info.get("location") and (not entry.get("location") or entry["location"] == "TBD"):
        loc = info["location"]
        if loc and loc.lower() not in ("n/a", "tbd", "tba", ""):
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
    info = fetch_from_official(target["official_cfp"], target["base_url"])
    if info.get("deadline"):
        _apply(entry, info)
        entry["data_source"] = "official"
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
# 手動オーバーライド読み込み
# ─────────────────────────────────────────────────────────────

def load_overrides() -> dict[str, dict]:
    """
    conferences.override.json を読み込む。
    ファイルがなければ空辞書を返す（エラーにしない）。
    """
    override_path = REPO_ROOT / "conferences.override.json"
    if not override_path.exists():
        log.info("override ファイルなし（スキップ）")
        return {}
    try:
        raw = json.loads(override_path.read_text(encoding="utf-8"))
        # _comment キーは無視
        overrides = {k: v for k, v in raw.items() if not k.startswith("_")}
        log.info("override 読み込み: %d 件", len(overrides))
        return overrides
    except Exception as e:
        log.warning("override 読み込み失敗: %s", e)
        return {}


def apply_override(entry: dict, overrides: dict) -> dict:
    """
    overrides に該当エントリがあれば、そのフィールドで entry を上書きする。
    上書きされたフィールドはログに記録する。
    """
    abbr = entry.get("abbr", "")
    patch = overrides.get(abbr)
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
    
    # 既存データ読み込み
    existing: dict[str, dict] = {}
    if output_path.exists():
        try:
            old = json.loads(output_path.read_text(encoding="utf-8"))
            old_list = old.get("conferences", old) if isinstance(old, dict) else old
            existing = {c["abbr"]: c for c in old_list if isinstance(c, dict)}
            log.info("既存データ読み込み: %d 件", len(existing))
        except Exception as e:
            log.warning("既存データ読み込み失敗: %s", e)

    # ここで override を読み込む ← 追加
    overrides = load_overrides()

    conferences = []
    for i, target in enumerate(TARGET_CONFERENCES, 1):
        log.info("[%d/%d] %s", i, len(TARGET_CONFERENCES), target["abbr"])
        try:
            entry = process_conference(target, existing)
            entry = apply_override(entry, overrides)  # ← 追加（スクレイピング後に適用）
            conferences.append(entry)
            log.info("  完了: src=%-20s deadline=%s  loc=%s",
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
            # エラー時もoverrideは適用する ← 追加
            fallback = apply_override(fallback, overrides)
            conferences.append(fallback)
        time.sleep(1)

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
