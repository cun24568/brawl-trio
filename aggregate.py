"""
集めた trio バトルから map × brawler の picks/wins を集計し、
マップ別ティアリスト案を生成する。
"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).parent
OUT = SCRIPT_DIR / "data"
INPUT = OUT / "trio_battles_club.json"
MIN_PICKS_FOR_TIER = 3  # ティア掲載に必要な最小pick数


def main():
    battles = json.loads(INPUT.read_text(encoding="utf-8"))
    print(f"読み込み: {len(battles)} battles\n")

    # 集計: requesterのチームに pick + (rank<=2 なら win)
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
        rank = bt.get("rank") or 5
        is_win = rank <= 2

        for p in teams[ti]:
            brawler = (p.get("brawler") or {}).get("name", "Unknown")
            mkey = (map_name, brawler)
            agg[mkey]["picks"] += 1
            if is_win:
                agg[mkey]["wins"] += 1
            agg[mkey]["ranks"].append(rank)

    print(f"unique battles: {len(seen)}")
    print(f"map x brawler cells: {len(agg)}\n")

    # CSV出力
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
    rows.sort(key=lambda x: (x["map"], -x["picks"]))

    csv_path = OUT / "trio_meta.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["map", "brawler", "picks", "wins", "win_rate", "avg_rank"],
        )
        w.writeheader()
        w.writerows(rows)
    print(f"CSV保存: {csv_path}\n")

    # マップ別ティア風表示
    by_map = defaultdict(list)
    for r in rows:
        by_map[r["map"]].append(r)

    for m in sorted(by_map.keys(), key=lambda x: -sum(r["picks"] for r in by_map[x])):
        total = sum(r["picks"] for r in by_map[m])
        print(f"\n=== {m} (total {total} picks) ===")
        # pick数フィルタ
        rs = [r for r in by_map[m] if r["picks"] >= MIN_PICKS_FOR_TIER]
        # win_rate でソート(picks 同値以上)
        rs.sort(key=lambda x: (-x["win_rate"], -x["picks"]))
        print(f"  {'brawler':<15} {'picks':>5} {'wins':>4} {'WR':>6} {'avgRank':>7}")
        for r in rs[:15]:
            print(
                f"  {r['brawler']:<15} {r['picks']:>5} {r['wins']:>4} "
                f"{r['win_rate']:>6.1%} {r['avg_rank']:>7.2f}"
            )


if __name__ == "__main__":
    main()
