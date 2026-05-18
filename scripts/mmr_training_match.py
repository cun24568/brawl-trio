"""キャラ詳細画面 「練習試合」 (= type='friendly' AND n_players=1) の bot強さ分析.

仮説 (ユーザ提案): ブロウラー詳細画面から押せる練習試合のbot強さがMMRに連動するなら、
duration / 勝敗 / bot brawler選択 から MMR を逆推定できる。

公式APIの制約:
  - bot の trophies は -1 マスク
  - bot の brawler種類は見える (id/name)
  - duration, result, my_brawler は普通に取れる

分析項目:
  1. 練習試合の存在確認: type='friendly' AND teams_total=1
  2. duration の分布
  3. bot brawler の選択頻度 (誰が現れやすい?)
  4. プレイヤー別 (観察ベースMMR比較): bot 種類/duration が違う?
  5. mode 別 (gemGrab vs brawlBall vs trioShowdown)
"""
import json
import sqlite3
import statistics
from collections import defaultdict, Counter


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


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    # プレイヤー観察ベースMMR (再計算: 全モード ranked battles から)
    obs_per_player = defaultdict(list)
    profiles = {}
    for r in con.execute("SELECT tag, profile_json, name FROM watchlist WHERE profile_json IS NOT NULL"):
        try:
            p = json.loads(r["profile_json"])
        except Exception:
            continue
        profiles[r["tag"]] = {
            "name": p.get("name", "") or r["name"] or "",
            "highest": p.get("highestTrophies", 0) or 0,
            "rankedElo": p.get("rankedElo", 0) or 0,
            "highestRankedElo": p.get("highestAllTimeRankedElo", 0) or 0,
            "expLevel": p.get("expLevel", 0) or 0,
        }

    # 全 ranked 試合から観察ベースMMR
    for r in con.execute("SELECT tag, raw_json FROM battles WHERE mode='trioShowdown'"):
        try:
            raw = json.loads(r["raw_json"])
        except Exception:
            continue
        battle = raw.get("battle") or {}
        if battle.get("type", "") != "ranked":
            continue
        teams = battle.get("teams") or []
        others = []
        for team in teams:
            for p in team:
                if p.get("tag") != r["tag"]:
                    tr = (p.get("brawler") or {}).get("trophies", 0) or 0
                    if tr > 0:
                        others.append(tr)
        if len(others) >= 4:
            obs_per_player[r["tag"]].append(statistics.median(others))
    obs_mmr = {t: statistics.median(arr) for t, arr in obs_per_player.items() if len(arr) >= 30}
    print(f"obs_MMR 計算済プレイヤー: {len(obs_mmr)}")

    # 練習試合抽出 (type='friendly' AND 試合内合計1人)
    print()
    print("="*80)
    print("=== キャラ詳細画面 練習試合 検出 (type='friendly' AND 試合内人数=1) ===")
    print("="*80)
    training_battles = []
    for r in con.execute("SELECT tag, battle_time, mode, map, brawler, rank, raw_json FROM battles WHERE mode IS NOT NULL"):
        try:
            raw = json.loads(r["raw_json"])
        except Exception:
            continue
        battle = raw.get("battle") or {}
        ev = raw.get("event") or {}
        if battle.get("type", "") != "friendly":
            continue
        teams = battle.get("teams") or []
        players = battle.get("players") or []
        # 試合内合計人数
        n_total = sum(len(t) for t in teams) if teams else len(players)
        if n_total != 1:
            continue
        # teams があるなら自分のチーム情報 + 敵チーム (空) を確認
        # 注: teams=[[self]] (1チーム×1人) パターン or 自分以外 bot は別 dict ?
        training_battles.append({
            "tag": r["tag"],
            "battle_time": r["battle_time"],
            "mode": ev.get("mode", ""),
            "map": r["map"] or "",
            "brawler": r["brawler"] or "",
            "rank": r["rank"],
            "duration": battle.get("duration", 0) or 0,
            "result": battle.get("result", ""),
            "trophy_change": battle.get("trophyChange", 0) or 0,
            "starPlayer": (battle.get("starPlayer") or {}).get("tag", "") if battle.get("starPlayer") else "",
            "raw": raw,
        })

    print(f"  検出: {len(training_battles)}試合")
    if not training_battles:
        print("  該当試合なし。 マイページ登録ユーザの中にキャラ別練習試合をプレイした人がいない。")
        print("  → 自分 (主タグ #YQ8YY09R) の battlelog にキャラ別練習試合がない可能性、 もしくは別のtype判定が必要")
        return

    # モード別
    print("\n  モード別:")
    by_mode = Counter(tb["mode"] for tb in training_battles)
    for m, n in by_mode.most_common():
        print(f"    {m:<20} {n}")

    # プレイヤー別
    print("\n  プレイヤー別 (試合数 >= 1):")
    by_player = defaultdict(list)
    for tb in training_battles:
        by_player[tb["tag"]].append(tb)
    for tag, arr in sorted(by_player.items(), key=lambda x: -len(x[1])):
        nm = profiles.get(tag, {}).get("name", "?")
        mmr = obs_mmr.get(tag, None)
        dur_list = [t["duration"] for t in arr if t["duration"] > 0]
        dur_med = statistics.median(dur_list) if dur_list else 0
        results = Counter(t["result"] for t in arr)
        print(f"    [{nm[:18]:<18}] {tag} N={len(arr)}  obs_MMR={mmr!s:<7}  dur_med={dur_med:.0f}s  results={dict(results)}")

    # サンプル試合
    print("\n  サンプル試合詳細:")
    for tb in training_battles[:5]:
        print(f"    {tb['battle_time']} mode={tb['mode']} map={tb['map']} brawler={tb['brawler']} rank={tb['rank']} duration={tb['duration']}s result={tb['result']}")
        # raw_json から全プレイヤー
        battle = tb["raw"].get("battle") or {}
        teams = battle.get("teams") or []
        players = battle.get("players") or []
        print(f"      teams={teams}")
        print(f"      players={players}")

    # bot brawler 出現頻度 (training_battles の自分以外のプレイヤー位置にあるbotの brawler)
    print()
    print("="*80)
    print("=== 練習試合での bot brawler 出現頻度 ===")
    print("="*80)
    print("(別途分析: friendly で人数>1 の試合 = 友達練習試合に bot fill されてるパターン)")
    bot_fill_battles = []
    for r in con.execute("SELECT tag, battle_time, mode, brawler, rank, raw_json FROM battles WHERE mode IS NOT NULL"):
        try:
            raw = json.loads(r["raw_json"])
        except Exception:
            continue
        battle = raw.get("battle") or {}
        if battle.get("type", "") not in ("friendly", "challenge"):
            continue
        teams = battle.get("teams") or []
        players = battle.get("players") or []
        n_total = sum(len(t) for t in teams) if teams else len(players)
        if n_total == 1:
            # 純粋な1人練習試合 → 含める
            pass
        # bot 候補抽出: tag長さ < 6 or trophies==-1 のslot
        all_ps = [p for team in teams for p in team] + players
        bots = []
        for p in all_ps:
            tag = p.get("tag", "") or ""
            tr = (p.get("brawler") or {}).get("trophies", 0)
            if (not tag.startswith("#") or len(tag) < 7 or tr == -1) and p.get("tag") != r["tag"]:
                bots.append(p)
        if bots:
            bot_fill_battles.append({
                "tag": r["tag"], "btype": battle.get("type", ""),
                "mode": (raw.get("event") or {}).get("mode", ""),
                "n_total": n_total, "duration": battle.get("duration", 0) or 0,
                "result": battle.get("result", ""),
                "bots": bots, "brawler": r["brawler"], "rank": r["rank"],
            })

    print(f"  bot存在 friendly/challenge試合: {len(bot_fill_battles)}")
    if bot_fill_battles:
        # bot brawler 集計
        bot_brawler_count = Counter()
        for bf in bot_fill_battles:
            for b in bf["bots"]:
                bn = (b.get("brawler") or {}).get("name", "?")
                bot_brawler_count[bn] += 1
        print("\n  bot として出現した brawler (top10):")
        for n, c in bot_brawler_count.most_common(10):
            print(f"    {n:<15} {c}回")

    # duration を観察ベースMMRと相関 (友達練習+bot fill 含む)
    print()
    print("="*80)
    print("=== bot存在試合 duration vs 観察者 MMR ===")
    print("="*80)
    pairs = []
    for bf in bot_fill_battles:
        mmr = obs_mmr.get(bf["tag"])
        if mmr is None or not bf["duration"]: continue
        pairs.append((mmr, bf["duration"], bf))
    print(f"  pairs N={len(pairs)}")
    if len(pairs) >= 5:
        xs = [p[0] for p in pairs]; ys = [p[1] for p in pairs]
        rho, _ = spearman(xs, ys)
        print(f"  rho(obs_MMR, duration) = {rho:+.3f}")
        print(f"  → 正なら 「MMR高い人ほど練習試合が長引く (= bot強い)」 の傍証")
        # 帯別
        bands = [(0, 999), (1000, 1499), (1500, 1799), (1800, 9999)]
        for lo, hi in bands:
            sub = [p[1] for p in pairs if lo <= p[0] <= hi]
            if not sub: continue
            print(f"    obs_MMR {lo:>5}-{hi:<5}: N={len(sub):>3}  duration_med={statistics.median(sub):.0f}s")


if __name__ == "__main__":
    main()
