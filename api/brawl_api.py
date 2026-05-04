"""Brawl Stars 公式API ラッパ (api/ 内で使い回す薄いクライアント)。
.env から BRAWL_API_TOKEN を読み込む。
"""
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

API = "https://api.brawlstars.com/v1"
ENV = Path(__file__).parent.parent / ".env"
TIMEOUT = 15
RETRIES = 3


def _load_token() -> str:
    if "BRAWL_API_TOKEN" in os.environ:
        return os.environ["BRAWL_API_TOKEN"]
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            if line.startswith("BRAWL_API_TOKEN="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("BRAWL_API_TOKEN not found in .env or environment")


_TOKEN = None


def token() -> str:
    global _TOKEN
    if _TOKEN is None:
        _TOKEN = _load_token()
    return _TOKEN


def fetch(path: str) -> dict:
    last_err = None
    for attempt in range(RETRIES):
        req = Request(
            f"{API}{path}",
            headers={
                "Authorization": f"Bearer {token()}",
                "Accept": "application/json",
                "User-Agent": "brawl-trio-api/1.0",
            },
        )
        try:
            with urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8"))
        except HTTPError:
            raise
        except (TimeoutError, URLError, OSError) as e:
            last_err = e
            if attempt < RETRIES - 1:
                time.sleep(1 + attempt)
                continue
            raise


def get_player(tag: str) -> dict:
    return fetch(f"/players/{quote(tag, safe='')}")


def get_battlelog(tag: str) -> list[dict]:
    data = fetch(f"/players/{quote(tag, safe='')}/battlelog")
    return data.get("items", [])


def is_trio_battle(b: dict) -> bool:
    """トリオサバイバル限定判定。event.mode と teams 構造の両方で確認
    (公式APIは duo/trio で mode=duoShowdown を返すバグあり)。"""
    ev = b.get("event") or {}
    if ev.get("mode") == "trioShowdown":
        return True
    teams = (b.get("battle") or {}).get("teams") or []
    if len(teams) == 4 and all(len(t) == 3 for t in teams):
        return True
    return False
