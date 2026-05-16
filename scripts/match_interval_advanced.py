"""マッチング待機時間 拡張分析:
- battle.type別 (ranked/soloRanked/その他)
- マッチ平均トロフィー帯別 (1000未満/1000-1500/1500-2000/2000-2500/2500+)
- 仮説: 平均トロフィー 2000+ で遅くなる、 ガチ系で遅くなる
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
    """battle.teams or battle.players から全参加者の brawler.trophies を抽出"""
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


def tro_band(avg):
    if avg < 1000: return "<1000"
    if avg < 1500: return "1000-1499"
    if avg < 2000: return "1500-1999"
    if avg < 2500: return "2000-2499"
    if avg < 3000: return "2500-2999"
    return "3000+"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(Path(__file__).parent.parent / "data" / "users.db"))
    ap.add_argument("--mode", default="trioShowdown", help="絞り込み (default: trioShowdown)")
    ap.add_argument("--max-interval", type=int, default=1800)
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT tag, battle_time, mode, raw_json FROM battles WHERE mode = ? ORDER BY tag, battle_time",
        (args.mode,),
    ).fetchall()
    print(f"target mode: {args.mode}, total battles: {len(rows)}")

    # tag ごとに連続戦闘ペアを作る
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
            "type": battle.get("type", "") or "",
            "avg_trophies": statistics.mean(tros) if tros else 0,
            "players_count": len(tros),
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
                "type": curr["type"],
                "avg_trophies": curr["avg_trophies"],
                "players_count": curr["players_count"],
            })

    print(f"valid pairs: {len(pairs)}")
    if not pairs:
        return

    def summarize(group_arr, name):
        gaps = [p["gap"] for p in group_arr]
        if len(gaps) < 5:
            return f"{name:<20}: N={len(gaps):>5}  (サンプル不足)"
        med = statistics.median(gaps)
        mean = statistics.mean(gaps)
        n = len(gaps)
        return f"{name:<20}: N={n:>5}  median={med:>6.1f}s  mean={mean:>6.1f}s"

    # battle.type 別
    print(f"\n=== battle.type 別 ===")
    by_type = defaultdict(list)
    for p in pairs:
        by_type[p["type"] or "(empty)"].append(p)
    for k, arr in sorted(by_type.items(), key=lambda x: -len(x[1])):
        print(summarize(arr, k))

    # 平均トロフィー帯別 (全体)
    print(f"\n=== マッチ平均トロフィー帯別 ===")
    by_band = defaultdict(list)
    for p in pairs:
        by_band[tro_band(p["avg_trophies"])].append(p)
    bands_order = ["<1000", "1000-1499", "1500-1999", "2000-2499", "2500-2999", "3000+"]
    for b in bands_order:
        arr = by_band.get(b, [])
        if not arr: continue
        print(summarize(arr, b))

    # type=ranked のみ で帯別
    ranked_pairs = [p for p in pairs if "ranked" in (p["type"] or "").lower()]
    if ranked_pairs:
        print(f"\n=== ガチ系 (type=*ranked*) のトロフィー帯別 N={len(ranked_pairs)} ===")
        by_band2 = defaultdict(list)
        for p in ranked_pairs:
            by_band2[tro_band(p["avg_trophies"])].append(p)
        for b in bands_order:
            arr = by_band2.get(b, [])
            if not arr: continue
            print(summarize(arr, b))

    # 通常系のみ
    normal_pairs = [p for p in pairs if "ranked" not in (p["type"] or "").lower()]
    if normal_pairs:
        print(f"\n=== 通常系 (type!=*ranked*) のトロフィー帯別 N={len(normal_pairs)} ===")
        by_band3 = defaultdict(list)
        for p in normal_pairs:
            by_band3[tro_band(p["avg_trophies"])].append(p)
        for b in bands_order:
            arr = by_band3.get(b, [])
            if not arr: continue
            print(summarize(arr, b))


if __name__ == "__main__":
    main()
