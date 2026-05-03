"""指定キーワードで全マップを横断検索する。"""
import json
import sys
from urllib.request import urlopen, Request

API = "https://api.brawlapi.com/v1"


def fetch_json(path):
    req = Request(f"{API}{path}", headers={"User-Agent": "brawl-trio-fetcher/1.0"})
    with urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main(keyword: str):
    keyword = keyword.lower()
    maps_raw = fetch_json("/maps")
    hits = [
        m
        for m in maps_raw["list"]
        if keyword in (m.get("name") or "").lower()
        or keyword in (m.get("hash") or "").lower()
    ]
    if not hits:
        print(f"No maps matched '{keyword}' across all game modes.")
        print(f"Total maps in API: {len(maps_raw['list'])}")
        return
    print(f"Found {len(hits)} match(es):")
    for m in hits:
        gm = m.get("gameMode") or {}
        env = m.get("environment") or {}
        print(
            f"  id={m['id']}  name={m['name']}  hash={m.get('hash')}  "
            f"gameMode={gm.get('name')}  env={env.get('name')}  "
            f"disabled={m.get('disabled')}"
        )
        print(f"    image: {m.get('imageUrl')}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "molten")
