"""
公式API でトリオサバイバル戦を集めて集計する。
シードプレイヤーのクラブメンバー + 各国ランキング上位 から battlelog を取得。
"""
import csv
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import urlopen, Request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API = "https://api.brawlstars.com/v1"
SCRIPT_DIR = Path(__file__).parent
ENV = SCRIPT_DIR / ".env"
OUT = SCRIPT_DIR / "data"
DELAY = 0.2  # 秒/req

# あなたのタグ
SEED_TAG = "#YQ8YY09R"
COUNTRIES = ["global", "JP", "KR", "US"]


def load_token() -> str:
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if line.startswith("BRAWL_API_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError(".env の BRAWL_API_TOKEN が空")


TOKEN = load_token()


def fetch(path: str, retries: int = 2):
    req = Request(
        f"{API}{path}",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/json",
            "User-Agent": "brawl-trio/0.1",
        },
    )
    try:
        with urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except HTTPError as e:
        if e.code == 429 and retries > 0:
            print("  rate limit, sleeping 20s...")
            time.sleep(20)
            return fetch(path, retries - 1)
        raise


def collect_tags() -> set:
    tags: set = set()

    # シードプレイヤーのクラブメンバー
    print(f"[Phase 1a] シード {SEED_TAG} のクラブ取得")
    try:
        player = fetch(f"/players/{quote(SEED_TAG, safe='')}")
        club = player.get("club") or {}
        ctag = club.get("tag")
        if ctag:
            print(f"  club: {club.get('name')} ({ctag})")
            time.sleep(DELAY)
            cdata = fetch(f"/clubs/{quote(ctag, safe='')}")
            for m in cdata.get("members", []):
                tags.add(m["tag"])
            print(f"  +{len(cdata.get('members', []))} members (total {len(tags)})")
        else:
            print("  no club")
    except HTTPError as e:
        print(f"  club fetch failed: HTTP {e.code}")
    time.sleep(DELAY)

    # 各国ランキング
    print(f"\n[Phase 1b] 各国TOP200")
    for country in COUNTRIES:
        try:
            data = fetch(f"/rankings/{country}/players")
            items = data.get("items", [])
            for p in items:
                tags.add(p["tag"])
            print(f"  {country}: +{len(items)} (total {len(tags)})")
            time.sleep(DELAY)
        except HTTPError as e:
            print(f"  {country}: HTTP {e.code}")

    return tags


def fetch_trio_battles(tags: set) -> list:
    """各タグの battlelog から trioShowdown 戦のみ抽出。リクエスタータグも記録。"""
    all_battles = []
    n = len(tags)
    for i, tag in enumerate(tags, 1):
        try:
            data = fetch(f"/players/{quote(tag, safe='')}/battlelog")
            for b in data.get("items", []):
                bt = b.get("battle", {})
                if bt.get("mode") != "trioShowdown":
                    continue
                # リクエスター情報を記録
                b["_requester_tag"] = tag
                req_team_idx = None
                for ti, team in enumerate(bt.get("teams", [])):
                    if any(p.get("tag") == tag for p in team):
                        req_team_idx = ti
                        break
                b["_requester_team_idx"] = req_team_idx
                all_battles.append(b)
            time.sleep(DELAY)
        except HTTPError:
            pass  # 個別失敗はスキップ
        if i % 25 == 0:
            print(f"  {i}/{n} processed | {len(all_battles)} trio battles")
    return all_battles


def aggregate(battles: list):
    """リクエスターのチーム3人に pick + (rank<=2なら win) クレジット。"""
    agg = defaultdict(lambda: {"picks": 0, "wins": 0, "ranks": []})
    seen = set()
    for b in battles:
        key = (b.get("battleTime", ""), b.get("_requester_tag", ""))
        if key in seen:
            continue
        seen.add(key)

        ev = b.get("event", {})
        map_name = ev.get("map", "Unknown")
        bt = b.get("battle", {})
        teams = bt.get("teams", [])
        ti = b.get("_requester_team_idx")
        if ti is None or ti >= len(teams):
            continue
        rank = bt.get("rank", 5) or 5
        is_win = rank <= 2

        for p in teams[ti]:
            brawler = (p.get("brawler") or {}).get("name", "Unknown")
            mkey = (map_name, brawler)
            agg[mkey]["picks"] += 1
            if is_win:
                agg[mkey]["wins"] += 1
            agg[mkey]["ranks"].append(rank)
    return agg, len(seen)


def main():
    OUT.mkdir(exist_ok=True)
    t0 = time.time()

    print("=" * 60)
    print("Phase 1: プレイヤータグ収集")
    print("=" * 60)
    tags = collect_tags()
    print(f"\nUnique tags: {len(tags)}")

    print("\n" + "=" * 60)
    print(f"Phase 2: バトルログ取得 ({len(tags)} players)")
    print("=" * 60)
    battles = fetch_trio_battles(tags)
    print(f"\nTotal trio battles fetched: {len(battles)}")

    with open(OUT / "trio_battles_raw.json", "w", encoding="utf-8") as f:
        json.dump(battles, f, ensure_ascii=False)
    print(f"Saved raw: {OUT / 'trio_battles_raw.json'}")

    print("\n" + "=" * 60)
    print("Phase 3: 集計")
    print("=" * 60)
    agg, unique_n = aggregate(battles)
    print(f"Unique battles after dedup: {unique_n}")
    print(f"(map x brawler) cells: {len(agg)}")

    # CSV
    rows = []
    for (m, br), s in agg.items():
        picks = s["picks"]
        wins = s["wins"]
        wr = wins / picks if picks else 0
        avg_rank = sum(s["ranks"]) / len(s["ranks"]) if s["ranks"] else 0
        rows.append(
            {
                "map": m,
                "brawler": br,
                "picks": picks,
                "wins": wins,
                "win_rate": round(wr, 3),
                "avg_rank": round(avg_rank, 2),
            }
        )
    rows.sort(key=lambda x: (-x["picks"],))
    with open(OUT / "trio_meta.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["map", "brawler", "picks", "wins", "win_rate", "avg_rank"],
        )
        w.writeheader()
        w.writerows(rows)
    print(f"Saved CSV: {OUT / 'trio_meta.csv'}")

    # サマリ
    map_total = defaultdict(int)
    brawler_total = defaultdict(int)
    for (m, br), s in agg.items():
        map_total[m] += s["picks"]
        brawler_total[br] += s["picks"]

    print("\n--- マップ別合計picks (上位15) ---")
    for m, c in sorted(map_total.items(), key=lambda x: -x[1])[:15]:
        print(f"  {c:5d}  {m}")

    print("\n--- ブロウラー別合計picks (上位20) ---")
    for br, c in sorted(brawler_total.items(), key=lambda x: -x[1])[:20]:
        print(f"  {c:5d}  {br}")

    print(f"\n所要時間: {time.time() - t0:.1f}秒")


if __name__ == "__main__":
    main()
