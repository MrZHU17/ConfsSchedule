"""
Conference Tracker Scraper  v10
================================
変更点（v9 → v10）:
  - WikiCFP スクレイピングを完全削除（ネットワーク制限のため接続不可）
  - Claude API + web_search のみを使用
  - anthropic-beta ヘッダーを追加（web_search 必須）
  - tool_use 複数ターンループを実装
  - _apply_info を共通化し DRY に
"""

import json
import os
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
    for sep in ("→", "⇒", "->"):
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


# ─────────────────────────────────────────────
# API ヘッダー（anthropic-beta が必須）
# ─────────────────────────────────────────────

def _api_headers() -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY が設定されていません。\n"
            "  ローカル実行: export ANTHROPIC_API_KEY=sk-ant-...\n"
            "  GitHub Actions: Settings > Secrets > Actions に登録"
        )
    return {
        "x-api-key":         api_key,
        "anthropic-version": "2023-06-01",
        "anthropic-beta":    "web-search-2025-03-05",  # web_search ツールに必須
        "content-type":      "application/json",
    }


# ─────────────────────────────────────────────
# Claude API + web_search（tool_use 複数ターン対応）
# ─────────────────────────────────────────────

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


def fetch_conference_info(abbr: str, search_query: str) -> dict:
    """
    Claude API + web_search で会議情報を取得。
    stop_reason == "tool_use" のループを正しく処理する。
    """
    messages = [
        {
            "role": "user",
            "content": (
                f"Find the latest paper submission deadline for: {abbr}\n"
                f"Search query: {search_query}\n"
                f"Return ONLY the JSON object."
            ),
        }
    ]

    max_turns = 8  # 無限ループ防止
    for turn in range(max_turns):
        payload = {
            "model":      MODEL,
            "max_tokens": 1024,
            "system":     SYSTEM_PROMPT,
            "tools": [
                {
                    "type":     "web_search_20250305",
                    "name":     "web_search",
                    "max_uses": 3,  # コスト抑制
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
            log.error("  API HTTP エラー [%s]: %s", r.status_code, r.text[:300])
            return {}
        except Exception as e:
            log.error("  API 呼び出し失敗: %s", e)
            return {}

        data        = r.json()
        stop_reason = data.get("stop_reason")
        content     = data.get("content", [])

        log.debug("  ターン %d: stop_reason=%s, blocks=%d", turn + 1, stop_reason, len(content))

        # アシスタント応答を履歴に追加
        messages.append({"role": "assistant", "content": content})

        if stop_reason == "end_turn":
            # テキストを結合して JSON を抽出
            text = "".join(
                b.get("text", "") for b in content if b.get("type") == "text"
            )
            result = _extract_json(text)
            if result:
                log.info(
                    "  API 結果: deadline=%s, conf=%s〜%s, location=%s, confidence=%s",
                    result.get("deadline"), result.get("confDate"),
                    result.get("confDateEnd"), result.get("location"),
                    result.get("confidence"),
                )
            else:
                log.warning("  JSON 抽出失敗。レスポンス: %s", text[:300])
            return result

        elif stop_reason == "tool_use":
            # tool_use ブロックごとに tool_result を作成
            tool_results = []
            for block in content:
                if block.get("type") == "tool_use":
                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": block["id"],
                        "content":     "",  # web_search は Anthropic サーバーが処理
                    })

            if not tool_results:
                log.warning("  tool_use ブロックが空。ループ終了。")
                break

            messages.append({"role": "user", "content": tool_results})
            log.debug("  → tool_result %d 件を返して継続", len(tool_results))

        elif stop_reason == "max_tokens":
            log.warning("  max_tokens に達しました。")
            break
        else:
            log.warning("  予期しない stop_reason: %s", stop_reason)
            break

    return {}


# ─────────────────────────────────────────────
# ユーティリティ
# ─────────────────────────────────────────────

def _apply_info(entry: dict, info: dict) -> None:
    """info の値を entry に適用（None/空文字列はスキップ）。"""
    for field in ("deadline", "notification", "confDate", "confDateEnd"):
        raw = info.get(field)
        if raw:
            entry[field] = parse_date(str(raw)) or raw
    if info.get("location"):
        entry["location"] = info["location"]
    if info.get("url"):
        entry["url"] = info["url"]


# ─────────────────────────────────────────────
# 1件の会議を処理
# ─────────────────────────────────────────────

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

    # ── Step 1: Claude API + web_search ──────────────────────
    info = fetch_conference_info(abbr, target["search_query"])
    if info:
        _apply_info(entry, info)
        entry["data_source"] = "api_search"

    # ── Step 2: 既存データで欠損フィールドを補完 ──────────────
    old = existing.get(abbr, {})
    for field in ("deadline", "notification", "confDate", "confDateEnd",
                  "location", "url", "full"):
        if not entry.get(field) and old.get(field) and old[field] != "TBD":
            entry[field] = old[field]
            log.info("  補完 [%s] ← 既存: %s", field, old[field])

    return entry


# ─────────────────────────────────────────────
# メイン
# ─────────────────────────────────────────────

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
                "abbr":         target["abbr"],
                "full":         target["full"],
                "url":          target["base_url"],
                "area":         target["area"],
                "location":     None,
                "confDate":     None,
                "confDateEnd":  None,
                "deadline":     None,
                "notification": None,
                "data_source":  "error",
                "fetched_at":   datetime.now(timezone.utc).isoformat(),
            })

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
