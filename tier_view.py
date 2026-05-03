"""
trio_meta_full.csv からマップ別ティア表示。
信頼度 = picks 数で判定し、十分なサンプルがあるマップだけ詳細表示。
"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CSV = Path(__file__).parent / "data" / "trio_meta_full.csv"
MIN_PICKS_PER_BRAWLER = 5  # ブロウラー単位の最小サンプル
MIN_PICKS_PER_MAP = 50  # マップ単位の最小サンプル(これ未満は信頼度低)


def main():
    rows = list(csv.DictReader(CSV.open(encoding="utf-8-sig")))
    by_map = defaultdict(list)
    for r in rows:
        r["picks"] = int(r["picks"])
        r["wins"] = int(r["wins"])
        r["win_rate"] = float(r["win_rate"])
        r["avg_rank"] = float(r["avg_rank"])
        by_map[r["map"]].append(r)

    map_totals = [(m, sum(r["picks"] for r in rs)) for m, rs in by_map.items()]
    map_totals.sort(key=lambda x: -x[1])

    print("=" * 70)
    print(" 信頼度高(50pick以上のマップ) = ティアリスト掲載候補 ")
    print("=" * 70)

    for m, total in map_totals:
        if total < MIN_PICKS_PER_MAP:
            continue
        print(f"\n■ {m}  (total {total} picks)")
        # ブロウラーフィルタ + 勝率ソート + 同率ならpicksで
        rs = [r for r in by_map[m] if r["picks"] >= MIN_PICKS_PER_BRAWLER]
        rs.sort(key=lambda x: (-x["win_rate"], -x["picks"]))
        print(f"  {'rank':>4} {'brawler':<15} {'picks':>5} {'wins':>4} {'WR':>6} {'avgRk':>6}")
        for i, r in enumerate(rs[:15], 1):
            tier = "S+" if r["win_rate"] >= 0.85 else "S" if r["win_rate"] >= 0.75 else "A" if r["win_rate"] >= 0.65 else "B"
            print(
                f"  [{tier:>2}] {r['brawler']:<15} {r['picks']:>5} {r['wins']:>4} "
                f"{r['win_rate']:>6.1%} {r['avg_rank']:>6.2f}"
            )

    print("\n" + "=" * 70)
    print(" 信頼度低(50pick未満)= 追加データ収集が必要 ")
    print("=" * 70)
    for m, total in map_totals:
        if total >= MIN_PICKS_PER_MAP:
            continue
        print(f"  {total:3d}  {m}")


if __name__ == "__main__":
    main()
