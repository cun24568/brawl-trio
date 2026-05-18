"""観察ベース MMR 推定: 「自分が遭遇した他プレイヤーの trophies 中央値」 が MMR の直接観測値.

検証ロジック:
  通常マッチで rho(自highest, 他者平均トロ) = +0.685 という極めて強い対称性が確認されたので、
  「観察者が経験した全試合の (敵+味方) brawler trophy 中央値の中央値」 = MMR推定値
  と仮定する。 既存指標 (rankedElo, highestTrophies, TrueSkill μ等) との相関を見て検証。

副次仮説 (bot関連):
  練習試合 (type='friendly') では他者トロ値が -1 マスクされてるので、 公式APIから bot強さは取れない。
  C案 (パケット解析) で friendly 試合の生 payload を解読すれば、 内部bot trophy値や AIパラメータが
  見える可能性あり。 これは別途プロジェクトで。
"""
import json
import sqlite3
import statistics
from collections import defaultdict


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

    # プロフィール
    profiles = {}
    for r in con.execute("SELECT tag, profile_json, name FROM watchlist WHERE profile_json IS NOT NULL"):
        try:
            p = json.loads(r["profile_json"])
        except Exception:
            continue
        profiles[r["tag"]] = {
            "name": p.get("name", "") or r["name"] or "",
            "trophies": p.get("trophies", 0) or 0,
            "highest": p.get("highestTrophies", 0) or 0,
            "rankedElo": p.get("rankedElo", 0) or 0,
            "highestRankedElo": p.get("highestAllTimeRankedElo", 0) or 0,
            "expLevel": p.get("expLevel", 0) or 0,
        }

    # 各プレイヤーごとに 経験した他者 trophies の中央値を計算
    observed_data = defaultdict(list)  # tag → list of "他者平均トロ"
    observed_max = defaultdict(list)
    observed_med = defaultdict(list)
    # ブロウラー別 (自分が使ったキャラごとに観察者MMRも違うはず)
    obs_per_brawler = defaultdict(list)

    rows = con.execute(
        "SELECT tag, brawler, raw_json FROM battles WHERE mode='trioShowdown'"
    ).fetchall()
    print(f"loading {len(rows)} battles...")
    for r in rows:
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
                    if tr > 0:  # マスク値 (-1) 除外
                        others.append(tr)
        if not others or len(others) < 4:
            continue
        observed_data[r["tag"]].append(statistics.mean(others))
        observed_max[r["tag"]].append(max(others))
        observed_med[r["tag"]].append(statistics.median(others))
        if r["brawler"]:
            obs_per_brawler[(r["tag"], r["brawler"])].append(statistics.median(others))

    # プレイヤー単位 MMR推定値
    print("\n" + "="*80)
    print("=== プレイヤー単位 「観察ベース MMR」 vs 既存指標 ===")
    print("="*80)
    print("「観察ベースMMR」 = そのプレイヤーが ranked試合で経験した 他者 brawler trophies 中央値の中央値")

    rows_p = []
    for tag, arr in observed_data.items():
        if len(arr) < 30: continue
        prof = profiles.get(tag)
        if not prof: continue
        rows_p.append({
            "tag": tag,
            "name": prof["name"],
            "obs_mean_med": statistics.median(arr),     # 平均トロの中央値
            "obs_med_med": statistics.median(observed_med[tag]),  # 中央トロの中央値
            "obs_max_med": statistics.median(observed_max[tag]),  # 最高トロの中央値
            "n_battles": len(arr),
            **prof,
        })

    if not rows_p:
        print("サンプル不足")
        return

    # ランキング表示
    rows_p.sort(key=lambda x: -x["obs_med_med"])
    print(f"\n{'rank':<5} {'tag':<15} {'name':<22} {'obs_med':>8} {'obs_avg':>8} {'highest':>8} {'rankedElo':>9} {'N'}")
    for i, p in enumerate(rows_p[:50]):
        print(f"{i+1:<5} {p['tag']:<15} {p['name'][:20]:<22} {p['obs_med_med']:>7.0f} {p['obs_mean_med']:>7.0f} {p['highest']:>7} {p['rankedElo']:>8} {p['n_battles']:>5}")

    # 相関
    print(f"\n=== 観察ベースMMR vs 既存指標 (N={len(rows_p)}) ===")
    for tgt_k, tgt_lab in [("obs_med_med", "観察中央トロ中央値"), ("obs_mean_med", "観察平均トロ中央値"), ("obs_max_med", "観察最高トロ中央値")]:
        print(f"\n  [{tgt_lab}]")
        for k in ["highest", "trophies", "rankedElo", "highestRankedElo", "expLevel"]:
            x = [p[k] for p in rows_p]
            y = [p[tgt_k] for p in rows_p]
            rho, _ = spearman(x, y)
            print(f"    vs {k:<22}: rho={rho:+.3f}")

    # ブロウラー別 観察MMR
    print()
    print("="*80)
    print("=== 個別 (プレイヤー × ブロウラー) ペアの観察MMR 上位下位 ===")
    print("="*80)
    pairs = []
    for (tag, br), arr in obs_per_brawler.items():
        if len(arr) < 10: continue
        nm = profiles.get(tag, {}).get("name", "")
        pairs.append({"tag": tag, "name": nm, "br": br, "obs_med": statistics.median(arr), "n": len(arr)})
    pairs.sort(key=lambda x: -x["obs_med"])
    print(f"\nTOP 20 (このペアで遭遇した相手 が強い):")
    for p in pairs[:20]:
        print(f"  {p['name'][:14]:<14} × {p['br']:<14} obs_med={p['obs_med']:.0f}  N={p['n']}")
    print(f"\nBOTTOM 20 (このペアで遭遇した相手 が弱い):")
    for p in pairs[-20:]:
        print(f"  {p['name'][:14]:<14} × {p['br']:<14} obs_med={p['obs_med']:.0f}  N={p['n']}")

    # 同一プレイヤー内 ブロウラー差 (= プレイヤーは同じだが、 そのキャラ使ったときだけ MMR が違う)
    print()
    print("="*80)
    print("=== 同一プレイヤー × 別ブロウラー の観察MMR スプレッド (Top10) ===")
    print("="*80)
    by_player = defaultdict(list)
    for p in pairs:
        by_player[p["tag"]].append(p)
    spreads = []
    for tag, ps in by_player.items():
        if len(ps) < 3: continue
        vals = [p["obs_med"] for p in ps]
        spreads.append({
            "tag": tag,
            "name": profiles.get(tag, {}).get("name", ""),
            "spread": max(vals) - min(vals),
            "n_brawlers": len(ps),
            "best": max(ps, key=lambda x: x["obs_med"]),
            "worst": min(ps, key=lambda x: x["obs_med"]),
        })
    spreads.sort(key=lambda x: -x["spread"])
    print(f"\n{'name':<22} {'spread':>8} {'n_br':>5} {'最強キャラ':<22} {'最弱キャラ':<22}")
    for s in spreads[:15]:
        best = s["best"]; worst = s["worst"]
        print(f"  {s['name'][:20]:<22} {s['spread']:>7.0f} {s['n_brawlers']:>5}  {best['br']+'='+str(int(best['obs_med'])):<22} {worst['br']+'='+str(int(worst['obs_med'])):<22}")
    print("\n→ spread が大きい人ほど、 同じプレイヤーでも 「強キャラ使用時」 と「弱キャラ使用時」 で別MMRが効いている証拠 (== MMR は ブロウラー単位)")


if __name__ == "__main__":
    main()
