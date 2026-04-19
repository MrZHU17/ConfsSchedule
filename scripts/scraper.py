"""
Conference Tracker Scraper  v9
================================
修正点:
  1. anthropic-beta ヘッダー追加（web_search ツール必須）
  2. tool_use の複数ターンループ実装
  3. WikiCFP 直接スクレイピングをプライマリに
  4. Claude API（web_search）をセカンダリフォールバックに
"""

import json, os, re, time, logging
from datetime import datetime, timezone
from pathlib import Path
import requests
from bs4 import BeautifulSoup

REPO_ROOT  = Path(__file__).parent.parent
API_URL    = "https://api.anthropic.com/v1/messages"
MODEL      = "claude-sonnet-4-20250514"
WIKICFP_SEARCH = "https://www.wikicfp.com/cfp/search?q={query}&year=f"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# 会議リスト
# ─────────────────────────────────────────────────────────────
TARGET_CONFERENCES = [
    {
        "abbr": "IEEE GLOBECOM",
        "full": "IEEE Global Communications Conference",
        "base_url": "https://globecom2026.ieee-globecom.org",
        "area": "Communications",
        "wikicfp_query": "GLOBECOM 2026",
        "search_query": "IEEE GLOBECOM 2026 paper submission deadline",
    },
    {
        "abbr": "IEEE WCNC",
        "full": "IEEE Wireless Communications and Networking Conference",
        "base_url": "https://wcnc2026.ieee-wcnc.org",
        "area": "Wireless",
        "wikicfp_query": "WCNC 2026",
        "search_query": "IEEE WCNC 2026 paper submission deadline",
    },
    {
        "abbr": "IEEE ICC",
        "full": "IEEE International Conference on Communications",
        "base_url": "https://icc2026.ieee-icc.org",
        "area": "Communications",
        "wikicfp_query": "ICC 2026",
        "search_query": "IEEE ICC 2026 paper submission deadline",
    },
    {
        "abbr": "IEEE INFOCOM",
        "full": "IEEE International Conference on Computer Communications",
        "base_url": "https://infocom2026.ieee-infocom.org",
        "area": "Networking",
        "wikicfp_query": "INFOCOM 2026",
        "search_query": "IEEE INFOCOM 2026 paper submission deadline",
    },
    {
        "abbr": "IEEE VTC",
        "full": "IEEE Vehicular Technology Conference",
        "base_url": "https://events.vtsociety.org/vtc2026-fall",
        "area": "V2X / 5G",
        "wikicfp_query": "VTC Fall 2026",
        "search_query": "IEEE VTC Fall 2026 paper submission deadline",
    },
    {
        "abbr": "IEEE PIMRC",
        "full": "IEEE Int. Symposium on Personal, Indoor and Mobile Radio Communications",
        "base_url": "https://pimrc2026.ieee-pimrc.org",
        "area": "Wireless",
        "wikicfp_query": "PIMRC 2026",
        "search_query": "IEEE PIMRC 2026 paper submission deadline",
    },
    {
        "abbr": "IEEE IV",
        "full": "IEEE Intelligent Vehicles Symposium",
        "base_url": "https://iv2026.ieee-iv.org",
        "area": "ITS / V2X",
        "wikicfp_query": "IEEE IV 2026",
        "search_query": "IEEE Intelligent Vehicles Symposium 2026 submission deadline",
    },
    {
        "abbr": "IEEE VNC",
        "full": "IEEE Vehicular Networking Conference",
        "base_url": "https://vnc2026.ieee-vnc.org",
        "area": "V2X / Networking",
        "wikicfp_query": "VNC 2026",
        "search_query": "IEEE VNC Vehicular Networking Conference 2026 submission deadline",
    },
    {
        "abbr": "IEEE ITSC",
        "full": "IEEE Int. Conference on Intelligent Transportation Systems",
        "base_url": "https://ieee-itsc.org/2026",
        "area": "ITS",
        "wikicfp_query": "ITSC 2026",
        "search_query": "IEEE ITSC 2026 paper submission deadline",
    },
    {
        "abbr": "ITS World Congress",
        "full": "ITS World Congress",
        "base_url": "https://2026itsworldcongress.org",
        "area": "ITS",
        "wikicfp_query": "ITS World Congress 2026",
        "search_query": "ITS World Congress 2026 paper submission deadline",
    },
    {
        "abbr": "IEEE GCCE",
        "full": "IEEE Global Conference on Consumer Electronics",
        "base_url": "https://www.ieee-gcce.org/2026",
        "area": "Consumer Electronics",
        "wikicfp_query": "GCCE 2026",
        "search_query": "IEEE GCCE 2026 paper submission deadline",
    },
    {
        "abbr": "IEEE WFIoT",
        "full": "IEEE World Forum on Internet of Things",
        "base_url": "https://wfiot2026.iot.ieee.org",
        "area": "IoT",
        "wikicfp_query": "WFIoT 2026",
        "search_query": "IEEE WFIoT World Forum IoT 2026 submission deadline",
    },
    {
        "abbr": "IEEE CCNC",
        "full": "IEEE Consumer Communications and Networking Conference",
        "base_url": "https://ccnc2027.ieee-ccnc.org",
        "area": "Consumer / Networking",
        "wikicfp_query": "CCNC 2027",
        "search_query": "IEEE CCNC 2027 paper submission deadline",
    },
    {
        "abbr": "IEEE CTW",
        "full": "IEEE Communication Theory Workshop",
        "base_url": "https://ctw2026.ieee-ctw.org",
        "area": "Theory",
        "wikicfp_query": "CTW 2026",
        "search_query": "IEEE CTW Communication Theory Workshop 2026 submission deadline",
    },
    {
        "abbr": "APCC",
        "full": "Asia-Pacific Conference on Communications",
        "base_url": "https://apcc2026.org",
        "area": "Asia-Pacific",
        "wikicfp_query": "APCC 2026",
        "search_query": "APCC Asia-Pacific Conference on Communications 2026 submission deadline",
    },
    {
        "abbr": "ICOIN",
        "full": "International Conference on Information Networking",
        "base_url": "https://www.icoin.org",
        "area": "Networking",
        "wikicfp_query": "ICOIN 2026",
        "search_query": "ICOIN International Conference Information Networking 2026 submission deadline",
    },
    {
        "abbr": "WPMC",
        "full": "Int. Symposium on Wireless Personal Multimedia Communications",
        "base_url": "https://www.wpmc-conf.org/2026",
        "area": "Wireless",
        "wikicfp_query": "WPMC 2026",
        "search_query": "WPMC 2026 Wireless Personal Multimedia Communications submission deadline",
    },
    {
        "abbr": "ICETC",
        "full": "Int. Conference on Emerging Technologies for Communications",
        "base_url": "https://www.ieice.org/cs/icetc/2026",
        "area": "Emerging Tech",
        "wikicfp_query": "ICETC 2026",
        "search_query": "ICETC 2026 Emerging Technologies Communications submission deadline",
    },
    {
        "abbr": "ICNC",
        "full": "Int. Conference on Computing, Networking and Communications",
        "base_url": "https://www.conf-icnc.org/2027",
        "area": "Networking",
        "wikicfp_query": "ICNC 2027",
        "search_query": "ICNC 2027 Computing Networking Communications submission deadline",
    },
]

