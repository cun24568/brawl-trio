"""
公式 Brawl Stars API から全ブロウラー(id, name)を取得して
data/official_brawlers.json に保存。
Brawlify未収録キャラの画像URL構築 (CDN) に使う。
"""
import json
import os
import sys
from pathlib import Path
from urllib.request import urlopen, Request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).parent
ENV_FILE = ROOT / ".env"
OUT = ROOT / "data" / "official_brawlers.json"


def load_env():
    if not ENV_FILE.exists():
        sys.exit("missing .env")
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def main():
    load_env()
    token = os.environ["BRAWL_API_TOKEN"]
    req = Request(
        "https://api.brawlstars.com/v1/brawlers",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
    )
    data = json.loads(urlopen(req, timeout=15).read())
    items = [
        {"id": x["id"], "name": x["name"]} for x in data.get("items", [])
    ]
    items.sort(key=lambda x: x["id"])
    OUT.write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Saved {len(items)} brawlers to {OUT}")


if __name__ == "__main__":
    main()
