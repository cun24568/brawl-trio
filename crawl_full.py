"""
拡張クロール: クラブ + global TOP200 + JP TOP200
- 20タグごとに途中保存(中断OK)
- 各タグの結果を逐次表示
- 完了後に自動で集計してCSV出力
"""
import csv
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen, Request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API = "https://api.brawlstars.com/v1"
SCRIPT_DIR = Path(__file__).parent
ENV = SCRIPT_DIR / ".env"
OUT = SCRIPT_DIR / "data"
SEED = "#YQ8YY09R"
# 追加クラブ (シードプレイヤーのクラブに加えて取得)
EXTRA_CLUBS = [
    ("#2CGLLR98V", "祝杯をあげよう"),
    ("#2QG9UVUUY", "バトロワオンリー"),
]
COUNTRIES = ["global", "JP"]
DELAY = 0.15
TIMEOUT = 8
SAVE_EVERY = 20


def load_token():
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if line.startswith("BRAWL_API_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("token missing")


TOKEN = load_token()


def fetch(path):
    req = Request(
        f"{API}{path}",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/json",
            "User-Agent": "brawl-trio/0.1",
        },
    )
    with urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def collect_tags():
    tags = set()
    print(f"[Phase 1] タグ収集")

    # シードプレイヤーのクラブ
    try:
        player = fetch(f"/players/{quote(SEED, safe='')}")
        ctag = (player.get("club") or {}).get("tag")
        cname = (player.get("club") or {}).get("name", "?")
        if ctag:
            cdata = fetch(f"/clubs/{quote(ctag, safe='')}")
            for m in cdata.get("members", []):
                tags.add(m["tag"])
            print(f"  {cname}: +{len(cdata.get('members', []))} (total {len(tags)})")
    except (HTTPError, URLError) as e:
        print(f"  seed club FAIL: {e}")
    time.sleep(DELAY)

    # 追加クラブ
    for ctag, cname in EXTRA_CLUBS:
        try:
            cdata = fetch(f"/clubs/{quote(ctag, safe='')}")
            members = cdata.get("members", [])
            for m in members:
                tags.add(m["tag"])
            print(f"  {cname}: +{len(members)} (total {len(tags)})")
            time.sleep(DELAY)
        except (HTTPError, URLError) as e:
            print(f"  {cname} FAIL: {e}")

    # 各国
    for country in COUNTRIES:
        try:
            data = fetch(f"/rankings/{country}/players")
            items = data.get("items", [])
            for p in items:
                tags.add(p["tag"])
            print(f"  {country}: +{len(items)} (total {len(tags)})")
            time.sleep(DELAY)
        except (HTTPError, URLError) as e:
            print(f"  {country} FAIL: {e}")

    return sorted(tags)


def is_trio_battle(b):
    """event.mode と チーム構造の両方でトリオ判定"""
    ev = b.get("event", {})
    if ev.get("mode") == "trioShowdown":
        return True
    teams = b.get("battle", {}).get("teams", [])
    if len(teams) == 4 and all(len(t) == 3 for t in teams):
        return True
    return False


def fetch_battles(tags):
    battles = []
    fail = 0
    rate_limited = False
    for i, tag in enumerate(tags, 1):
        t0 = time.time()
        try:
            data = fetch(f"/players/{quote(tag, safe='')}/battlelog")
            n = 0
            for b in data.get("items", []):
                if not is_trio_battle(b):
                    continue
                b["_requester_tag"] = tag
                idx = None
                for ti, team in enumerate(b["battle"].get("teams", [])):
                    if any(p.get("tag") == tag for p in team):
                        idx = ti
                        break
                b["_requester_team_idx"] = idx
                battles.append(b)
                n += 1
            ms = (time.time() - t0) * 1000
            print(f"  {i:3d}/{len(tags)}  {tag:<12} trio:{n:2d}  ({ms:.0f}ms)  total:{len(battles)}")
        except HTTPError as e:
            fail += 1
            print(f"  {i:3d}/{len(tags)}  {tag:<12} HTTP {e.code}")
            if e.code == 429:
                print("\n⚠ Rate limited! 中断")
                rate_limited = True
                break
        except URLError as e:
            fail += 1
            print(f"  {i:3d}/{len(tags)}  {tag:<12} timeout: {e}")
        except Exception as e:
            fail += 1
            print(f"  {i:3d}/{len(tags)}  {tag:<12} ERROR: {e}")
        time.sleep(DELAY)

        if i % SAVE_EVERY == 0:
            with open(OUT / "trio_battles_partial.json", "w", encoding="utf-8") as f:
                json.dump(battles, f, ensure_ascii=False)

    return battles, fail, rate_limited


def aggregate(battles):
    agg = defaultdict(lambda: {"picks": 0, "wins": 0, "ranks": []})
    seen = set()
    for b in battles:
        key = (b.get("battleTime", ""), b.get("_requester_tag", ""))
        if key in seen:
            continue
        seen.add(key)
        ev = b.get("event", {})
        bt = b.get("battle", {})
        teams = bt.get("teams", [])
        ti = b.get("_requester_team_idx")
        if ti is None or ti >= len(teams):
            continue
        rank = bt.get("rank") or 5
        is_win = rank <= 2
        for p in teams[ti]:
            br = (p.get("brawler") or {}).get("name", "?")
            mkey = (ev.get("map", "?"), br)
            agg[mkey]["picks"] += 1
            if is_win:
                agg[mkey]["wins"] += 1
            agg[mkey]["ranks"].append(rank)
    return agg, len(seen)


def main():
    OUT.mkdir(exist_ok=True)
    t0 = time.time()

    tags = collect_tags()
    print(f"\nUnique tags: {len(tags)}\n推定時間: {len(tags) * 1.0 / 60:.1f}分\n")
    print("=" * 60)

    battles, fail, rate_limited = fetch_battles(tags)
    print("=" * 60)
    print(f"完了: {len(battles)} trio battles / 失敗 {fail} / rate_limited={rate_limited}")

    out_raw = OUT / "trio_battles_full.json"
    with open(out_raw, "w", encoding="utf-8") as f:
        json.dump(battles, f, ensure_ascii=False)
    print(f"Saved: {out_raw}")

    print("\n[Phase 3] 集計")
    agg, unique_n = aggregate(battles)
    print(f"unique battles: {unique_n} / cells: {len(agg)}\n")

    # CSV出力
    rows = []
    for (m, br), s in agg.items():
        picks = s["picks"]
        wins = s["wins"]
        wr = wins / picks if picks else 0
        avg_r = sum(s["ranks"]) / len(s["ranks"]) if s["ranks"] else 0
        rows.append(
            {
                "map": m,
                "brawler": br,
                "picks": picks,
                "wins": wins,
                "win_rate": round(wr, 3),
                "avg_rank": round(avg_r, 2),
            }
        )
    rows.sort(key=lambda x: (x["map"], -x["picks"]))
    with open(OUT / "trio_meta_full.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["map", "brawler", "picks", "wins", "win_rate", "avg_rank"],
        )
        w.writeheader()
        w.writerows(rows)
    print(f"Saved: {OUT / 'trio_meta_full.csv'}")

    # マップ別picks サマリ
    map_total = defaultdict(int)
    for r in rows:
        map_total[r["map"]] += r["picks"]
    print("\n--- マップ別picks (上位20) ---")
    for m, c in sorted(map_total.items(), key=lambda x: -x[1])[:20]:
        print(f"  {c:5d}  {m}")

    print(f"\n所要時間: {time.time() - t0:.1f}秒")


if __name__ == "__main__":
    main()