# ─────────────────────────────────────────────────────────────
# 共通ヘッダー（修正①: anthropic-beta を追加）
# ─────────────────────────────────────────────────────────────

def _api_headers() -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY が設定されていません。")
    return {
        "x-api-key":         api_key,
        "anthropic-version": "2023-06-01",
        "anthropic-beta":    "web-search-2025-03-05",   # ← 修正①: 必須ヘッダー
        "content-type":      "application/json",
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
    # 延長表記「旧日付 → 新日付」は最新（末尾）を使う
    for sep in ("→", "⇒", "->"):
        if sep in raw:
            raw = raw.split(sep)[-1].strip()
            break
    # YYYY-MM-DD / YYYY/MM/DD
    m = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # DD Mon YYYY
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", raw)
    if m:
        mon = MONTH_MAP.get(m.group(2).lower())
        if mon:
            return f"{m.group(3)}-{mon:02d}-{int(m.group(1)):02d}"
    # Mon DD, YYYY
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2})[,\s]+(\d{4})", raw)
    if m:
        mon = MONTH_MAP.get(m.group(1).lower())
        if mon:
            return f"{m.group(3)}-{mon:02d}-{int(m.group(2)):02d}"
    return None

# ─────────────────────────────────────────────────────────────
# プライマリ: WikiCFP 直接スクレイピング
# ─────────────────────────────────────────────────────────────

_HEADERS_BROWSER = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; ConferenceTracker/1.0; "
        "+https://github.com/YOUR_USERNAME/conf-tracker)"
    )
}

