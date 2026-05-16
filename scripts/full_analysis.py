"""全因子 × マッチ間隔 の総合分析.

入力データ:
  users.db.watchlist.profile_json: アカウント単位の指標 (ガチElo, expLevel, prestige等)
                                  + ブロウラー単位の指標 (highest, prestigeLv, winStreak)
  users.db.battles: 試合履歴 (gap算出のため)

出力:
  1) ペア単位 (tag×brawler) の指標 vs gap中央値 の Spearman 相関一覧
  2) プレイヤー単位 (tag) の指標 vs gap中央値 の相関
  3) highest をコントロールした時の他因子の偏相関 (簡易: 高highest群 vs 低highest群で比較)
  4) cur_trophies帯ごとの「highest が効くか」 を分割集計
  5) 連勝中 (currentWinStreak高) でマッチ遅化するか
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


def spearman(x, y):
    n = len(x)
    if n < 5: return None, 0
    rx = sorted(range(n), key=lambda i: x[i])
    ry = sorted(range(n), key=lambda i: y[i])
    rank_x = [0]*n; rank_y = [0]*n
    for i, idx in enumerate(rx): rank_x[idx] = i
    for i, idx in enumerate(ry): rank_y[idx] = i
    mx = sum(rank_x)/n; my = sum(rank_y)/n
    cov = sum((rank_x[i]-mx)*(rank_y[i]-my) for i in range(n))
    vx = (sum((rank_x[i]-mx)**2 for i in range(n)))**0.5
    vy = (sum((rank_y[i]-my)**2 for i in range(n)))**0.5
    if vx == 0 or vy == 0: return 0, n
    return cov/(vx*vy), n


def sig_label(rho):
    if rho is None: return ""
    a = abs(rho)
    if a >= 0.5: return "***"
    if a >= 0.3: return "**"
    if a >= 0.15: return "*"
    return ""


def main():
    db_path = "/home/soya/brawl-trio/data/users.db"
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row

    # 1. profile_json から各プレイヤー の指標 + brawler indexed
    print("loading profiles...")
    player_meta = {}  # tag → {trophies, highestTrophies, expLevel, rankedElo, ...}
    brawler_meta = {}  # (tag, brawler_name) → {trophies, highestTrophies, prestigeLevel, ...}
    wl = con.execute("SELECT tag, profile_json FROM watchlist WHERE profile_json IS NOT NULL").fetchall()
    for r in wl:
        try:
            p = json.loads(r["profile_json"])
        except Exception:
            continue
        tag = r["tag"]
        player_meta[tag] = {
            "trophies": p.get("trophies", 0) or 0,
            "highestTrophies": p.get("highestTrophies", 0) or 0,
            "totalPrestigeLevel": p.get("totalPrestigeLevel", 0) or 0,
            "expLevel": p.get("expLevel", 0) or 0,
            "expPoints": p.get("expPoints", 0) or 0,
            "rankedElo": p.get("rankedElo", 0) or 0,
            "highestSeasonRankedElo": p.get("highestSeasonRankedElo", 0) or 0,
            "highestAllTimeRankedElo": p.get("highestAllTimeRankedElo", 0) or 0,
            "rankedRank": p.get("rankedRank", 0) or 0,
            "highestAllTimeRankedRank": p.get("highestAllTimeRankedRank", 0) or 0,
            "v3v3": p.get("3vs3Victories", 0) or 0,
            "vSolo": p.get("soloVictories", 0) or 0,
            "vDuo": p.get("duoVictories", 0) or 0,
        }
        for b in p.get("brawlers", []):
            brawler_meta[(tag, b["name"])] = {
                "trophies": b.get("trophies", 0) or 0,
                "highestTrophies": b.get("highestTrophies", 0) or 0,
                "prestigeLevel": b.get("prestigeLevel", 0) or 0,
                "currentWinStreak": b.get("currentWinStreak", 0) or 0,
                "maxWinStreak": b.get("maxWinStreak", 0) or 0,
                "rank": b.get("rank", 0) or 0,
                "power": b.get("power", 0) or 0,
                "hasHC": 1 if b.get("hyperCharges") else 0,
                "starPowers": len(b.get("starPowers") or []),
                "gadgets": len(b.get("gadgets") or []),
                "gears": len(b.get("gears") or []),
            }

    # 2. battles から (tag, brawler) ごとの gap中央値 + 平均順位 + top2率
    print("loading battles...")
    rows = con.execute(
        "SELECT tag, battle_time, brawler, rank, raw_json FROM battles "
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
            "rank": r["rank"] or 0,
        })

    # gap per (tag, brawler)
    pair_gaps = defaultdict(list)
    pair_ranks = defaultdict(list)
    pair_picks = defaultdict(int)
    for tag, battles in by_tag.items():
        battles.sort(key=lambda x: x["time"])
        for i, b in enumerate(battles):
            pair_picks[(tag, b["brawler"])] += 1
            if b["rank"] > 0:
                pair_ranks[(tag, b["brawler"])].append(b["rank"])
            if i == 0: continue
            gap = (b["time"] - battles[i-1]["time"]).total_seconds() - b["duration"]
            if 0 <= gap <= 1800:
                pair_gaps[(tag, b["brawler"])].append(gap)

    # ペア単位の集計データ
    pair_data = []
    for key, gaps in pair_gaps.items():
        if len(gaps) < 3: continue
        tag, brawler = key
        bm = brawler_meta.get(key)
        if bm is None: continue
        ranks = pair_ranks.get(key, [])
        pair_data.append({
            "tag": tag, "brawler": brawler,
            "med_gap": statistics.median(gaps),
            "mean_gap": statistics.mean(gaps),
            "picks": pair_picks[key],
            "gap_n": len(gaps),
            "avg_rank": statistics.mean(ranks) if ranks else 0,
            "top2_rate": sum(1 for r in ranks if r <= 2) / len(ranks) if ranks else 0,
            **bm,
        })

    print(f"pair-level samples: N={len(pair_data)}")

    # 3. ペア単位の相関一覧
    print("\n" + "="*72)
    print("=== ペア単位 (tag × brawler) の各指標 × med_gap Spearman相関 ===")
    print("="*72)
    target_keys = [
        ("highestTrophies", "ブロウラー生涯最高トロ"),
        ("trophies",         "ブロウラー現在トロ"),
        ("prestigeLevel",    "ブロウラー prestige"),
        ("currentWinStreak", "現連勝"),
        ("maxWinStreak",     "最大連勝"),
        ("rank",             "ブロウラー rank (生涯)"),
        ("power",            "ブロウラー power"),
        ("hasHC",            "ハイチャ所持(0/1)"),
        ("picks",            "そのキャラ DB picks"),
        ("avg_rank",         "そのキャラの平均順位 (低いほど強)"),
    ]
    y = [p["med_gap"] for p in pair_data]
    print(f"{'metric':<35} {'rho':<10} {'sig':<6} {'N'}")
    for k, lab in target_keys:
        x = [p[k] for p in pair_data]
        rho, n = spearman(x, y)
        if rho is None: continue
        print(f"  {lab:<33} {rho:>+6.3f}    {sig_label(rho):<5}  {n}")

    # 4. プレイヤー単位 (tag) の指標 × プレイヤーgap中央値 相関
    print("\n" + "="*72)
    print("=== プレイヤー単位の各指標 × そのプレイヤーのgap中央値 ===")
    print("="*72)
    player_data = []
    for tag, battles in by_tag.items():
        all_gaps = []
        battles.sort(key=lambda x: x["time"])
        for i in range(1, len(battles)):
            gap = (battles[i]["time"] - battles[i-1]["time"]).total_seconds() - battles[i]["duration"]
            if 0 <= gap <= 1800: all_gaps.append(gap)
        if len(all_gaps) < 30: continue
        pm = player_meta.get(tag)
        if pm is None: continue
        player_data.append({
            "tag": tag,
            "med_gap": statistics.median(all_gaps),
            "n": len(all_gaps),
            **pm,
        })
    print(f"player-level samples: N={len(player_data)}")
    py = [p["med_gap"] for p in player_data]
    keys_p = [
        ("trophies", "総合トロフィー"),
        ("highestTrophies", "アカウント最高トロ"),
        ("rankedElo", "現ガチElo"),
        ("highestAllTimeRankedElo", "生涯最高ガチElo"),
        ("highestSeasonRankedElo", "シーズン最高Elo"),
        ("rankedRank", "現ガチRank番号"),
        ("highestAllTimeRankedRank", "生涯最高Rank番号"),
        ("expLevel", "経験値レベル"),
        ("totalPrestigeLevel", "総プレ"),
        ("v3v3", "3v3勝利数"),
        ("vSolo", "ソロ勝利数"),
        ("vDuo", "デュオ勝利数"),
    ]
    print(f"{'metric':<35} {'rho':<10} {'sig':<6} {'N'}")
    for k, lab in keys_p:
        x = [p[k] for p in player_data]
        rho, n = spearman(x, y if False else py)
        if rho is None: continue
        print(f"  {lab:<33} {rho:>+6.3f}    {sig_label(rho):<5}  {n}")

    # 5. highest をコントロールした上での他因子効果 (簡易: 同highest帯内での効果)
    print("\n" + "="*72)
    print("=== highest帯ごとに他因子の効果を確認 (highestを固定したとき他は効くか?) ===")
    print("="*72)
    bands = [(0, 999), (1000, 1999), (2000, 2999), (3000, 9999)]
    other_keys = ["picks", "prestigeLevel", "currentWinStreak", "maxWinStreak", "trophies"]
    for lo, hi in bands:
        sub = [p for p in pair_data if lo <= p["highestTrophies"] <= hi]
        if len(sub) < 10: continue
        print(f"\n[highest {lo}-{hi}] N={len(sub)}, med_gap中央値={statistics.median([p['med_gap'] for p in sub]):.0f}s")
        ys = [p["med_gap"] for p in sub]
        for k in other_keys:
            xs = [p[k] for p in sub]
            rho, n = spearman(xs, ys)
            if rho is None: continue
            print(f"  vs {k:<20} rho={rho:+.3f} {sig_label(rho)} (N={n})")

    # 6. 連勝中 (currentWinStreak >= 5) vs それ以外 でマッチ間隔比較
    print("\n" + "="*72)
    print("=== 連勝補正検証: currentWinStreak と マッチ間隔 ===")
    print("="*72)
    streak_buckets = [(0,0), (1,2), (3,4), (5,9), (10,19), (20,99)]
    for lo, hi in streak_buckets:
        sub = [p for p in pair_data if lo <= p["currentWinStreak"] <= hi]
        if len(sub) < 5: continue
        med = statistics.median([p["med_gap"] for p in sub])
        print(f"  WinStreak {lo}-{hi}: N={len(sub)} med={med:.0f}s")

    # 7. 「マッチ間隔」 と「平均順位」 「top2率」 の相関 (= マッチ遅い試合は勝てる/負ける?)
    print("\n" + "="*72)
    print("=== マッチ間隔 × 試合結果 ===")
    print("="*72)
    ys = [p["med_gap"] for p in pair_data]
    for k, lab in [("avg_rank", "平均順位"), ("top2_rate", "TOP2率")]:
        xs = [p[k] for p in pair_data]
        rho, n = spearman(xs, ys)
        print(f"  {lab} vs med_gap: rho={rho:+.3f} {sig_label(rho)} (N={n})")


if __name__ == "__main__":
    main()
