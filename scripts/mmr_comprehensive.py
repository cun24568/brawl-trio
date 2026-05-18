"""MMR解析 包括版: チーム/試合/キャラ/プレイヤー × gap/rank/top2 全相関.

ユーザー要望 (2026-05-17):
  - チーム平均トロ / 試合の平均トロ / チーム最高トロ
  - ガチバトル (Elo) / 総合トロ
  - キャラの使用率 / 勝率
  - + 他の角度を貪欲に

実装する指標 (battle単位):

【チーム指標】
  team_avg_tr, team_max_tr, team_min_tr, team_var_tr  自チーム3人 brawler.trophies
  team_avg_minus_min                                   最強と最弱の差

【試合全体指標】
  match_avg_tr, match_max_tr, match_min_tr, match_var_tr  全9人
  enemy_avg_tr, enemy_max_tr, enemy_min_tr               敵6人

【ブロウラー指標 (自分)】
  my_br_tr           現在トロ
  my_br_highest      生涯最高
  my_br_diff         (highest - current)
  my_br_pickrate     DB内 そのキャラ ピック比率
  my_br_winrate      DB内 そのキャラ top2率
  my_br_avgrank      DB内 そのキャラ 平均順位
  my_br_hc           ハイチャ装備
  my_br_streak       currentWinStreak
  my_br_maxstreak    maxWinStreak

【プレイヤー指標】
  p_trophies         アカウント総トロ
  p_highest          アカウント最高トロ
  p_rankedElo        現ガチElo
  p_highestRankedElo 生涯最高ガチElo
  p_expLevel
  p_vDuo / vSolo / v3v3

【時間指標】
  hour_of_day, day_of_week
  prev_gap, recent5_avg_rank, recent5_top2_rate

【ターゲット】
  gap     次試合との間隔
  rank    試合結果順位
  top2    rank<=2 二値

出力:
  全因子 × {gap, rank, top2_rate} の Spearman 相関一覧
  各因子 帯別 中央値表
"""
import json
import sqlite3
import statistics
from collections import defaultdict, Counter
from datetime import datetime, timezone

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

    # 1. プロフィール
    print("=== loading profiles ===")
    player_meta = {}
    brawler_meta = {}
    wl = con.execute("SELECT tag, profile_json FROM watchlist WHERE profile_json IS NOT NULL").fetchall()
    for r in wl:
        try:
            p = json.loads(r["profile_json"])
        except Exception:
            continue
        tag = r["tag"]
        player_meta[tag] = {
            "p_trophies": p.get("trophies", 0) or 0,
            "p_highest": p.get("highestTrophies", 0) or 0,
            "p_rankedElo": p.get("rankedElo", 0) or 0,
            "p_highestRankedElo": p.get("highestAllTimeRankedElo", 0) or 0,
            "p_expLevel": p.get("expLevel", 0) or 0,
            "p_totalPrestige": p.get("totalPrestigeLevel", 0) or 0,
            "p_v3v3": p.get("3vs3Victories", 0) or 0,
            "p_vSolo": p.get("soloVictories", 0) or 0,
            "p_vDuo": p.get("duoVictories", 0) or 0,
        }
        for b in p.get("brawlers", []):
            brawler_meta[(tag, b["name"])] = {
                "tr": b.get("trophies", 0) or 0,
                "highest": b.get("highestTrophies", 0) or 0,
                "prestige": b.get("prestigeLevel", 0) or 0,
                "streak": b.get("currentWinStreak", 0) or 0,
                "maxstreak": b.get("maxWinStreak", 0) or 0,
                "hc": 1 if b.get("hyperCharges") else 0,
            }
    print(f"  {len(player_meta)} players, {len(brawler_meta)} brawler entries")

    # 2. 試合データ load + ピック/勝率 集計 (グローバル)
    print("=== loading battles + computing global brawler stats ===")
    rows = con.execute(
        "SELECT tag, battle_time, mode, map, brawler, rank, raw_json FROM battles "
        "WHERE mode='trioShowdown' ORDER BY tag, battle_time"
    ).fetchall()

    # グローバル ピック数 / 勝率
    pick_count = Counter()
    top2_count = Counter()
    rank_sum = defaultdict(int)
    rank_n = defaultdict(int)
    for r in rows:
        br = r["brawler"] or ""
        if not br: continue
        pick_count[br] += 1
        if r["rank"] and r["rank"] <= 2:
            top2_count[br] += 1
        if r["rank"]:
            rank_sum[br] += r["rank"]
            rank_n[br] += 1
    total_picks = sum(pick_count.values())
    br_global = {}
    for br, n in pick_count.items():
        br_global[br] = {
            "pickrate": n / total_picks,
            "winrate": top2_count[br] / n if n else 0,
            "avgrank": rank_sum[br] / rank_n[br] if rank_n[br] else 0,
            "picks": n,
        }
    print(f"  global pickrate computed for {len(br_global)} brawlers")
    # 上位5
    top_picks = sorted(br_global.items(), key=lambda x: -x[1]["picks"])[:5]
    print(f"  top picks: {[(b, d['picks']) for b, d in top_picks]}")

    # 3. 試合ごとの特徴抽出
    print("=== extracting per-battle features ===")
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
        if len(teams) != 4 or not all(len(t_) == 3 for t_ in teams):
            continue
        my_idx = None
        for i, team in enumerate(teams):
            if any(p.get("tag") == r["tag"] for p in team):
                my_idx = i; break
        if my_idx is None: continue
        my_team = teams[my_idx]
        enemy_teams = [t_ for i, t_ in enumerate(teams) if i != my_idx]
        team_tr = [(p.get("brawler") or {}).get("trophies", 0) or 0 for p in my_team]
        enemy_tr = []
        for et in enemy_teams:
            for p in et:
                enemy_tr.append((p.get("brawler") or {}).get("trophies", 0) or 0)
        match_tr = team_tr + enemy_tr
        by_tag[r["tag"]].append({
            "time": t,
            "duration": battle.get("duration", 0) or 0,
            "brawler": r["brawler"] or "",
            "rank": r["rank"] or 0,
            "map": r["map"] or "",
            "team_tr": team_tr,
            "enemy_tr": enemy_tr,
            "match_tr": match_tr,
        })

    # 4. enriched samples 構築 (gap算出 + 全特徴量)
    enriched = []
    for tag, battles in by_tag.items():
        battles.sort(key=lambda x: x["time"])
        pm = player_meta.get(tag)
        if not pm: continue
        rolling_ranks = []  # for recent5
        for i, b in enumerate(battles):
            if i > 0:
                prev = battles[i-1]
                gap = (b["time"] - prev["time"]).total_seconds() - b["duration"]
                if not (0 <= gap <= 1800): gap = None
            else:
                gap = None
            bmeta = brawler_meta.get((tag, b["brawler"]))
            if bmeta is None: bmeta = {"tr": 0, "highest": 0, "prestige": 0, "streak": 0, "maxstreak": 0, "hc": 0}
            brg = br_global.get(b["brawler"], {"pickrate": 0, "winrate": 0, "avgrank": 0, "picks": 0})
            r5 = rolling_ranks[-5:] if len(rolling_ranks) >= 3 else None
            sample = {
                "tag": tag,
                "time": b["time"],
                "gap_next": None,  # 次の試合との gap (battles[i+1] - battles[i].time - battles[i+1].duration)
                "gap_prev": gap,
                "rank": b["rank"],
                "top2": 1 if b["rank"] and b["rank"] <= 2 else 0,
                "duration": b["duration"],
                "brawler": b["brawler"],
                "map": b["map"],
                # チーム指標
                "team_avg_tr": statistics.mean(b["team_tr"]) if b["team_tr"] else 0,
                "team_max_tr": max(b["team_tr"]) if b["team_tr"] else 0,
                "team_min_tr": min(b["team_tr"]) if b["team_tr"] else 0,
                "team_var_tr": statistics.variance(b["team_tr"]) if len(b["team_tr"]) > 1 else 0,
                "team_spread": (max(b["team_tr"]) - min(b["team_tr"])) if b["team_tr"] else 0,
                # 試合全体指標
                "match_avg_tr": statistics.mean(b["match_tr"]) if b["match_tr"] else 0,
                "match_max_tr": max(b["match_tr"]) if b["match_tr"] else 0,
                "match_min_tr": min(b["match_tr"]) if b["match_tr"] else 0,
                "match_var_tr": statistics.variance(b["match_tr"]) if len(b["match_tr"]) > 1 else 0,
                # 敵指標
                "enemy_avg_tr": statistics.mean(b["enemy_tr"]) if b["enemy_tr"] else 0,
                "enemy_max_tr": max(b["enemy_tr"]) if b["enemy_tr"] else 0,
                "enemy_min_tr": min(b["enemy_tr"]) if b["enemy_tr"] else 0,
                # ブロウラー指標
                "my_br_tr": bmeta["tr"],
                "my_br_highest": bmeta["highest"],
                "my_br_diff": bmeta["highest"] - bmeta["tr"],
                "my_br_prestige": bmeta["prestige"],
                "my_br_streak": bmeta["streak"],
                "my_br_maxstreak": bmeta["maxstreak"],
                "my_br_hc": bmeta["hc"],
                "my_br_pickrate": brg["pickrate"],
                "my_br_winrate": brg["winrate"],
                "my_br_avgrank_global": brg["avgrank"],
                # プレイヤー指標
                **pm,
                # 時間指標
                "hour": b["time"].hour,
                "weekday": b["time"].weekday(),
                "recent5_avg_rank": statistics.mean(r5) if r5 else None,
                "recent5_top2_rate": sum(1 for r in r5 if r <= 2) / len(r5) if r5 else None,
            }
            enriched.append(sample)
            if b["rank"]: rolling_ranks.append(b["rank"])

    # gap_next を埋める
    by_tag_e = defaultdict(list)
    for e in enriched:
        by_tag_e[e["tag"]].append(e)
    for tag, samples in by_tag_e.items():
        samples.sort(key=lambda x: x["time"])
        for i in range(len(samples) - 1):
            cur = samples[i]; nxt = samples[i+1]
            g = (nxt["time"] - cur["time"]).total_seconds() - nxt["duration"]
            if 0 <= g <= 1800: cur["gap_next"] = g

    # 有効サンプル (gap_next ありの試合 = 次の gap が観測できる試合)
    samples_g = [e for e in enriched if e["gap_next"] is not None]
    print(f"  enriched: total {len(enriched)}, with gap_next: {len(samples_g)}")

    # === 出力1: 全因子 vs gap_next ===
    print("\n" + "="*80)
    print(f"=== 全因子 × gap_next (次試合とのマッチ間隔) === N={len(samples_g)}")
    print("="*80)
    targets = [
        # チーム
        ("team_avg_tr", "★チーム平均トロ"),
        ("team_max_tr", "★チーム最高トロ"),
        ("team_min_tr", "チーム最低トロ"),
        ("team_var_tr", "チーム内分散"),
        ("team_spread", "チーム内spread"),
        # 試合
        ("match_avg_tr", "★試合9人 平均トロ"),
        ("match_max_tr", "試合9人 最高トロ"),
        ("match_min_tr", "試合9人 最低トロ"),
        ("match_var_tr", "試合9人 分散"),
        # 敵
        ("enemy_avg_tr", "敵6人平均"),
        ("enemy_max_tr", "敵6人最高"),
        ("enemy_min_tr", "敵6人最低"),
        # ブロウラー
        ("my_br_tr", "自ブロウラー現トロ"),
        ("my_br_highest", "自ブロウラー最高トロ"),
        ("my_br_diff", "(highest-current) 乖離"),
        ("my_br_prestige", "prestige"),
        ("my_br_streak", "現連勝"),
        ("my_br_maxstreak", "最大連勝"),
        ("my_br_hc", "HC装備(0/1)"),
        ("my_br_pickrate", "★キャラ使用率(DB内)"),
        ("my_br_winrate", "★キャラ勝率(DB内)"),
        ("my_br_avgrank_global", "キャラ平均順位(DB内)"),
        # プレイヤー
        ("p_trophies", "★総合トロ"),
        ("p_highest", "アカウント最高トロ"),
        ("p_rankedElo", "★現ガチElo"),
        ("p_highestRankedElo", "★生涯最高ガチElo"),
        ("p_expLevel", "経験値レベル"),
        ("p_totalPrestige", "総プレスティージ"),
        ("p_v3v3", "3v3勝利数"),
        ("p_vSolo", "ソロ勝利数"),
        ("p_vDuo", "デュオ勝利数"),
        # 時間
        ("duration", "試合時間"),
        ("hour", "時刻"),
    ]
    y_gap = [s["gap_next"] for s in samples_g]
    print(f"  {'指標':<35} {'rho':>7} {'sig':<5} {'N'}")
    for k, lab in targets:
        try:
            x = [s[k] for s in samples_g]
            rho, n = spearman(x, y_gap)
            if rho is None: continue
            print(f"  {lab:<33} {rho:>+6.3f}  {sig(rho):<5} {n}")
        except Exception as e:
            print(f"  {lab}: ERROR {e}")

    # === 出力2: 全因子 vs rank (試合結果) ===
    print("\n" + "="*80)
    print(f"=== 全因子 × rank (試合内順位、 低いほど強) === N={sum(1 for e in enriched if e['rank'])}")
    print("="*80)
    samples_r = [e for e in enriched if e["rank"]]
    y_rank = [s["rank"] for s in samples_r]
    print(f"  {'指標':<35} {'rho':>7} {'sig':<5} {'N'}")
    for k, lab in targets:
        try:
            x = [s[k] for s in samples_r]
            rho, n = spearman(x, y_rank)
            if rho is None: continue
            print(f"  {lab:<33} {rho:>+6.3f}  {sig(rho):<5} {n}")
        except Exception:
            pass

    # === 出力3: 全因子 vs top2 ===
    print("\n" + "="*80)
    print(f"=== 全因子 × top2 (1か2位 = 1、 それ以外 = 0) === N={len(samples_r)}")
    print("="*80)
    y_top2 = [s["top2"] for s in samples_r]
    print(f"  {'指標':<35} {'rho':>7} {'sig':<5} {'N'}")
    for k, lab in targets:
        try:
            x = [s[k] for s in samples_r]
            rho, n = spearman(x, y_top2)
            if rho is None: continue
            print(f"  {lab:<33} {rho:>+6.3f}  {sig(rho):<5} {n}")
        except Exception:
            pass

    # === 出力4: チーム平均トロ 帯別 gap中央値 ===
    print("\n" + "="*80)
    print("=== チーム平均トロ 帯別 × gap中央値 + top2率 ===")
    print("="*80)
    bands = [(0, 499), (500, 999), (1000, 1499), (1500, 1999), (2000, 2499),
             (2500, 2999), (3000, 3499), (3500, 9999)]
    print(f"  {'team_avg':<14} {'N':>5} {'gap_med':>8} {'enemy_avg':>10} {'top2率':>8} {'avg_rank':>8}")
    for lo, hi in bands:
        sub = [s for s in samples_g if lo <= s["team_avg_tr"] <= hi]
        if len(sub) < 30: continue
        gm = statistics.median([s["gap_next"] for s in sub])
        em = statistics.median([s["enemy_avg_tr"] for s in sub])
        t2 = sum(1 for s in sub if s["top2"]) / len(sub)
        ar = statistics.mean([s["rank"] for s in sub if s["rank"]])
        print(f"  {lo:>5}-{hi:<5}   {len(sub):>5} {gm:>7.0f}s {em:>9.0f} {t2:>7.1%} {ar:>7.2f}")

    # === 出力5: チーム最高トロ 帯別 ===
    print("\n" + "="*80)
    print("=== チーム最高トロ 帯別 × gap + top2率 ===")
    print("="*80)
    print(f"  {'team_max':<14} {'N':>5} {'gap_med':>8} {'enemy_max':>10} {'top2率':>8} {'avg_rank':>8}")
    for lo, hi in bands:
        sub = [s for s in samples_g if lo <= s["team_max_tr"] <= hi]
        if len(sub) < 30: continue
        gm = statistics.median([s["gap_next"] for s in sub])
        em = statistics.median([s["enemy_max_tr"] for s in sub])
        t2 = sum(1 for s in sub if s["top2"]) / len(sub)
        ar = statistics.mean([s["rank"] for s in sub if s["rank"]])
        print(f"  {lo:>5}-{hi:<5}   {len(sub):>5} {gm:>7.0f}s {em:>9.0f} {t2:>7.1%} {ar:>7.2f}")

    # === 出力6: 試合平均トロ 帯別 ===
    print("\n" + "="*80)
    print("=== 試合9人 平均トロ 帯別 × gap + top2率 ===")
    print("="*80)
    print(f"  {'match_avg':<14} {'N':>5} {'gap_med':>8} {'top2率':>8} {'avg_rank':>8} {'mean_dur':>9}")
    for lo, hi in bands:
        sub = [s for s in samples_g if lo <= s["match_avg_tr"] <= hi]
        if len(sub) < 30: continue
        gm = statistics.median([s["gap_next"] for s in sub])
        t2 = sum(1 for s in sub if s["top2"]) / len(sub)
        ar = statistics.mean([s["rank"] for s in sub if s["rank"]])
        dm = statistics.mean([s["duration"] for s in sub])
        print(f"  {lo:>5}-{hi:<5}   {len(sub):>5} {gm:>7.0f}s {t2:>7.1%} {ar:>7.2f} {dm:>8.0f}s")

    # === 出力7: 自ブロウラー highest 帯別 ===
    print("\n" + "="*80)
    print("=== 自ブロウラー highest 帯別 ===")
    print("="*80)
    print(f"  {'br_highest':<14} {'N':>5} {'gap_med':>8} {'top2率':>8} {'team_avg':>10} {'enemy_avg':>10}")
    for lo, hi in bands:
        sub = [s for s in samples_g if lo <= s["my_br_highest"] <= hi]
        if len(sub) < 30: continue
        gm = statistics.median([s["gap_next"] for s in sub])
        t2 = sum(1 for s in sub if s["top2"]) / len(sub)
        ta = statistics.mean([s["team_avg_tr"] for s in sub])
        ea = statistics.mean([s["enemy_avg_tr"] for s in sub])
        print(f"  {lo:>5}-{hi:<5}   {len(sub):>5} {gm:>7.0f}s {t2:>7.1%} {ta:>9.0f} {ea:>9.0f}")

    # === 出力8: キャラ使用率 (pickrate) 帯別 ===
    print("\n" + "="*80)
    print("=== キャラ使用率 (DB内ピック比率) 帯別 ===")
    print("="*80)
    print("仮説: 使用率高 (= 流行キャラ) ほど対戦相手も持ってる → matchmaking 速い? 遅い?")
    pr_bands = [(0, 0.005), (0.005, 0.01), (0.01, 0.02), (0.02, 0.04), (0.04, 0.10), (0.10, 1.0)]
    print(f"  {'pickrate':<14} {'N':>5} {'gap_med':>8} {'top2率':>8} {'br_highest_med':>14}")
    for lo, hi in pr_bands:
        sub = [s for s in samples_g if lo <= s["my_br_pickrate"] < hi]
        if len(sub) < 30: continue
        gm = statistics.median([s["gap_next"] for s in sub])
        t2 = sum(1 for s in sub if s["top2"]) / len(sub)
        hm = statistics.median([s["my_br_highest"] for s in sub])
        print(f"  {lo:.3f}-{hi:.3f}  {len(sub):>5} {gm:>7.0f}s {t2:>7.1%} {hm:>13.0f}")

    # === 出力9: キャラ勝率 (winrate) 帯別 ===
    print("\n" + "="*80)
    print("=== キャラ勝率 (DB内 top2率) 帯別 ===")
    print("="*80)
    wr_bands = [(0, 0.3), (0.3, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 1.0)]
    print(f"  {'winrate':<14} {'N':>5} {'gap_med':>8} {'top2率':>8} {'br_highest_med':>14}")
    for lo, hi in wr_bands:
        sub = [s for s in samples_g if lo <= s["my_br_winrate"] < hi]
        if len(sub) < 30: continue
        gm = statistics.median([s["gap_next"] for s in sub])
        t2 = sum(1 for s in sub if s["top2"]) / len(sub)
        hm = statistics.median([s["my_br_highest"] for s in sub])
        print(f"  {lo:.2f}-{hi:.2f}   {len(sub):>5} {gm:>7.0f}s {t2:>7.1%} {hm:>13.0f}")

    # === 出力10: ガチElo 帯別 (アカウント単位) ===
    print("\n" + "="*80)
    print("=== ガチバトル現Elo 帯別 ===")
    print("="*80)
    elo_bands = [(0, 99), (100, 499), (500, 799), (800, 999), (1000, 1199), (1200, 9999)]
    print(f"  {'rankedElo':<14} {'N':>5} {'gap_med':>8} {'top2率':>8} {'br_highest_med':>14}")
    for lo, hi in elo_bands:
        sub = [s for s in samples_g if lo <= s["p_rankedElo"] <= hi]
        if len(sub) < 30: continue
        gm = statistics.median([s["gap_next"] for s in sub])
        t2 = sum(1 for s in sub if s["top2"]) / len(sub)
        hm = statistics.median([s["my_br_highest"] for s in sub])
        print(f"  {lo:>5}-{hi:<5}   {len(sub):>5} {gm:>7.0f}s {t2:>7.1%} {hm:>13.0f}")

    # === 出力11: 生涯最高ガチElo ===
    print("\n" + "="*80)
    print("=== 生涯最高ガチElo 帯別 ===")
    print("="*80)
    print(f"  {'highElo':<14} {'N':>5} {'gap_med':>8} {'top2率':>8}")
    for lo, hi in elo_bands:
        sub = [s for s in samples_g if lo <= s["p_highestRankedElo"] <= hi]
        if len(sub) < 30: continue
        gm = statistics.median([s["gap_next"] for s in sub])
        t2 = sum(1 for s in sub if s["top2"]) / len(sub)
        print(f"  {lo:>5}-{hi:<5}   {len(sub):>5} {gm:>7.0f}s {t2:>7.1%}")

    # === 出力12: 総合トロ 帯別 ===
    print("\n" + "="*80)
    print("=== アカウント総合トロ 帯別 ===")
    print("="*80)
    tt_bands = [(0, 19999), (20000, 49999), (50000, 89999), (90000, 119999), (120000, 9999999)]
    print(f"  {'total_tr':<14} {'N':>5} {'gap_med':>8} {'top2率':>8}")
    for lo, hi in tt_bands:
        sub = [s for s in samples_g if lo <= s["p_trophies"] <= hi]
        if len(sub) < 30: continue
        gm = statistics.median([s["gap_next"] for s in sub])
        t2 = sum(1 for s in sub if s["top2"]) / len(sub)
        print(f"  {lo:>7}-{hi:<7}{len(sub):>5} {gm:>7.0f}s {t2:>7.1%}")

    # === 出力13: 時刻別 gap ===
    print("\n" + "="*80)
    print("=== 時刻 (UTC hour) 別 gap ===")
    print("="*80)
    print(f"  {'hour':>4} {'N':>5} {'gap_med':>8} {'top2率':>8}")
    for h in range(24):
        sub = [s for s in samples_g if s["hour"] == h]
        if len(sub) < 30: continue
        gm = statistics.median([s["gap_next"] for s in sub])
        t2 = sum(1 for s in sub if s["top2"]) / len(sub)
        print(f"  {h:>4} {len(sub):>5} {gm:>7.0f}s {t2:>7.1%}")

    # === 出力14: 曜日別 ===
    print("\n" + "="*80)
    print("=== 曜日別 (0=月, 6=日) ===")
    print("="*80)
    for w in range(7):
        sub = [s for s in samples_g if s["weekday"] == w]
        if not sub: continue
        gm = statistics.median([s["gap_next"] for s in sub])
        t2 = sum(1 for s in sub if s["top2"]) / len(sub)
        print(f"  weekday={w}: N={len(sub):>5}  gap_med={gm:>5.0f}s  top2={t2:.1%}")

    # === 出力15: 試合時間 (duration) と gap 関係 ===
    print("\n" + "="*80)
    print("=== 試合時間別 × 次gap (長い試合の後は遅い? 短い試合の後は早い?) ===")
    print("="*80)
    dur_bands = [(0, 60), (60, 120), (120, 180), (180, 240), (240, 300), (300, 9999)]
    print(f"  {'duration':<14} {'N':>5} {'gap_med':>8} {'top2率':>8}")
    for lo, hi in dur_bands:
        sub = [s for s in samples_g if lo <= s["duration"] < hi]
        if len(sub) < 30: continue
        gm = statistics.median([s["gap_next"] for s in sub])
        t2 = sum(1 for s in sub if s["top2"]) / len(sub)
        print(f"  {lo:>5}-{hi:<5}s  {len(sub):>5} {gm:>7.0f}s {t2:>7.1%}")

    # === 出力16: 直近5戦結果と次gap (連勝/連敗 補正) ===
    print("\n" + "="*80)
    print("=== 直近5戦 平均順位 × 次gap (再確認 + top2率) ===")
    print("="*80)
    valid5 = [s for s in samples_g if s["recent5_avg_rank"] is not None]
    rk_bands = [(1.0, 1.5), (1.5, 2.0), (2.0, 2.5), (2.5, 3.0), (3.0, 3.5), (3.5, 4.0)]
    print(f"  {'recent5_avg':<14} {'N':>5} {'gap_med':>8} {'this_top2':>10}")
    for lo, hi in rk_bands:
        sub = [s for s in valid5 if lo <= s["recent5_avg_rank"] < hi]
        if len(sub) < 30: continue
        gm = statistics.median([s["gap_next"] for s in sub])
        t2 = sum(1 for s in sub if s["top2"]) / len(sub)
        print(f"  {lo:.1f}-{hi:.1f}     {len(sub):>5} {gm:>7.0f}s {t2:>9.1%}")

    # === 出力17: マップ×ブロウラー 上位ピック - パフォーマンス vs gap ===
    print("\n" + "="*80)
    print("=== マップ別 自分が使ったブロウラー TOP3 (60戦以上) ===")
    print("="*80)
    by_map_br = defaultdict(list)
    for s in samples_g:
        by_map_br[(s["map"], s["brawler"])].append(s)
    map_groups = defaultdict(list)
    for (mp, br), arr in by_map_br.items():
        if len(arr) >= 60:
            t2 = sum(1 for x in arr if x["top2"]) / len(arr)
            gm = statistics.median([x["gap_next"] for x in arr])
            map_groups[mp].append((br, len(arr), gm, t2))
    for mp in sorted(map_groups.keys()):
        items = sorted(map_groups[mp], key=lambda x: -x[1])[:5]
        print(f"  [{mp[:24]:<24}]")
        for br, n, gm, t2 in items:
            print(f"     {br:<15} N={n:>4}  gap_med={gm:>5.0f}s  top2={t2:.1%}")

    # === 出力18: セッション中断検出 (24h以上空いた後の最初の試合) ===
    print("\n" + "="*80)
    print("=== セッション再開直後の gap (24h以上空いた後の最初試合) ===")
    print("="*80)
    session_first_gaps = []
    cont_gaps = []
    for tag, battles in by_tag.items():
        battles.sort(key=lambda x: x["time"])
        for i in range(1, len(battles)):
            elapsed = (battles[i]["time"] - battles[i-1]["time"]).total_seconds()
            gap = elapsed - battles[i]["duration"]
            if not (0 <= gap <= 1800): continue
            if elapsed > 24*3600:
                session_first_gaps.append(gap)
            else:
                cont_gaps.append(gap)
    if session_first_gaps:
        print(f"  セッション再開直後 (>24h空白): N={len(session_first_gaps)}  gap_med={statistics.median(session_first_gaps):.0f}s")
    if cont_gaps:
        print(f"  通常 (連続プレイ中): N={len(cont_gaps)}  gap_med={statistics.median(cont_gaps):.0f}s")

    # === 出力19: 同一ブロウラー連投 vs 切替 ===
    print("\n" + "="*80)
    print("=== 同一ブロウラー連投 vs 切替 ===")
    print("="*80)
    same_gaps = []
    diff_gaps = []
    for tag, battles in by_tag.items():
        battles.sort(key=lambda x: x["time"])
        for i in range(1, len(battles)):
            g = (battles[i]["time"] - battles[i-1]["time"]).total_seconds() - battles[i]["duration"]
            if not (0 <= g <= 1800): continue
            if battles[i]["brawler"] == battles[i-1]["brawler"]:
                same_gaps.append(g)
            else:
                diff_gaps.append(g)
    if same_gaps:
        print(f"  連投 (同ブロウラー): N={len(same_gaps)}  gap_med={statistics.median(same_gaps):.0f}s")
    if diff_gaps:
        print(f"  切替 (別ブロウラー): N={len(diff_gaps)}  gap_med={statistics.median(diff_gaps):.0f}s")
    if same_gaps and diff_gaps:
        print(f"  差: {statistics.median(same_gaps) - statistics.median(diff_gaps):+.0f}s")

    # === 出力20: 強キャラ vs 弱キャラ (winrate 高低) ===
    print("\n" + "="*80)
    print("=== 強キャラ (winrate 60+) vs 弱キャラ (40-) 使用時の gap・rank ===")
    print("="*80)
    strong = [s for s in samples_g if s["my_br_winrate"] >= 0.6]
    weak = [s for s in samples_g if s["my_br_winrate"] <= 0.4]
    if strong:
        print(f"  強キャラ winrate>=60%: N={len(strong)}")
        print(f"    gap_med={statistics.median([s['gap_next'] for s in strong]):.0f}s")
        print(f"    top2率={sum(1 for s in strong if s['top2'])/len(strong):.1%}")
        print(f"    avg_rank={statistics.mean([s['rank'] for s in strong if s['rank']]):.2f}")
    if weak:
        print(f"  弱キャラ winrate<=40%: N={len(weak)}")
        print(f"    gap_med={statistics.median([s['gap_next'] for s in weak]):.0f}s")
        print(f"    top2率={sum(1 for s in weak if s['top2'])/len(weak):.1%}")
        print(f"    avg_rank={statistics.mean([s['rank'] for s in weak if s['rank']]):.2f}")

    print("\n=== END ===")


if __name__ == "__main__":
    main()
