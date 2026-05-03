"""指定プレイヤーの所属クラブタグを取得"""
import json
import sys
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen, Request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API = "https://api.brawlstars.com/v1"
ENV = Path(__file__).parent / ".env"


def load_token():
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if line.startswith("BRAWL_API_TOKEN="):
            return line.split("=", 1)[1].strip()


TOKEN = load_token()


def fetch(path):
    req = Request(
        f"{API}{path}",
        headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"},
    )
    with urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def main(tags):
    for t in tags:
        try:
            p = fetch(f"/players/{quote(t, safe='')}")
            club = p.get("club") or {}
            print(f"{t} → {p.get('name')} / Club: {club.get('name')} ({club.get('tag', 'no club')})")
        except Exception as e:
            print(f"{t} → ERROR: {e}")


if __name__ == "__main__":
    main(["#8YCVLLQL0", "#PLQU2UJGC"])
