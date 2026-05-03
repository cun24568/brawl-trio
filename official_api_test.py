"""
Brawl Stars 公式API 疎通テスト。
.env から BRAWL_API_TOKEN を読み、プレイヤータグでプレイヤー情報と直近バトルを取得。

使い方: py official_api_test.py "#YOUR_TAG"
"""
import json
import sys
import os
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen, Request
from urllib.error import HTTPError

# Windows コンソールのcp932対策。絵文字も出せるようUTF-8で
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

API = "https://api.brawlstars.com/v1"
SCRIPT_DIR = Path(__file__).parent
ENV_FILE = SCRIPT_DIR / ".env"


def load_env():
    """最小限の .env パーサ(KEY=VALUE 形式のみ)"""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def fetch(path: str, token: str):
    req = Request(
        f"{API}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "brawl-trio/0.1",
        },
    )
    try:
        with urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code} on {path}\n{body}", file=sys.stderr)
        sys.exit(1)


def main(raw_tag: str):
    load_env()
    token = os.environ.get("BRAWL_API_TOKEN", "").strip()
    if not token:
        print("ERROR: .env に BRAWL_API_TOKEN を設定してください", file=sys.stderr)
        sys.exit(1)

    # # を %23 にURLエンコード
    tag = raw_tag.lstrip("#").strip().upper()
    encoded = quote(f"#{tag}", safe="")

    print(f"--- /players/{encoded} ---")
    player = fetch(f"/players/{encoded}", token)
    print(f"Name        : {player.get('name')}")
    print(f"Trophies    : {player.get('trophies')}")
    print(f"Highest     : {player.get('highestTrophies')}")
    print(f"Club        : {(player.get('club') or {}).get('name', '(no club)')}")
    print(f"Brawlers    : {len(player.get('brawlers', []))}")
    print(f"Solo wins   : {player.get('soloVictories')}")
    print(f"Duo wins    : {player.get('duoVictories')}")
    print(f"3v3 wins    : {player.get('3vs3Victories')}")

    print(f"\n--- /players/{encoded}/battlelog (latest 1) ---")
    log = fetch(f"/players/{encoded}/battlelog", token)
    items = log.get("items", [])
    print(f"Total battles in log: {len(items)}")
    if items:
        b = items[0]
        ev = b.get("event", {})
        bt = b.get("battle", {})
        result = bt.get("result")
        if not result:
            result = f"rank={bt.get('rank')}"
        print(f"  time   : {b.get('battleTime')}")
        print(f"  mode   : {bt.get('mode') or ev.get('mode')}")
        print(f"  map    : {ev.get('map')}")
        print(f"  result : {result}")
        print(f"  type   : {bt.get('type')}")

    print("\nOK: 公式API疎通成功")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: py official_api_test.py "#YOUR_TAG"', file=sys.stderr)
        sys.exit(2)
    main(sys.argv[1])
