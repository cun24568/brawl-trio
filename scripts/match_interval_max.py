"""マッチ間隔を 自分のチームの 最高/最低/平均トロフィー それぞれで帯分け比較。

仮説: チーム内 max trophies が高いとマッチング遅い (= マッチング側が最強プレイヤーに合わせて
       同帯探しに行く可能性)。
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


def extract_my_team_stats(raw, my_tag):
    battle = (raw.get("battle") or {})
    teams = battle.get("teams") or []
    for team in teams:
        if any(p.get("tag") == my_tag for p in team):
            tros = [(pp.get("brawler") or {}).get("trophies", 0) or 0 for pp in team]
            if not tros:
                return None
            return {
                "avg": statistics.mean(tros),
                "max": max(tros),
                "min": min(tros),
                "self": next(((pp.get("brawler") or {}).get("trophies", 0) for pp in team if pp.get("tag") == my_tag), 0),
                "team_size": len(team),
            }
    players = battle.get("players") or []
    for p in players:
        if p.get("tag") == my_tag:
            tro = (p.get("brawler") or {}).get("trophies", 0) or 0
            return {"avg": tro, "max": tro, "min": tro, "self": tro, "team_size": 1}
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(Path(__file__).parent.parent / "data" / "users.db"))
    ap.add_argument("--mode", default="trioShowdown")
    ap.add_argument("--max-interval", type=int, default=1800)
    ap.add_argument("--band", type=int, default=200)
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT tag, battle_time, raw_json FROM battles WHERE mode = ? ORDER BY tag, battle_time",
        (args.mode,),
    ).fetchall()

    by_tag = defaultdict(list)
    for r in rows:
        t = parse_bt(r["battle_time"])
        if t is None: continue
        try:
            raw = json.loads(r["raw_json"])
        except Exception:
            continue
        battle = raw.get("battle") or {}
        s = extract_my_team_stats(raw, r["tag"])
        if s is None: continue
        s["time"] = t
        s["duration"] = battle.get("duration", 0) or 0
        by_tag[r["tag"]].append(s)

    pairs = []
    for tag, battles in by_tag.items():
        battles.sort(key=lambda x: x["time"])
        for i in range(1, len(battles)):
            prev = battles[i-1]; curr = battles[i]
            gap = (curr["time"] - prev["time"]).total_seconds() - curr["duration"]
            if gap < 0 or gap > args.max_interval: continue
            pairs.append({"gap": gap, **curr})

    print(f"mode: {args.mode}, valid pairs: {len(pairs)}")
    print(f"band size: {args.band} trophies\n")

    def show_by(key, label):
        by_band = defaultdict(list)
        for p in pairs:
            b = int(p[key] // args.band) * args.band
            by_band[b].append(p["gap"])
        print(f"=== チーム {label} 別 ===")
        for b in sorted(by_band.keys()):
            arr = by_band[b]
            if len(arr) < 5:
                if arr: print(f"  {b:>5}-{b+args.band-1:<5}: N={len(arr)} (不足)")
                continue
            med = statistics.median(arr)
            bar = "█" * int(med / 40)
            print(f"  {b:>5}-{b+args.band-1:<5}: N={len(arr):>5} med={med:>5.0f}s mean={statistics.mean(arr):>5.0f}s  {bar}")
        print()

    show_by("avg", "平均トロフィー")
    show_by("max", "最高トロフィー")
    show_by("min", "最低トロフィー")
    show_by("self", "自分自身のbrawlerトロ")

    # 「平均が低いのにmaxが高い」 ケースを抽出: avg < 1500 かつ max >= 2500 等
    print(f"=== 平均は低めだが max が高い (avg<1500 & max>=2500) ===")
    edge = [p for p in pairs if p["avg"] < 1500 and p["max"] >= 2500]
    if len(edge) >= 5:
        gaps = [p["gap"] for p in edge]
        print(f"  N={len(gaps)} med={statistics.median(gaps):.0f}s mean={statistics.mean(gaps):.0f}s")
        # 同じavg帯の通常 (max<2500) と比較
        same_avg = [p for p in pairs if p["avg"] < 1500 and p["max"] < 2500]
        if len(same_avg) >= 5:
            g2 = [p["gap"] for p in same_avg]
            print(f"  比較: 同avg帯で max<2500: N={len(g2)} med={statistics.median(g2):.0f}s")
            print(f"  → 差: {statistics.median(gaps) - statistics.median(g2):+.0f}s")
    else:
        print(f"  N={len(edge)} (サンプル不足)")


if __name__ == "__main__":
    main()
