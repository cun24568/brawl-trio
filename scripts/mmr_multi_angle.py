"""MMR解析: 複数角度からの仮説検証 (2026-05-17 セット).

過去解析で確定した知見:
  - ブロウラー highest が最強因子 (rho=+0.602)
  - picks 逆相関 (高highestを使い込まないと遅い)
  - 連勝5+で +10-15s 遅化
  - 「遅い試合 = 勝てる試合」 (rho=-0.485)

本スクリプトの新規仮説:
  A. 対戦相手側 highest × 自分の gap 相関
     → 相手チーム/敵チームの brawler highest 中央値が高いほど、 その試合前後の gap が長い?
     → 確認できれば「matchmaking は対称」 = 自分のMMRが相手側にも反映されている証拠
  B. (highest - current) 乖離 × gap
     → 過去栄光が残ってるキャラほど gap 長い? (旧MMR残存量の直接観測)
  C. クラブ内 MMR 連動
     → 同クラブメンバー間で gap 中央値が似てる? (vs ランダム抽出時の分散)
  D. マップ別 gap 分布
     → マップごとに MMR厳しさが違う? (= マップ別 matchmaking pool)
  E. 試合内 trophy 分散 vs gap
     → 「gap長い試合ほど 9人のトロフィー分散が小さい」 = サーバが精密マッチ組んでる証拠
  F. ガチバトル経験量 × 全モード gap
     → rankedElo・highestAllTimeRankedElo が全モード matchmaking に効く?
  G. 出現国/地域効果
     → 公式APIに国情報なし、 club から推定
  H. 「乖離大ブロウラー」 多く所持してる人 ほど total gap 長い?

実装方針: 1 script で全部走らせる。 結果は print + jsonl。
"""
import json
import sqlite3
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


DB = "/home/soya/brawl-trio/data/users.db"


def spearman(x, y):
    n = len(x)
    if n < 5: return None, n
    rx = sorted(range(n), key=lambda i: x[i])
    ry = sorted(range(n), key=lambda i: y[i])
    rank_x = [0]*n; rank_y = [0]*n
    for i, idx in enumerate(rx): rank_x[idx] = i
    for i, idx in enumerate(ry): rank_y[idx] = i
    mx = sum(rank_x)/n; my = sum(rank_y)/n
    cov = sum((rank_x[i]-mx)*(rank_y[i]-my) for i in range(n))
    vx = (sum((rank_x[i]-mx)**2 for i in range(n)))**0.5
    vy = (sum((rank_y[i]-my)**2 for i in range(n)))**0.5
    if vx == 0 or vy == 0: return 0.0, n
    return cov/(vx*vy), n


def sig(rho):
    if rho is None: return ""
    a = abs(rho)
    if a >= 0.5: return "***"
    if a >= 0.3: return "**"
    if a >= 0.15: return "*"
    return ""


