"""マッチング待機時間の間接推定スクリプト.

公式APIでは取れないので、 連続2試合の間隔から推定:
  interval = battle_time_B - duration_B - battle_time_A
           ≒ ロビー帰還 + マッチング待機 + 試合準備 + メニュー操作

ssh soya@vps 'python3 /home/soya/brawl-trio/scripts/match_interval.py'
ssh soya@vps 'python3 /home/soya/brawl-trio/scripts/match_interval.py --mode trioShowdown'
"""
import argparse
import json
import sqlite3
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def parse_battle_time(bt: str):
    try:
        return datetime.strptime(bt[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(Path(__file__).parent.parent / "data" / "users.db"))
    ap.add_argument("--mode", default=None, help="絞り込み (例: trioShowdown, duoShowdown, gemGrab)")
    ap.add_argument("--max-interval", type=int, default=1800, help="このsec超は外れ値として除外")
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    where = "1=1"
    params = []
    if args.mode:
        where += " AND mode = ?"
        params.append(args.mode)
    rows = con.execute(
        f"SELECT tag, battle_time, mode, map, rank, raw_json FROM battles WHERE {where} ORDER BY tag, battle_time",
        params,
    ).fetchall()
    print(f"total battles: {len(rows)}")

    by_tag = defaultdict(list)
    for r in rows:
        d = parse_battle_time(r["battle_time"])
        if d is None:
            continue
        try:
            raw = json.loads(r["raw_json"])
        except Exception:
            continue
        battle = raw.get("battle") or {}
        duration = battle.get("duration", 0) or 0
        by_tag[r["tag"]].append({
            "time": d,
            "mode": r["mode"],
            "map": r["map"],
            "rank": r["rank"],
            "duration": duration,
        })

    intervals = []
    by_mode = defaultdict(list)
    by_hour = defaultdict(list)
    for tag, battles in by_tag.items():
        battles.sort(key=lambda x: x["time"])
        for i in range(1, len(battles)):
            prev = battles[i - 1]
            curr = battles[i]
            # interval = (curr終了 - curr長さ) - prev終了 = 「prev終了 → curr開始」 (ロビー+マッチング)
            gap_sec = (curr["time"] - prev["time"]).total_seconds() - curr["duration"]
            # 0未満 (= 計算上ありえない、 公式APIの精度問題) は除外
            if gap_sec < 0:
                continue
            # 30分以上の間隔は休憩・別アクティビティなのでマッチング推定に使えない
            if gap_sec > args.max_interval:
                continue
            intervals.append(gap_sec)
            by_mode[curr["mode"]].append(gap_sec)
            # JST hour で時間帯別
            jst_hour = (curr["time"].hour + 9) % 24
            by_hour[jst_hour].append(gap_sec)

    if not intervals:
        print("有効な連続戦闘ペアが見つからない")
        return

    def stats(arr, name):
        if not arr:
            return f"{name:<20}: N=0"
        med = statistics.median(arr)
        mean = statistics.mean(arr)
        q1, q3 = (sorted(arr)[len(arr)//4], sorted(arr)[3*len(arr)//4])
        return f"{name:<20}: N={len(arr):>6}  median={med:>6.1f}s  mean={mean:>6.1f}s  Q1={q1:>5.1f}s  Q3={q3:>5.1f}s"

    print(f"\n=== 全体 ===")
    print(stats(intervals, "ALL"))

    print(f"\n=== モード別 (試合数順) ===")
    for mode, arr in sorted(by_mode.items(), key=lambda x: -len(x[1]))[:15]:
        if len(arr) < 10:
            continue
        print(stats(arr, mode))

    print(f"\n=== 時間帯別 (JST) ===")
    for h in range(24):
        arr = by_hour.get(h, [])
        if len(arr) < 10:
            continue
        med = statistics.median(arr)
        bar = "█" * int(med / 10)
        print(f"  {h:02d}時 N={len(arr):>5} 中央値={med:>5.1f}s {bar}")

    print("\n注: マッチング待機時間 ≠ この値。")
    print("  この値 ≒ 前試合終了 → 次試合開始まで (= ロビー帰還 + キュー + 準備 + メニュー操作)")
    print("  純粋なキュー時間はもっと短い。 ただし時間帯/モード別の相対比較には使える。")


if __name__ == "__main__":
    main()
