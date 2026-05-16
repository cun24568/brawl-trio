"""特定プレイヤーのブロウラー別マッチ間隔分析.

仮説: トロフィー制度刷新前に使っていたキャラ (= 高使用回数) は
      マッチング時のMMR/Eloが内部的に残っていてマッチが遅くなる.

使い方:
  python scripts/match_interval_by_brawler.py "#YQ8YY09R"
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


def normalize_tag(tag):
    t = (tag or "").strip().upper()
    if not t.startswith("#"):
        t = "#" + t
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("--db", default=str(Path(__file__).parent.parent / "data" / "users.db"))
    ap.add_argument("--mode", default="trioShowdown")
    ap.add_argument("--max-interval", type=int, default=1800)
    ap.add_argument("--min-picks", type=int, default=3, help="このpicks未満のキャラは表示しない")
    args = ap.parse_args()

    tag = normalize_tag(args.tag)
    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT battle_time, brawler, rank, raw_json FROM battles "
        "WHERE tag = ? AND mode = ? ORDER BY battle_time",
        (tag, args.mode),
    ).fetchall()
    if not rows:
        print(f"no battles for {tag} mode={args.mode}")
        return

    battles = []
    for r in rows:
        t = parse_bt(r["battle_time"])
        if t is None: continue
        try:
            raw = json.loads(r["raw_json"])
        except Exception:
            continue
        battle = raw.get("battle") or {}
        battles.append({
            "time": t,
            "duration": battle.get("duration", 0) or 0,
            "brawler": r["brawler"] or "",
            "rank": r["rank"] or 0,
        })

    # マッチ間隔を計算 (= 前試合終了からの差 - 自身のduration)
    by_brawler = defaultdict(list)  # current使用キャラごとの gap
    by_brawler_picks = defaultdict(int)
    for i, b in enumerate(battles):
        by_brawler_picks[b["brawler"]] += 1
        if i == 0: continue
        prev = battles[i-1]
        gap = (b["time"] - prev["time"]).total_seconds() - b["duration"]
        if gap < 0 or gap > args.max_interval: continue
        by_brawler[b["brawler"]].append(gap)

    print(f"=== {tag} ブロウラー別マッチ間隔 (mode={args.mode}) ===")
    print(f"{'brawler':<20} {'picks':<7} {'gap_n':<6} {'median':<8} {'mean':<8} {'avg_rank':<9}")
    # picks降順 = 使用回数多い順
    rows_to_show = []
    for br, gaps in by_brawler.items():
        if by_brawler_picks[br] < args.min_picks: continue
        if len(gaps) < 2: continue
        ranks_for_br = [b["rank"] for b in battles if b["brawler"] == br and b["rank"] > 0]
        avg_rank = statistics.mean(ranks_for_br) if ranks_for_br else 0
        rows_to_show.append({
            "brawler": br,
            "picks": by_brawler_picks[br],
            "gap_n": len(gaps),
            "median": statistics.median(gaps),
            "mean": statistics.mean(gaps),
            "avg_rank": avg_rank,
        })
    rows_to_show.sort(key=lambda x: -x["picks"])
    for r in rows_to_show:
        bar = "█" * int(r["median"] / 30)
        print(f"  {r['brawler']:<18} {r['picks']:>5}  {r['gap_n']:>5}  {r['median']:>5.0f}s   {r['mean']:>5.0f}s   {r['avg_rank']:>5.2f}  {bar}")

    # 全体平均との比較
    all_gaps = [g for gs in by_brawler.values() for g in gs]
    if all_gaps:
        med_all = statistics.median(all_gaps)
        print(f"\n全体: N={len(all_gaps)}, 中央値={med_all:.0f}s, 平均={statistics.mean(all_gaps):.0f}s")
        print(f"\n=== 全体中央値より遅いブロウラー (上位5) ===")
        rows_to_show.sort(key=lambda x: -x["median"])
        for r in rows_to_show[:5]:
            d = r["median"] - med_all
            print(f"  {r['brawler']:<18} {r['median']:>5.0f}s ({d:+.0f}s vs 全体) picks={r['picks']}")


if __name__ == "__main__":
    main()
