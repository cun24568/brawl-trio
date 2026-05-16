"""マッチ内チーム間のトロフィー差を分析。

仮説: 自分のチーム平均が低めでも、 マッチ内の他チーム平均が突出して高い場合、
マッチング時間が長くなる (= マッチが組みにくい = 入る側も待たされる)
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


def extract_team_avgs(raw, my_tag):
    """自分チーム平均, 他チーム平均リスト を返す。"""
    teams = (raw.get("battle") or {}).get("teams") or []
    my_team_avg = None
    other_team_avgs = []
    for team in teams:
        tros = [(pp.get("brawler") or {}).get("trophies", 0) or 0 for pp in team]
        avg = statistics.mean(tros) if tros else 0
        if any(p.get("tag") == my_tag for p in team):
            my_team_avg = avg
        else:
            other_team_avgs.append(avg)
    return my_team_avg, other_team_avgs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(Path(__file__).parent.parent / "data" / "users.db"))
    ap.add_argument("--mode", default="trioShowdown")
    ap.add_argument("--max-interval", type=int, default=1800)
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
        my_avg, others = extract_team_avgs(raw, r["tag"])
        if my_avg is None or not others: continue
        by_tag[r["tag"]].append({
            "time": t,
            "duration": battle.get("duration", 0) or 0,
            "my_team_avg": my_avg,
            "max_other_team_avg": max(others),
            "min_other_team_avg": min(others),
            "all_teams_avg": (my_avg + sum(others)) / (1 + len(others)),
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
                "my_team_avg": curr["my_team_avg"],
                "max_other_team_avg": curr["max_other_team_avg"],
                "spread": curr["max_other_team_avg"] - curr["my_team_avg"],  # 正なら他が上, 負なら他が下
            })

    print(f"mode: {args.mode}, valid pairs: {len(pairs)}")

    # 自分チーム平均帯ごとに、 「他チーム最高平均」 の高低でマッチ間隔比較
    print(f"\n=== 自分チーム平均帯 × 他チーム最高平均との差 ===")
    print(f"(spread = 他チーム最高 - 自分チーム; +なら他チームが上)\n")
    my_bands = [(0,999), (1000,1499), (1500,1999), (2000,2399), (2400,2699), (2700,2999)]
    spread_bands = [(-9999,-200), (-200,200), (200,500), (500,900), (900,9999)]
    spread_labels = ["他が-200以下(同帯か下)", "他が±200(同帯)", "他が+200〜+500(やや上)", "他が+500〜+900(かなり上)", "他が+900超(突出)"]
    header = f"{'自分avg':<14}"
    for lab in spread_labels:
        header += f"{lab[:14]:<16}"
    print(header)
    for lo, hi in my_bands:
        line = f"{lo}-{hi:<10}"
        for (slo, shi), lab in zip(spread_bands, spread_labels):
            arr = [p["gap"] for p in pairs if lo <= p["my_team_avg"] <= hi and slo <= p["spread"] < shi]
            if len(arr) < 5:
                line += f"N={len(arr):<14}"
            else:
                med = statistics.median(arr)
                line += f"{med:>4.0f}s(N={len(arr)}){'':<5}"
        print(line)

    # 一目で見る要約: 「自分avg 2400-2599 帯」 で他チーム最高との関係
    print(f"\n=== 詳細: 自分チーム avg 2400-2599 のマッチで、 他チーム最高 ===")
    focus = [p for p in pairs if 2400 <= p["my_team_avg"] < 2700]
    by_other = defaultdict(list)
    for p in focus:
        b = int(p["max_other_team_avg"] // 200) * 200
        by_other[b].append(p["gap"])
    print(f"  N(focus)={len(focus)}")
    for b in sorted(by_other.keys()):
        arr = by_other[b]
        if len(arr) < 5: continue
        med = statistics.median(arr)
        bar = "█" * int(med / 40)
        print(f"  他最高 {b:>4}-{b+199:<4}: N={len(arr):<5} med={med:>5.0f}s  {bar}")

    # 同じ「自分2400-2599」 でも、 spread別 (他チーム最高 - 自分) で比較
    print(f"\n=== 自分avg 2400-2599: 他チーム最高との差 (spread) 別 ===")
    spread_focus = focus
    by_spread = defaultdict(list)
    for p in spread_focus:
        s = p["spread"]
        b = int(s // 200) * 200
        by_spread[b].append(p["gap"])
    for b in sorted(by_spread.keys()):
        arr = by_spread[b]
        if len(arr) < 5: continue
        med = statistics.median(arr)
        bar = "█" * int(med / 40)
        sign = "+" if b >= 0 else ""
        print(f"  spread {sign}{b:>4}-{sign}{b+199:<4}: N={len(arr):<5} med={med:>5.0f}s  {bar}")


if __name__ == "__main__":
    main()
