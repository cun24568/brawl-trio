"""
クラブメンバー全員のbattlelogから出現するmode名を集計。
trioShowdown が本当に正しい名前かどうか確認。
"""
import json
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen, Request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API = "https://api.brawlstars.com/v1"
ENV = Path(__file__).parent / ".env"
SEED = "#YQ8YY09R"


def load_token() -> str:
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


def main():
    print(f"クラブから全タグ収集...")
    player = fetch(f"/players/{quote(SEED, safe='')}")
    ctag = (player.get("club") or {}).get("tag")
    cdata = fetch(f"/clubs/{quote(ctag, safe='')}")
    tags = [m["tag"] for m in cdata.get("members", [])]
    print(f"{len(tags)} members\n")

    mode_counter = Counter()
    type_counter = Counter()
    map_counter = Counter()
    sample_battles = {}  # mode -> 1 sample battle (for inspection)

    for i, tag in enumerate(tags, 1):
        try:
            data = fetch(f"/players/{quote(tag, safe='')}/battlelog")
            for b in data.get("items", []):
                bt = b.get("battle", {})
                ev = b.get("event", {})
                mode = bt.get("mode") or ev.get("mode") or "?"
                btype = bt.get("type") or "?"
                map_name = ev.get("map") or "?"
                mode_counter[mode] += 1
                type_counter[btype] += 1
                map_counter[map_name] += 1
                # 各modeの最初の1サンプルを保存
                if mode not in sample_battles:
                    sample_battles[mode] = b
            print(f"  {i}/{len(tags)}  {tag}", end="\r")
            time.sleep(0.15)
        except Exception as e:
            print(f"  {i}/{len(tags)}  {tag}  ERROR: {e}")

    print("\n\n=== mode 分布 ===")
    for m, c in mode_counter.most_common():
        print(f"  {c:4d}  {m}")

    print("\n=== type 分布 ===")
    for t, c in type_counter.most_common():
        print(f"  {c:4d}  {t}")

    print("\n=== map 分布 (上位20) ===")
    for m, c in map_counter.most_common(20):
        print(f"  {c:4d}  {m}")

    # showdown 系の各サンプル詳細
    print("\n=== showdown系サンプル ===")
    for mode in mode_counter:
        if "howdown" in mode.lower() or "urvival" in mode.lower():
            b = sample_battles[mode]
            ev = b.get("event", {})
            bt = b.get("battle", {})
            print(f"\n  mode={mode}")
            print(f"    event.mode = {ev.get('mode')}")
            print(f"    event.map  = {ev.get('map')}")
            print(f"    type       = {bt.get('type')}")
            print(f"    rank/result= {bt.get('rank') or bt.get('result')}")
            print(f"    teams      = {len(bt.get('teams', []))} teams of {len(bt.get('teams', [[]])[0])} players each")


if __name__ == "__main__":
    main()
