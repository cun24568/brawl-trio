"""TrueSkill 実走 + 連敗補正検出.

J. TrueSkill: トリオの 3チーム×3人 × 順位 で μ/σ を更新。
   各試合 → env.rate([team1, team2, team3], ranks=[r1, r2, r3])
   観測: ウォッチリスト 37人のうち、 試合に1度でも出てきた全プレイヤー (敵含む)
   最終的に μ ランキングを出す。 σ (収束度) も表示。

K. 連敗補正: J案結果と組み合わせて、 連敗中 (直近5戦平均順位>=3.0) のプレイヤーは
   gap が短くなるか?
"""
import json
import sqlite3
import statistics
from collections import defaultdict
from datetime import datetime, timezone

DB = "/home/soya/brawl-trio/data/users.db"


def parse_bt(bt):
    try:
        return datetime.strptime(bt[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def main():
    try:
        import trueskill
    except ImportError:
        print("ERROR: trueskill ライブラリが入ってない。 pip install trueskill")
        return
    env = trueskill.TrueSkill(draw_probability=0.0)  # トリオは引き分け基本なし

    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT tag, battle_time, brawler, rank, raw_json FROM battles "
        "WHERE mode='trioShowdown' ORDER BY battle_time"
    ).fetchall()

    # 試合を「試合ID (=battle_time + 自タグ抜き) で重複排除」 すべきだが、
    # 同一試合 でも自タグごとに行が立ってる可能性あり (複数 watchlist が同じ試合に出た場合)
    # → 試合 unique key: (battle_time, 自分以外のtag set) で代用
    seen_battles = set()
    matches = []
    for tag, bt, brawler, rank, raw in rows:
        try:
            r = json.loads(raw)
        except Exception:
            continue
        battle = r.get("battle") or {}
        teams = battle.get("teams") or []
        if len(teams) != 4 or not all(len(t) == 3 for t in teams):
            continue
        # 順位を取り出す: 各チームに rank があれば使う、 なければ battle.rank
        # 公式APIは個人rankしか持たないので、 「自分のチームの rank = 自分のrank」 と仮定
        # 他チームの順位は不明 → showdown は自分の rank=1/2/3/4 のみ
        # ★ トリオの場合 4位がいない (3チーム) → rank=1,2,3 の3チーム
        # 実際の形: rank=1 or 2 or 3 or 4 (4位=最初に全滅、 1位=最後生き残り)
        # → rank=4 のチームを排除して 3チーム順位とする
        all_tags = sorted([p.get("tag", "") for team in teams for p in team])
        key = (bt, tuple(all_tags))
        if key in seen_battles:
            continue
        seen_battles.add(key)
        # 各チーム → set of tags
        team_tags = [[p.get("tag", "") for p in team] for team in teams]
        # 自分のrank
        my_rank = rank or 0
        if my_rank == 0:
            continue
        my_team_idx = None
        for i, team in enumerate(teams):
            if any(p.get("tag") == tag for p in team):
                my_team_idx = i
                break
        if my_team_idx is None:
            continue
        # 他チームの順位は不明。 我々のrankだけ確定。
        # 簡略化: 「自チーム = rank(=my_rank), 他チーム は max(1, my_rank±1) 程度の順位」 ← 推定困難
        # → 他チームの順位を「2位 if my=1 / 1位 if my>=2」 と仮定すると粗雑
        # 代替案: 自分の rank だけ確定なので、 「自分のチームと最強チーム (rank=1) のペア」 だけ更新
        # ★ 実装: 自分のrank=1 なら他チームは [rank=2, rank=3] と仮定 (順序不明だが対等扱い)
        # ★ より正確には 4チーム x 3人 を 4ランクで更新したいが、 解像度落とす方が安全
        # 暫定: my_rank だけ確定で「3チーム順位」 のうち自分の位置を埋める
        # 他2チームは draw 扱いで rate
        ranks_assumed = [0, 0, 0]  # team 0/1/2/3 の rank
        # 自分のチーム = my_rank
        # 他チームは my_rank 以外を均等に
        other_ranks = [r for r in [1, 2, 3, 4] if r != my_rank][:3]
        ranks_assumed = list(other_ranks)
        ranks_assumed.insert(my_team_idx, my_rank)
        # 4位チーム = 戦死済みなので 3チーム + 1 → 上位3チームだけ更新する方が良いかも
        # 単純化: 全4チームをそのまま env.rate に流す
        matches.append({
            "battle_time": bt,
            "teams": team_tags,
            "ranks": ranks_assumed,
        })

    print(f"unique matches: {len(matches)}")

    # TrueSkill 初期化
    ratings = defaultdict(lambda: env.create_rating())
    # 試合を時系列順に処理
    matches.sort(key=lambda m: m["battle_time"])
    for m in matches:
        # チームに 1人もタグがない場合スキップ
        if any(not any(t for t in team) for team in m["teams"]):
            continue
        teams_ratings = [[ratings[t] for t in team if t] for team in m["teams"]]
        if not all(teams_ratings):
            continue
        try:
            new_teams = env.rate(teams_ratings, ranks=m["ranks"])
        except Exception:
            continue
        for team_in, team_out in zip(m["teams"], new_teams):
            i = 0
            for tag in team_in:
                if not tag: continue
                if i < len(team_out):
                    ratings[tag] = team_out[i]
                    i += 1

    print(f"prayers rated: {len(ratings)}")

    # μ 上位ランキング (試合数 30+ のみ)
    appearances = defaultdict(int)
    for m in matches:
        for team in m["teams"]:
            for t in team:
                if t: appearances[t] += 1
    qualified = [(t, ratings[t].mu, ratings[t].sigma, appearances[t]) for t in ratings if appearances[t] >= 30]
    qualified.sort(key=lambda x: -x[1])
    print(f"\nqualified players (>=30 matches): {len(qualified)}")
    print(f"\n=== TrueSkill TOP 50 (μ - 3σ で保守的に評価) ===")
    print(f"{'rank':<5} {'tag':<15} {'μ':<7} {'σ':<6} {'μ-3σ':<7} {'N':<6} {'name'}")
    # 名前取得
    names = {}
    for r in con.execute("SELECT tag, name FROM watchlist WHERE name IS NOT NULL"):
        names[r[0]] = r[1]
    # 敵プレイヤー名は raw_json から拾う必要あり (省略、 watchlist 内のみ表示)
    qualified_sorted = sorted(qualified, key=lambda x: -(x[1] - 3*x[2]))
    for i, (tag, mu, sig, n) in enumerate(qualified_sorted[:50]):
        nm = names.get(tag, "")
        print(f"{i+1:<5} {tag:<15} {mu:>6.2f} {sig:>5.2f} {mu - 3*sig:>6.2f} {n:>5} {nm}")

    # =============================================================
    print("\n" + "="*72)
    print("=== K. 連敗補正の検出 (直近5戦平均順位 × 次gap) ===")
    print("="*72)
    # 各 (tag, brawler) で時系列を見る
    by_tag = defaultdict(list)
    for tag, bt, brawler, rank, raw in rows:
        try:
            r = json.loads(raw)
        except Exception:
            continue
        battle = r.get("battle") or {}
        duration = battle.get("duration", 0) or 0
        t = parse_bt(bt)
        if t is None: continue
        by_tag[tag].append({"time": t, "rank": rank or 0, "brawler": brawler, "duration": duration})

    # 各試合 i に対し、 直近5戦の平均順位 (i-5..i-1)、 と 次の gap (i→i+1)
    samples = []
    for tag, battles in by_tag.items():
        battles.sort(key=lambda x: x["time"])
        for i in range(5, len(battles) - 1):
            recent = battles[i-5:i]
            recent_ranks = [b["rank"] for b in recent if b["rank"] > 0]
            if len(recent_ranks) < 3: continue
            avg_recent = statistics.mean(recent_ranks)
            # next gap
            nxt = battles[i+1]
            gap = (nxt["time"] - battles[i]["time"]).total_seconds() - nxt["duration"]
            if not (0 <= gap <= 1800): continue
            samples.append({"avg_recent_rank": avg_recent, "next_gap": gap})
    print(f"  N={len(samples)}")
    # 帯別
    bands = [(1.0, 1.5), (1.5, 2.0), (2.0, 2.5), (2.5, 3.0), (3.0, 3.5), (3.5, 4.0)]
    for lo, hi in bands:
        sub = [s["next_gap"] for s in samples if lo <= s["avg_recent_rank"] < hi]
        if len(sub) < 30: continue
        med = statistics.median(sub)
        n = len(sub)
        print(f"  直近5戦平均順位 {lo:.1f}-{hi:.1f}: N={n:>5}  next_gap_med={med:>5.0f}s")

    # Spearman 相関
    xs = [s["avg_recent_rank"] for s in samples]
    ys = [s["next_gap"] for s in samples]
    # 簡易 spearman
    def spearman(x, y):
        n = len(x)
        if n < 5: return None
        rx = sorted(range(n), key=lambda i: x[i])
        ry = sorted(range(n), key=lambda i: y[i])
        rank_x = [0]*n; rank_y = [0]*n
        for i, idx in enumerate(rx): rank_x[idx] = i
        for i, idx in enumerate(ry): rank_y[idx] = i
        mx = sum(rank_x)/n; my = sum(rank_y)/n
        cov = sum((rank_x[i]-mx)*(rank_y[i]-my) for i in range(n))
        vx = (sum((rank_x[i]-mx)**2 for i in range(n)))**0.5
        vy = (sum((rank_y[i]-my)**2 for i in range(n)))**0.5
        return cov/(vx*vy) if vx*vy > 0 else 0
    rho = spearman(xs, ys)
    print(f"  Spearman: 直近平均順位 vs next_gap = {rho:+.3f}")
    print(f"  解釈: 正なら 「平均順位悪い = gap長い」 (連敗者を待たせる)、 負なら 「連敗者は早くマッチさせる」")


if __name__ == "__main__":
    main()
