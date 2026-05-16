"""マッチ間隔を 自分のチーム平均トロフィー (3人) で帯分け。
体感: 自分チーム平均 2000+ でマッチ遅い、 2500/2800 でも段差?
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


def extract_my_team_avg(raw, my_tag):
    """自分のチーム (自分のタグを含むチーム) の brawler.trophies 平均を返す。
    solo モード等の teams 無しの場合は自分1人分。"""
    battle = (raw.get("battle") or {})
    teams = battle.get("teams") or []
    for team in teams:
        if any(p.get("tag") == my_tag for p in team):
            tros = [(pp.get("brawler") or {}).get("trophies", 0) or 0 for pp in team]
            return statistics.mean(tros) if tros else 0, len(team)
    players = battle.get("players") or []
    for p in players:
        if p.get("tag") == my_tag:
            return (p.get("brawler") or {}).get("trophies", 0) or 0, 1
    return 0, 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(Path(__file__).parent.parent / "data" / "users.db"))
    ap.add_argument("--mode", default="trioShowdown")
    ap.add_argument("--max-interval", type=int, default=1800)
    ap.add_argument("--band", type=int, default=100)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--end", type=int, default=3500)
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
        avg, team_size = extract_my_team_avg(raw, r["tag"])
        by_tag[r["tag"]].append({
            "time": t,
            "duration": battle.get("duration", 0) or 0,
            "my_team_avg": avg,
            "team_size": team_size,
        })

    pairs = []
    for tag, battles in by_tag.items():
        battles.sort(key=lambda x: x["time"])
        for i in range(1, len(battles)):
            prev = battles[i-1]; curr = battles[i]
            gap = (curr["time"] - prev["time"]).total_seconds() - curr["duration"]
            if gap < 0 or gap > args.max_interval: continue
            if curr["my_team_avg"] <= 0: continue
            pairs.append({"gap": gap, "my_team_avg": curr["my_team_avg"]})

    print(f"mode: {args.mode}, valid pairs: {len(pairs)}")
    print(f"band size: {args.band} trophies (自分のチーム平均)")

    by_band = defaultdict(list)
    for p in pairs:
        b = int(p["my_team_avg"] // args.band) * args.band
        by_band[b].append(p["gap"])

    print(f"\n=== {args.band}刻み 自分チーム平均トロ別マッチ間隔 ===")
    for b in range(args.start, args.end, args.band):
        arr = by_band.get(b, [])
        if len(arr) < 5:
            if arr:
                print(f"{b:>5}-{b+args.band-1:<8} N={len(arr):<5} (サンプル不足)")
            continue
        med = statistics.median(arr)
        mean = statistics.mean(arr)
        srt = sorted(arr)
        q1 = srt[len(srt)//4]
        q3 = srt[3*len(srt)//4]
        bar = "█" * int(med / 30)
        print(f"{b:>5}-{b+args.band-1:<8} N={len(arr):<5} {med:>5.0f}s   {mean:>5.0f}s   Q1={q1:>4.0f}s Q3={q3:>4.0f}s  {bar}")


if __name__ == "__main__":
    main()
