"""全プレイヤー対象: そのキャラの highestTrophies と マッチ間隔 の相関を統計検証。

各 (plyer, brawler) ペアの (gap中央値, highestTrophies) を点としてプロット。
"""
import sqlite3
import json
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
    con = sqlite3.connect("/home/soya/brawl-trio/data/users.db")
    con.row_factory = sqlite3.Row

    # 全タグのbrawler highest map を作る
    wl = con.execute("SELECT tag, profile_json FROM watchlist WHERE profile_json IS NOT NULL").fetchall()
    highest_map = {}  # (tag, brawler) → highest
    for r in wl:
        try:
            p = json.loads(r["profile_json"])
        except Exception:
            continue
        for b in p.get("brawlers", []):
            highest_map[(r["tag"], b["name"])] = b.get("highestTrophies", 0)

    # 各 (tag, brawler) のマッチ間隔中央値
    print("collecting gaps...")
    rows = con.execute(
        "SELECT tag, battle_time, brawler, raw_json FROM battles "
        "WHERE mode='trioShowdown' ORDER BY tag, battle_time"
    ).fetchall()

    by_tag = defaultdict(list)
    for r in rows:
        t = parse_bt(r["battle_time"])
        if t is None: continue
        try:
            raw = json.loads(r["raw_json"])
        except Exception:
            continue
        by_tag[r["tag"]].append({
            "time": t,
            "duration": (raw.get("battle") or {}).get("duration", 0) or 0,
            "brawler": r["brawler"] or "",
        })

    pair_gaps = defaultdict(list)
    for tag, battles in by_tag.items():
        battles.sort(key=lambda x: x["time"])
        for i in range(1, len(battles)):
            gap = (battles[i]["time"] - battles[i-1]["time"]).total_seconds() - battles[i]["duration"]
            if 0 <= gap <= 1800:
                pair_gaps[(tag, battles[i]["brawler"])].append(gap)

    # 集約: 各 (tag, brawler) の med_gap と highest を集めて散布図化
    points = []
    for key, gaps in pair_gaps.items():
        if len(gaps) < 3: continue  # サンプル少なすぎは除外
        h = highest_map.get(key)
        if h is None: continue
        points.append({"tag": key[0], "brawler": key[1], "n": len(gaps), "med_gap": statistics.median(gaps), "highest": h})

    print(f"\nN = {len(points)} (tag, brawler) ペア")

    # 全体: highest 帯ごとの中央値マッチ間隔
    by_band = defaultdict(list)
    for p in points:
        b = (p["highest"] // 500) * 500
        by_band[b].append(p["med_gap"])
    print(f"\n=== highestTrophies帯 → マッチ間隔中央値 ===")
    print(f"{'highest band':<15} {'N(pairs)':<10} {'med of medians':<16} {'mean of medians'}")
    for b in sorted(by_band.keys()):
        arr = by_band[b]
        if len(arr) < 5: continue
        med = statistics.median(arr)
        mean = statistics.mean(arr)
        bar = "█" * int(med / 30)
        print(f"  {b:>5}-{b+499:<6} N={len(arr):<6} {med:>5.0f}s          {mean:>5.0f}s  {bar}")

    # Spearman 相関
    n = len(points)
    if n >= 5:
        xs = [p["highest"] for p in points]
        ys = [p["med_gap"] for p in points]
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
        print(f"\nSpearman相関 highestTrophies × med_gap = {rho:+.3f} (N={n})")
        if rho >= 0.5: print("→ 強い正相関")
        elif rho >= 0.3: print("→ 中程度の正相関")
        elif rho >= 0.15: print("→ 弱い正相関")
        else: print("→ ほぼ無相関")

    # highest >= 5000 (= 旧制度レガシー) の異常値ケース
    print(f"\n=== highest >= 5000 のケース (旧トロフィー制度のレガシー) ===")
    leg = [p for p in points if p["highest"] >= 5000]
    for p in sorted(leg, key=lambda x: -x["highest"])[:15]:
        bar = "█" * int(p["med_gap"] / 30)
        print(f"  tag={p['tag']:<14} {p['brawler']:<10} hi={p['highest']:>6} N={p['n']:>4} med={p['med_gap']:>5.0f}s  {bar}")


if __name__ == "__main__":
    main()