def _wikicfp_search_page(query: str) -> list[dict]:
    """
    WikiCFP 検索結果ページを解析して会議リストを返す。
    各要素: {abbr, full, deadline, notification, confDate, confDateEnd, location, url}
    """
    url = WIKICFP_SEARCH.format(query=requests.utils.quote(query))
    try:
        resp = requests.get(url, headers=_HEADERS_BROWSER, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        log.warning("  WikiCFP 検索失敗: %s", e)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []

    # WikiCFP の検索結果テーブル（class="contsec" の中にある）
    # 行構造: 奇数行=会議名/リンク、偶数行=日程詳細
    tables = soup.find_all("table", attrs={"cellpadding": "3"})
    for table in tables:
        rows = table.find_all("tr")
        i = 0
        while i < len(rows) - 1:
            row1 = rows[i]
            row2 = rows[i + 1] if i + 1 < len(rows) else None
            cols1 = row1.find_all("td")
            if len(cols1) >= 2:
                link = cols1[0].find("a")
                abbr_text  = link.get_text(strip=True) if link else cols1[0].get_text(strip=True)
                full_text  = cols1[1].get_text(strip=True)
                conf_url   = ("https://www.wikicfp.com" + link["href"]) if link and link.get("href") else None

                entry = {
                    "abbr":        abbr_text,
                    "full":        full_text,
                    "url":         conf_url,
                    "deadline":    None,
                    "notification": None,
                    "confDate":    None,
                    "confDateEnd": None,
                    "location":    None,
                }

                if row2:
                    cols2 = row2.find_all("td")
                    # WikiCFP 列順: submission | notification | conf_start | conf_end | location
                    if len(cols2) >= 4:
                        entry["deadline"]     = parse_date(cols2[0].get_text(strip=True))
                        entry["notification"] = parse_date(cols2[1].get_text(strip=True))
                        entry["confDate"]     = parse_date(cols2[2].get_text(strip=True))
                        entry["confDateEnd"]  = parse_date(cols2[3].get_text(strip=True))
                    if len(cols2) >= 5:
                        loc = cols2[4].get_text(strip=True)
                        if loc and loc.lower() not in ("n/a", "tbd", ""):
                            entry["location"] = loc
                    i += 2
                    results.append(entry)
                    continue
            i += 1

    return results


def fetch_from_wikicfp(abbr: str, wikicfp_query: str, base_url: str) -> dict:
    """WikiCFP で会議情報を取得。最もマッチする行を返す。"""
    results = _wikicfp_search_page(wikicfp_query)
    if not results:
        return {}

    abbr_lower = abbr.lower().replace("ieee ", "")
    for r in results:
        r_abbr = r["abbr"].lower().replace("ieee ", "")
        if abbr_lower in r_abbr or r_abbr in abbr_lower:
            # WikiCFP のURLではなく公式サイトURLを使用
            r["url"] = base_url
            log.info("  WikiCFP ヒット: %s | deadline=%s | conf=%s",
                     r["abbr"], r["deadline"], r["confDate"])
            return r

    # 完全一致がなければ最初の結果を返す（クエリが具体的なため）
    if results:
        results[0]["url"] = base_url
        log.info("  WikiCFP 先頭使用: %s | deadline=%s",
                 results[0]["abbr"], results[0]["deadline"])
        return results[0]

    return {}

# ─────────────────────────────────────────────────────────────
# セカンダリ: Claude API + web_search（修正②: 複数ターンループ）
# ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a research assistant that finds academic conference submission deadlines.
Search the web and return ONLY a JSON object — no markdown, no explanation.

Rules:
- Find the LATEST deadline including any extensions.
- Focus on MAIN paper submission only (not workshop/tutorial/demo).
- All dates in ISO format: "YYYY-MM-DD". Unknown fields → null.

JSON schema (return exactly this):
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

def _extract_json(text: str) -> dict:
    text = re.sub(r"```(?:json)?|```", "", text).strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group())
    except json.JSONDecodeError:
        return {}