def parse_bt(bt):
    try:
        return datetime.strptime(bt[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    # 1. プロフィール: brawler indexed
    print("loading profiles...")
    player_meta = {}
    brawler_meta = {}  # (tag, brawler_name) → meta
    wl = con.execute("SELECT tag, profile_json FROM watchlist WHERE profile_json IS NOT NULL").fetchall()
    for r in wl:
        try:
            p = json.loads(r["profile_json"])
        except Exception:
            continue
        tag = r["tag"]
        player_meta[tag] = {
            "name": p.get("name", ""),
            "trophies": p.get("trophies", 0) or 0,
            "highestTrophies": p.get("highestTrophies", 0) or 0,
            "expLevel": p.get("expLevel", 0) or 0,
            "rankedElo": p.get("rankedElo", 0) or 0,
            "highestAllTimeRankedElo": p.get("highestAllTimeRankedElo", 0) or 0,
            "totalPrestigeLevel": p.get("totalPrestigeLevel", 0) or 0,
            "v3v3": p.get("3vs3Victories", 0) or 0,
            "vSolo": p.get("soloVictories", 0) or 0,
            "vDuo": p.get("duoVictories", 0) or 0,
            "club_tag": (p.get("club") or {}).get("tag", ""),
            "club_name": (p.get("club") or {}).get("name", ""),
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
            }
    print(f"  {len(player_meta)} players, {len(brawler_meta)} (player×brawler) entries")

    # 2. 試合データ (trioShowdown のみ。 他モードは数が少なすぎる)
    print("loading battles (trioShowdown)...")
    rows = con.execute(
        "SELECT tag, battle_time, mode, map, brawler, rank, raw_json FROM battles "
        "WHERE mode='trioShowdown' ORDER BY tag, battle_time"
    ).fetchall()
    print(f"  {len(rows)} rows")

    # 試合を整形: 各試合 → [my_brawler, my_rank, enemies(list of brawler+trophies), my_team, duration, map, time]
    by_tag = defaultdict(list)
    for r in rows:
        t = parse_bt(r["battle_time"])
        if t is None: continue
        try:
            raw = json.loads(r["raw_json"])
        except Exception:
            continue
        battle = raw.get("battle") or {}
        teams = battle.get("teams") or []
        my_idx = None
        my_team = None
        for i, team in enumerate(teams):
            if any(p.get("tag") == r["tag"] for p in team):
                my_idx = i
                my_team = team
                break
        if my_idx is None:
            continue
        enemy_teams = [team for i, team in enumerate(teams) if i != my_idx]
        # 各チーム → list of (brawler_name, current_trophies)
        my_team_brs = [((p.get("brawler") or {}).get("name", ""), (p.get("brawler") or {}).get("trophies", 0)) for p in my_team]
        enemy_brs = []
        for et in enemy_teams:
            for p in et:
                enemy_brs.append(((p.get("brawler") or {}).get("name", ""), (p.get("brawler") or {}).get("trophies", 0)))
        by_tag[r["tag"]].append({
            "time": t,
            "duration": battle.get("duration", 0) or 0,
            "brawler": r["brawler"] or "",
            "rank": r["rank"] or 0,
            "map": r["map"] or "",
            "my_team": my_team_brs,
            "enemies": enemy_brs,
            # 試合内9人 (自分以外8人) のトロフィー
            "trio_trophies": [tr for _, tr in (my_team_brs + enemy_brs)],
        })

    # 各試合の前ペア gap を算出
    print("computing gaps + per-battle features...")
    enriched = []  # 全試合 (gap付き)
    pair_gaps = defaultdict(list)  # (tag, brawler) → [gap, ...]
    for tag, battles in by_tag.items():
        battles.sort(key=lambda x: x["time"])
        for i, b in enumerate(battles):
            if i == 0:
                continue
            prev = battles[i-1]
            gap = (b["time"] - prev["time"]).total_seconds() - b["duration"]
            if not (0 <= gap <= 1800):
                continue
            # 敵 brawler の highestTrophies 中央値 (本人のprofile から)
            # ※ 敵プレイヤーのprofile_json は手元にないので、 「敵が使ったbrawler の current trophies」 で代替
            # ただし、 自分の brawler の highest は brawler_meta から取れる
            my_meta = brawler_meta.get((tag, b["brawler"]))
            if my_meta is None:
                continue
            enriched.append({
                "tag": tag,
                "time": b["time"],
                "gap": gap,
                "duration": b["duration"],
                "brawler": b["brawler"],
                "map": b["map"],
                "rank": b["rank"],
                "my_brawler_highest": my_meta["highestTrophies"],
                "my_brawler_current": my_meta["trophies"],
                "my_brawler_diff": my_meta["highestTrophies"] - my_meta["trophies"],
                "my_brawler_hasHC": my_meta["hasHC"],
                "enemy_trophy_median": statistics.median([tr for _, tr in b["enemies"]] or [0]),
                "enemy_trophy_max": max([tr for _, tr in b["enemies"]] or [0]),
                "trio_trophy_var": statistics.variance(b["trio_trophies"]) if len(b["trio_trophies"]) > 1 else 0,
                "trio_trophy_med": statistics.median(b["trio_trophies"] or [0]),
            })
            pair_gaps[(tag, b["brawler"])].append(gap)

    print(f"  enriched battle samples: N={len(enriched)}")

    # ================================================================
    print("\n" + "="*72)
    print("=== A. 対戦相手側 trophies × 自分の gap ===")
    print("="*72)
    print("敵チームの現在トロフィー (median/max) が、 その試合のgapと相関するか?")
    print("仮説: 「自分のMMRに見合う相手」 が組まれる → 相手の trophies は自分のMMR代理指標")
    ys = [e["gap"] for e in enriched]
    for key in ["enemy_trophy_median", "enemy_trophy_max", "trio_trophy_med"]:
        xs = [e[key] for e in enriched]
        rho, n = spearman(xs, ys)
        print(f"  {key:<22} vs gap: rho={rho:+.3f} {sig(rho):<5} N={n}")

    # 高highestブロウラーを使った試合とそうでない試合で、 敵trophy分布を比較
    print("\n  ★ 自分の highest 帯別 × 相手の trophy 中央値")
    bands = [(0, 1499), (1500, 2499), (2500, 3499), (3500, 99999)]
    for lo, hi in bands:
        sub = [e for e in enriched if lo <= e["my_brawler_highest"] <= hi]
        if len(sub) < 20: continue
        med_enemy = statistics.median([e["enemy_trophy_median"] for e in sub])
        med_gap = statistics.median([e["gap"] for e in sub])
        print(f"  my_highest {lo:>5}-{hi:<5} (N={len(sub):>4})  enemy_tr_med={med_enemy:>5.0f}  my_gap_med={med_gap:>5.0f}s")

    # ================================================================
    print("\n" + "="*72)
    print("=== B. (highest - current) 乖離 × gap (過去栄光MMR残存) ===")
    print("="*72)
    print("仮説: highest と current の差が大きい (= 過去高かったが今下がってる) ほど gap 長い")
    diff_xs = [e["my_brawler_diff"] for e in enriched]
    rho, n = spearman(diff_xs, ys)
    print(f"  (highest - current) vs gap: rho={rho:+.3f} {sig(rho)} N={n}")
    # 乖離帯ごとの中央値
    print("  乖離帯別 gap中央値:")
    for lo, hi in [(0, 99), (100, 499), (500, 999), (1000, 1999), (2000, 99999)]:
        sub = [e for e in enriched if lo <= e["my_brawler_diff"] <= hi]
        if len(sub) < 10: continue
        gm = statistics.median([e["gap"] for e in sub])
        print(f"    乖離 {lo:>5}-{hi:<5} (N={len(sub):>5})  gap_med={gm:>5.0f}s")

    # ================================================================
    print("\n" + "="*72)
    print("=== C. クラブ内 MMR 連動 ===")
    print("="*72)
    print("仮説: 同じクラブ所属メンバー同士で gap中央値が似てる")
    # プレイヤー単位 median gap
    player_med_gap = {}
    for tag, battles in by_tag.items():
        gaps = []
        battles.sort(key=lambda x: x["time"])
        for i in range(1, len(battles)):
            g = (battles[i]["time"] - battles[i-1]["time"]).total_seconds() - battles[i]["duration"]
            if 0 <= g <= 1800: gaps.append(g)
        if len(gaps) >= 30:
            player_med_gap[tag] = statistics.median(gaps)
    # クラブ別グループ化
    club_groups = defaultdict(list)
    for tag, med in player_med_gap.items():
        ct = player_meta.get(tag, {}).get("club_tag", "")
        if ct:
            club_groups[ct].append((tag, med))
    print(f"  対象クラブ数 (2人以上): {sum(1 for _, ms in club_groups.items() if len(ms) >= 2)}")
    print(f"  対象クラブ詳細:")
    for ct, ms in sorted(club_groups.items(), key=lambda x: -len(x[1])):
        if len(ms) < 2: continue
        gs = [m for _, m in ms]
        spread = max(gs) - min(gs)
        cn = player_meta.get(ms[0][0], {}).get("club_name", "?")
        print(f"    [{cn[:20]:<20}] N={len(ms)}  gap range {min(gs):.0f}-{max(gs):.0f}s (spread={spread:.0f})  members={[player_meta[t]['name'][:8] for t, _ in ms]}")
    # クラブ内分散 vs 全体分散
    within_var = []
    for ct, ms in club_groups.items():
        if len(ms) < 2: continue
        gs = [m for _, m in ms]
        within_var.append(statistics.variance(gs))
    total_var = statistics.variance(list(player_med_gap.values())) if len(player_med_gap) > 1 else 0
    if within_var:
        avg_within = statistics.mean(within_var)
        print(f"  ★ クラブ内 平均分散={avg_within:.0f}, 全プレイヤー分散={total_var:.0f}")
        print(f"  内/外比 = {avg_within/total_var:.2f}  (1.0未満なら クラブ内が均一 = MMR 連動傍証)")

    # ================================================================
    print("\n" + "="*72)
    print("=== D. マップ別 gap 分布 ===")
    print("="*72)
    print("マップごとに gap中央値・サンプル数を出す")
    by_map_gap = defaultdict(list)
    for e in enriched:
        by_map_gap[e["map"]].append(e["gap"])
    rows_m = []
    for m, gs in by_map_gap.items():
        if len(gs) < 20: continue
        gs.sort()
        rows_m.append((m, len(gs), statistics.median(gs), statistics.mean(gs)))
    rows_m.sort(key=lambda x: -x[2])  # 中央値遅い順
    print(f"  {'map':<30} {'N':>5} {'med':>6} {'mean':>6}")
    for m, n, med, mean in rows_m:
        print(f"  {m:<30} {n:>5} {med:>5.0f}s {mean:>5.0f}s")
    # マップ別 highest×gap 相関 (上位5マップ)
    print("\n  ★ マップ別 highest×gap 相関 (N>=30):")
    for m, _, _, _ in rows_m[:8]:
        sub = [e for e in enriched if e["map"] == m]
        if len(sub) < 30: continue
        xs_m = [e["my_brawler_highest"] for e in sub]
        ys_m = [e["gap"] for e in sub]
        rho, n = spearman(xs_m, ys_m)
        print(f"  {m:<30} N={n:>4}  rho(highest,gap)={rho:+.3f} {sig(rho)}")

    # ys を全 enriched の gap に戻す (E 以降で使う)
    ys = [e["gap"] for e in enriched]

    # ================================================================
    print("\n" + "="*72)
    print("=== E. 試合内 trophy 分散 vs gap ===")
    print("="*72)
    print("仮説: gap長い試合ほど、 9人の trophy が揃ってる (= 精密マッチ)")
    xs = [e["trio_trophy_var"] for e in enriched]
    rho, n = spearman(xs, ys)
    print(f"  trio_trophy分散 vs gap: rho={rho:+.3f} {sig(rho)} N={n}")
    # gap帯別の分散中央値
    print("  gap帯別 trio_trophy分散 中央値:")
    gap_bands = [(0, 60), (60, 120), (120, 240), (240, 480), (480, 9999)]
    for lo, hi in gap_bands:
        sub = [e for e in enriched if lo <= e["gap"] < hi]
        if len(sub) < 20: continue
        med_var = statistics.median([e["trio_trophy_var"] for e in sub])
        med_diff_tr = max(e["trio_trophies"][0] for e in sub) - min(e["trio_trophies"][-1] for e in sub) if sub else 0
        print(f"    gap {lo:>4}-{hi:<5}s (N={len(sub):>4})  trio_tr_var_med={med_var:>10.0f}")

    # ================================================================
    print("\n" + "="*72)
    print("=== F. ガチバトル経験量 × 全モード gap (プレイヤー単位) ===")
    print("="*72)
    print("仮説: rankedElo 高い人ほど、 トリオでもmatchmaking 厳しい (アカウントMMR寄与)")
    pdata = []
    for tag, med in player_med_gap.items():
        pm = player_meta.get(tag)
        if not pm: continue
        pdata.append({"tag": tag, "med": med, **pm})
    for k in ["rankedElo", "highestAllTimeRankedElo", "expLevel", "totalPrestigeLevel",
              "trophies", "highestTrophies", "v3v3", "vSolo", "vDuo"]:
        x = [p[k] for p in pdata]
        y = [p["med"] for p in pdata]
        rho, n = spearman(x, y)
        print(f"  {k:<28} vs player_med_gap: rho={rho:+.3f} {sig(rho)} N={n}")

    # ================================================================
    print("\n" + "="*72)
    print("=== G. 「乖離大ブロウラー」 多く所持 × player gap ===")
    print("="*72)
    print("仮説: highest-current 乖離が大きいキャラを多く持つ人 = 古参 = total gap 長い")
    diff_count = defaultdict(int)
    diff_sum = defaultdict(int)
    for (tag, br), bm in brawler_meta.items():
        d = bm["highestTrophies"] - bm["trophies"]
        if d >= 500:
            diff_count[tag] += 1
        diff_sum[tag] += max(0, d)
    print(f"  {'tag':<15} {'med_gap':>8} {'n_diff>=500':>11} {'sum_diff':>10} {'name'}")
    for tag, med in sorted(player_med_gap.items(), key=lambda x: -x[1]):
        pm = player_meta.get(tag, {})
        print(f"  {tag:<15} {med:>7.0f}s {diff_count.get(tag, 0):>11} {diff_sum.get(tag, 0):>10} {pm.get('name', '?')}")
    # 相関
    xs = [diff_count.get(t, 0) for t in player_med_gap]
    ys = [m for m in player_med_gap.values()]
    rho, n = spearman(xs, ys)
    print(f"  ★ 乖離500+ブロウラー数 vs player_gap: rho={rho:+.3f} {sig(rho)} N={n}")
    xs2 = [diff_sum.get(t, 0) for t in player_med_gap]
    rho2, n2 = spearman(xs2, ys)
    print(f"  ★ 乖離合計   vs player_gap: rho={rho2:+.3f} {sig(rho2)} N={n2}")

    # ================================================================
    print("\n" + "="*72)
    print("=== H. ハイチャ装備有無 × gap ===")
    print("="*72)
    print("仮説: ハイチャ持ってる brawler は強いから、 matchmaking が厳しい (== gap長い)")
    hc_gaps = [e["gap"] for e in enriched if e["my_brawler_hasHC"] == 1]
    no_gaps = [e["gap"] for e in enriched if e["my_brawler_hasHC"] == 0]
    if hc_gaps and no_gaps:
        print(f"  HC所持: N={len(hc_gaps)}, gap_med={statistics.median(hc_gaps):.0f}s, mean={statistics.mean(hc_gaps):.0f}s")
        print(f"  HC無し: N={len(no_gaps)}, gap_med={statistics.median(no_gaps):.0f}s, mean={statistics.mean(no_gaps):.0f}s")
        diff = statistics.median(hc_gaps) - statistics.median(no_gaps)
        print(f"  差 (HC - 無): {diff:+.0f}s")

    # ================================================================
    print("\n" + "="*72)
    print("=== I. 時系列 自己相関: 「遅い試合の次は遅い?」 ===")
    print("="*72)
    print("仮説: 直前の gap が長い = MMR帯が高くて待たされる人 → 次の試合 も長い")
    print("検証: 同一 (tag, brawler) で連続 gap の自己相関")
    auto_pairs = []
    pair_gaps_ordered = defaultdict(list)
    for tag, battles in by_tag.items():
        battles.sort(key=lambda x: x["time"])
        for i in range(1, len(battles)):
            g = (battles[i]["time"] - battles[i-1]["time"]).total_seconds() - battles[i]["duration"]
            if not (0 <= g <= 1800): continue
            pair_gaps_ordered[(tag, battles[i]["brawler"])].append(g)
    for k, gs in pair_gaps_ordered.items():
        for j in range(1, len(gs)):
            auto_pairs.append((gs[j-1], gs[j]))
    if len(auto_pairs) >= 30:
        xs = [a[0] for a in auto_pairs]
        ys = [a[1] for a in auto_pairs]
        rho, n = spearman(xs, ys)
        print(f"  連続gapの自己相関 (lag=1): rho={rho:+.3f} {sig(rho)} N={n}")

    print("\n=== END ===")


if __name__ == "__main__":
    main()
