"""マッチ間隔をマッチ平均トロフィーで細かい帯 (100刻み) に分解して表示。
2500 / 2800 などで段差があるか検証用。
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


def extract_match_trophies(raw):
    battle = (raw.get("battle") or {})
    teams = battle.get("teams") or []
    players = battle.get("players") or []
    trophies = []
    if teams:
        for t in teams:
            for p in t:
                tro = (p.get("brawler") or {}).get("trophies", 0) or 0
                trophies.append(tro)
    elif players:
        for p in players:
            tro = (p.get("brawler") or {}).get("trophies", 0) or 0
            trophies.append(tro)
    return trophies


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(Path(__file__).parent.parent / "data" / "users.db"))
    ap.add_argument("--mode", default="trioShowdown")
    ap.add_argument("--max-interval", type=int, default=1800)
    ap.add_argument("--band", type=int, default=100, help="トロフィー帯刻み (default: 100)")
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
        tros = extract_match_trophies(raw)
        by_tag[r["tag"]].append({
            "time": t,
            "duration": battle.get("duration", 0) or 0,
            "avg_trophies": statistics.mean(tros) if tros else 0,
            "type": battle.get("type", "") or "",
        })

    pairs = []
    for tag, battles in by_tag.items():
        battles.sort(key=lambda x: x["time"])
        for i in range(1, len(battles)):
            prev = battles[i-1]; curr = battles[i]
            gap = (curr["time"] - prev["time"]).total_seconds() - curr["duration"]
            if gap < 0 or gap > args.max_interval: continue
            pairs.append({
                "gap": gap,
                "avg_trophies": curr["avg_trophies"],
                "type": curr["type"],
            })

    print(f"mode: {args.mode}, valid pairs: {len(pairs)}")
    print(f"band size: {args.band} trophies")

    # 細かい帯で集計
    by_band = defaultdict(list)
    for p in pairs:
        b = int(p["avg_trophies"] // args.band) * args.band
        by_band[b].append(p["gap"])

    print(f"\n=== {args.band}刻み 帯別マッチ間隔 ===")
    print(f"{'band':<14} {'N':<6} {'median':<8} {'mean':<8} {'Q1':<7} {'Q3':<7}  視覚化")
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
        print(f"{b:>5}-{b+args.band-1:<8} N={len(arr):<5} {med:>5.0f}s   {mean:>5.0f}s   {q1:>4.0f}s   {q3:>4.0f}s  {bar}")


if __name__ == "__main__":
    main()