def fetch_from_api(abbr: str, search_query: str) -> dict:
    """
    修正②: tool_use の複数ターン会話ループを実装。
    stop_reason が "end_turn" になるまでリクエストを繰り返す。
    """
    messages = [
        {
            "role": "user",
            "content": (
                f"Find the latest paper submission deadline for: {abbr}\n"
                f"Search: {search_query}\n"
                f"Return ONLY the JSON object."
            ),
        }
    ]

    max_turns = 6  # tool_use が繰り返される場合の安全ループ上限
    for turn in range(max_turns):
        payload = {
            "model":      MODEL,
            "max_tokens": 1024,
            "system":     SYSTEM_PROMPT,
            "tools": [
                {
                    "type": "web_search_20250305",
                    "name": "web_search",
                    # 検索回数を制限してコスト抑制
                    "max_uses": 3,
                }
            ],
            "messages": messages,
        }

        try:
            r = requests.post(
                API_URL,
                headers=_api_headers(),
                json=payload,
                timeout=90,
            )
            r.raise_for_status()
        except requests.HTTPError as e:
            log.error("  API HTTPエラー [%s]: %s", r.status_code, r.text[:300])
            return {}
        except Exception as e:
            log.error("  API呼び出し失敗: %s", e)
            return {}

        data        = r.json()
        stop_reason = data.get("stop_reason")
        content     = data.get("content", [])

        # アシスタントの返答を会話履歴に追加
        messages.append({"role": "assistant", "content": content})

        if stop_reason == "end_turn":
            # テキストブロックを結合してJSONを抽出
            text = "".join(
                b.get("text", "")
                for b in content
                if b.get("type") == "text"
            )
            result = _extract_json(text)
            if result:
                log.info("  API結果: deadline=%s, conf=%s, confidence=%s",
                         result.get("deadline"), result.get("confDate"),
                         result.get("confidence"))
            else:
                log.warning("  APIからJSONを抽出できませんでした: %s", text[:200])
            return result

        elif stop_reason == "tool_use":
            # ── 修正②の核心: tool_result を組み立てて次のターンへ ──
            tool_results = []
            for block in content:
                if block.get("type") == "tool_use":
                    tool_id   = block.get("id", "")
                    tool_name = block.get("name", "")
                    # web_search はサーバーサイドで Anthropic が実行する。
                    # クライアントは「ツール結果を受け取った」という形式で
                    # 空の tool_result を返せばよい（実際の検索結果は
                    # Anthropic がレスポンスに埋め込む）。
                    #
                    # ただし API バージョンによっては tool_result が
                    # コンテンツブロック内に既に含まれている場合もある。
                    # その場合は content ブロックの "tool_result" 型を探す。
                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": tool_id,
                        "content":     "",   # web_search はサーバー側処理
                    })

            if tool_results:
                messages.append({
                    "role":    "user",
                    "content": tool_results,
                })
            else:
                log.warning("  tool_use ブロックが見つかりません。ループを終了します。")
                break

        elif stop_reason == "max_tokens":
            log.warning("  max_tokens に達しました。")
            break
        else:
            log.warning("  予期しない stop_reason: %s", stop_reason)
            break

    return {}


# ─────────────────────────────────────────────────────────────
# 会議1件の処理（WikiCFP → API → 既存データ の優先順位）
# ─────────────────────────────────────────────────────────────

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

    # ── Step 1: WikiCFP（プライマリ・無料・高信頼性）──────────
    info = fetch_from_wikicfp(abbr, target["wikicfp_query"], target["base_url"])
    if info and info.get("deadline"):
        _apply_info(entry, info)
        entry["data_source"] = "wikicfp"
        log.info("  [WikiCFP] deadline=%s, location=%s", entry["deadline"], entry["location"])

    # ── Step 2: Claude API + web_search（WikiCFPで取れなかった場合）──
    if not entry.get("deadline"):
        log.info("  WikiCFP で deadline 未取得 → API にフォールバック")
        info = fetch_from_api(abbr, target["search_query"])
        if info and (info.get("deadline") or info.get("confDate")):
            _apply_info(entry, info)
            entry["data_source"] = "api_search"
            log.info("  [API] deadline=%s, location=%s", entry["deadline"], entry["location"])

    # ── Step 3: 既存データで欠損フィールドを補完 ────────────────
    old = existing.get(abbr, {})
    for field in ("deadline", "notification", "confDate", "confDateEnd", "location", "url", "full"):
        if not entry.get(field) and old.get(field):
            entry[field] = old[field]
            log.info("  補完 [%s] ← 既存: %s", field, old[field])

    return entry


def _apply_info(entry: dict, info: dict) -> None:
    """info 辞書の値を entry に適用する（None/空文字は上書きしない）。"""
    for field in ("deadline", "notification", "confDate", "confDateEnd"):
        raw = info.get(field)
        if raw:
            parsed = parse_date(str(raw))
            entry[field] = parsed or raw
    if info.get("location"):
        entry["location"] = info["location"]
    if info.get("url"):
        entry["url"] = info["url"]
    if info.get("full"):
        entry["full"] = info["full"]


# ─────────────────────────────────────────────────────────────
# メイン
# ─────────────────────────────────────────────────────────────

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
                "location":    None,
                "confDate":    None,
                "confDateEnd": None,
                "deadline":    None,
                "notification": None,
                "data_source": "error",
                "fetched_at":  datetime.now(timezone.utc).isoformat(),
            })

        time.sleep(3)  # レート制限対応（WikiCFP + API 両方に配慮）

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
