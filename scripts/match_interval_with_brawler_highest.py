"""ブロウラー別マッチ間隔 + そのキャラのhighestTrophies/勝率/rank/power を併記.

仮説: brawler.highestTrophies が高いキャラほどマッチ遅い (= キャラ単位の隠しMMRピーク)
      新リリース (highestTrophies低) はマッチ速い (シリウス/ナジア仮説)
"""
import argparse
import json
import sqlite3
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def parse_bt(bt):
    try:
        return datetime.strptime(bt[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("--db", default=str(Path(__file__).parent.parent / "data" / "users.db"))
    ap.add_argument("--mode", default="trioShowdown")
    ap.add_argument("--max-interval", type=int, default=1800)
    args = ap.parse_args()

    tag = args.tag if args.tag.startswith("#") else "#" + args.tag
    tag = tag.upper()

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row

    # profile_json から brawler 別 highestTrophies / power / rank / trophies / hyperCharge を取得
    prof_row = con.execute("SELECT profile_json FROM watchlist WHERE tag=?", (tag,)).fetchone()
    brawler_meta = {}
    if prof_row and prof_row["profile_json"]:
        prof = json.loads(prof_row["profile_json"])
        for b in prof.get("brawlers", []):
            brawler_meta[b["name"]] = {
                "trophies": b.get("trophies", 0),
                "highestTrophies": b.get("highestTrophies", 0),
                "power": b.get("power", 0),
                "rank": b.get("rank", 0),
                "hasHC": 1 if (b.get("hyperCharges") or b.get("hyperCharge")) else 0,
                "prestigeLevel": b.get("prestigeLevel", 0),
            }

    rows = con.execute(
        "SELECT battle_time, brawler, rank, raw_json FROM battles "
        "WHERE tag = ? AND mode = ? ORDER BY battle_time",
        (tag, args.mode),
    ).fetchall()
    battles = []
    for r in rows:
        t = parse_bt(r["battle_time"])
        if t is None: continue
        try:
            raw = json.loads(r["raw_json"])
        except Exception:
            continue
        battles.append({
            "time": t,
            "duration": (raw.get("battle") or {}).get("duration", 0) or 0,
            "brawler": r["brawler"] or "",
            "rank": r["rank"] or 0,
        })

    by_br = defaultdict(list)
    picks = defaultdict(int)
    for i, b in enumerate(battles):
        picks[b["brawler"]] += 1
        if i == 0: continue
        gap = (b["time"] - battles[i-1]["time"]).total_seconds() - b["duration"]
        if 0 <= gap <= args.max_interval:
            by_br[b["brawler"]].append(gap)

    all_gaps = [g for gs in by_br.values() for g in gs]
    if not all_gaps:
        print("no data")
        return
    med_all = statistics.median(all_gaps)

    print(f"=== {tag} ===")
    print(f"全 battles: {len(battles)}, gap N={len(all_gaps)}, 中央値={med_all:.0f}s")
    print()
    print(f"{'brawler':<14} {'picks':<7} {'med_gap':<10} {'cur_tro':<8} {'highest':<8} {'power':<6} {'rank':<5} {'HC':<3}")

    rows_to_show = []
    for br, gaps in by_br.items():
        if picks[br] < 3 or len(gaps) < 2: continue
        m = brawler_meta.get(br, {})
        rows_to_show.append({
            "brawler": br,
            "picks": picks[br],
            "med_gap": statistics.median(gaps),
            "cur_tro": m.get("trophies", 0),
            "highest": m.get("highestTrophies", 0),
            "power": m.get("power", 0),
            "rank": m.get("rank", 0),
            "hasHC": m.get("hasHC", 0),
        })

    # picks降順
    rows_to_show.sort(key=lambda x: -x["picks"])
    for r in rows_to_show:
        diff = r["med_gap"] - med_all
        bar = "█" * int(r["med_gap"] / 30)
        hc = "✓" if r["hasHC"] else ""
        print(f"  {r['brawler']:<12} {r['picks']:>5}  {r['med_gap']:>5.0f}s ({diff:+.0f})  {r['cur_tro']:>6}  {r['highest']:>6}  P{r['power']:<3} R{r['rank']:<3}  {hc}")

    # 相関: highestTrophies vs median gap
    if len(rows_to_show) >= 5:
        n = len(rows_to_show)
        xs = [r["highest"] for r in rows_to_show]
        ys = [r["med_gap"] for r in rows_to_show]
        # Spearman
        rx = sorted(range(n), key=lambda i: xs[i])
        ry = sorted(range(n), key=lambda i: ys[i])
        rank_x = [0]*n; rank_y = [0]*n
        for i, idx in enumerate(rx): rank_x[idx] = i
        for i, idx in enumerate(ry): rank_y[idx] = i
        mx = sum(rank_x)/n; my = sum(rank_y)/n
        cov = sum((rank_x[i]-mx)*(rank_y[i]-my) for i in range(n))
        vx = (sum((rank_x[i]-mx)**2 for i in range(n)))**0.5
        vy = (sum((rank_y[i]-my)**2 for i in range(n)))**0.5
        rho = cov/(vx*vy) if vx and vy else 0
        print(f"\nSpearman相関: highestTrophies vs median_gap = {rho:+.3f}  (N={n})")
        if rho > 0.5:
            print("  → 強い正相関: そのキャラの最高到達トロが高いほどマッチ遅い")
        elif rho > 0.2:
            print("  → 中程度の正相関: highestTrophies が要因の一つ")


if __name__ == "__main__":
    main()
