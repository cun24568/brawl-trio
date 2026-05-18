"""仮説検証: 練習試合 (battle.type='friendly') のbot強さからMMRを推定可能か.

データ:
  battle.type='friendly' は 105試合 (DB全体)
  type='challenge' も 88件 (これも bot fill 系の可能性)
  team内人数 < 通常 (12) なら bot 不在 / 9-11人なら一部 bot
  9以下の試合は bot枠が teams に明示 されてない可能性 (空 slot)

分析方針:
  1. friendly/challenge 試合の試合内構成を全部出す
  2. 人数が < 12 なら bot 埋め確実
  3. bot とおぼしき位置 (= 人間プレイヤーじゃない slot) のトロフィーを抽出
  4. 観察者 (battlelog 観測者) の brawler_highest と、 そのbot のトロフィーを相関
  5. 「人間プレイヤーのみで埋まった friendly (= 12人) vs bot fill されてる friendly」 で
     試合内 trophy 分散 を比較

副次仮説:
  - friendly 試合のトロフィー値が「観察者の MMR推定値」 を映しているなら、
    観察者 highest が高いほど、 同行する人間/bot の trophies も高い、 という対称性が出る
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

    # 1. プロフィール
    brawler_meta = {}  # (tag, br) → highest
    wl = con.execute("SELECT tag, profile_json FROM watchlist WHERE profile_json IS NOT NULL").fetchall()
    for r in wl:
        try:
            p = json.loads(r["profile_json"])
        except Exception:
            continue
        for b in p.get("brawlers", []):
            brawler_meta[(r["tag"], b["name"])] = {
                "highest": b.get("highestTrophies", 0) or 0,
                "tr": b.get("trophies", 0) or 0,
            }

    # 2. friendly/challenge 試合を全部出す
    print("="*80)
    print("=== friendly/challenge 試合 全構成 ===")
    print("="*80)
    rows = con.execute(
        "SELECT tag, battle_time, mode, map, brawler, rank, raw_json FROM battles "
        "WHERE mode='trioShowdown'"
    ).fetchall()

    friendly_battles = []
    for r in rows:
        try:
            raw = json.loads(r["raw_json"])
        except Exception:
            continue
        battle = raw.get("battle") or {}
        btype = battle.get("type", "")
        if btype not in ("friendly", "challenge"):
            continue
        teams = battle.get("teams") or []
        if not teams:
            continue
        n_players = sum(len(t) for t in teams)
        # 観察者の highest を取得
        my_meta = brawler_meta.get((r["tag"], r["brawler"]))
        my_highest = my_meta["highest"] if my_meta else None
        # 全プレイヤーのトロフィー
        all_tr = []
        all_tags = []
        all_names = []
        for team in teams:
            for p in team:
                all_tr.append((p.get("brawler") or {}).get("trophies", 0) or 0)
                all_tags.append(p.get("tag", ""))
                all_names.append(p.get("name", ""))
        friendly_battles.append({
            "tag": r["tag"],
            "battle_time": r["battle_time"],
            "type": btype,
            "brawler": r["brawler"],
            "rank": r["rank"],
            "n_players": n_players,
            "my_highest": my_highest,
            "all_tr": all_tr,
            "all_tags": all_tags,
            "all_names": all_names,
            "team_count": len(teams),
            "team_sizes": [len(t) for t in teams],
        })

    print(f"\nfriendly/challenge trio試合: {len(friendly_battles)}")

    by_type = defaultdict(list)
    for fb in friendly_battles:
        by_type[fb["type"]].append(fb)

    for btype, fbs in by_type.items():
        print(f"\n--- type={btype} ({len(fbs)}試合) ---")
        # 人数 分布
        n_dist = Counter(fb["n_players"] for fb in fbs)
        print(f"  人数分布: {dict(n_dist)}")
        # 平均トロ分布
        all_avg = [statistics.mean(fb["all_tr"]) for fb in fbs if fb["all_tr"]]
        if all_avg:
            print(f"  試合内平均トロ: median={statistics.median(all_avg):.0f}, mean={statistics.mean(all_avg):.0f}")

    print()
    print("="*80)
    print("=== 観察者 brawler.highest × 試合内 平均トロ (friendly/challenge) ===")
    print("="*80)
    print("仮説: 観察者の MMR (≈ highest) が高いほど、 同行人/bot の trophies も高い")
    print("       → ボットも MMR 連動で強くなる (= bot強さでMMR推定可能の裏付け)")

    xs = []
    ys_avg = []
    ys_max = []
    ys_min = []
    for fb in friendly_battles:
        if fb["my_highest"] is None or not fb["all_tr"]:
            continue
        # 観察者自身を除く
        others = [tr for tag, tr in zip(fb["all_tags"], fb["all_tr"]) if tag != fb["tag"]]
        if not others:
            continue
        xs.append(fb["my_highest"])
        ys_avg.append(statistics.mean(others))
        ys_max.append(max(others))
        ys_min.append(min(others))
    print(f"  N={len(xs)}")
    if len(xs) >= 5:
        rho_a, _ = spearman(xs, ys_avg)
        rho_x, _ = spearman(xs, ys_max)
        rho_n, _ = spearman(xs, ys_min)
        print(f"  自highest × 他者平均トロ:  rho={rho_a:+.3f}")
        print(f"  自highest × 他者最高トロ:  rho={rho_x:+.3f}")
        print(f"  自highest × 他者最低トロ:  rho={rho_n:+.3f}")

    # 帯別
    print("\n  自highest 帯別 × 他者平均トロ:")
    bands = [(0, 999), (1000, 1499), (1500, 1999), (2000, 2499), (2500, 9999)]
    for lo, hi in bands:
        sub = [(x, y) for x, y in zip(xs, ys_avg) if lo <= x <= hi]
        if len(sub) < 3: continue
        print(f"    highest {lo:>5}-{hi:<5}: N={len(sub):>3}  他者平均トロ中央値={statistics.median([y for _, y in sub]):.0f}")

    # 通常 (ranked) と比較
    print()
    print("="*80)
    print("=== 比較: 通常マッチ (type='ranked') の対称性 ===")
    print("="*80)
    xs_r = []
    ys_r = []
    for r in rows[:5000]:  # サンプル抽出
        try:
            raw = json.loads(r["raw_json"])
        except Exception:
            continue
        battle = raw.get("battle") or {}
        if battle.get("type", "") != "ranked":
            continue
        teams = battle.get("teams") or []
        if not teams: continue
        my_meta = brawler_meta.get((r["tag"], r["brawler"]))
        if not my_meta: continue
        others = []
        for team in teams:
            for p in team:
                if p.get("tag") != r["tag"]:
                    others.append((p.get("brawler") or {}).get("trophies", 0) or 0)
        if not others: continue
        xs_r.append(my_meta["highest"])
        ys_r.append(statistics.mean(others))
    if xs_r:
        rho, n = spearman(xs_r, ys_r)
        print(f"  通常 (sample 5000): rho(自highest, 他者平均トロ) = {rho:+.3f}  N={n}")

    # 人数 < 12 の friendly 試合だけ抽出 (bot fill 確定)
    print()
    print("="*80)
    print("=== bot fill 確定 試合 (人数<12 + friendly/challenge) ===")
    print("="*80)
    bot_fills = [fb for fb in friendly_battles if fb["n_players"] < 12]
    print(f"  N={len(bot_fills)} 試合")
    if bot_fills:
        for fb in bot_fills[:20]:
            others_tr = [tr for tag, tr in zip(fb["all_tags"], fb["all_tr"]) if tag != fb["tag"]]
            print(f"  {fb['battle_time'][:12]} type={fb['type']:<10} 人数={fb['n_players']:>2}  my_highest={fb['my_highest']!s:>6}  自rank={fb['rank']}  他者トロ={others_tr}")

    # bot fill 試合で observer MMR と トロフィー対称性
    if len(bot_fills) >= 5:
        xs2, ys2 = [], []
        for fb in bot_fills:
            if fb["my_highest"] is None: continue
            others = [tr for tag, tr in zip(fb["all_tags"], fb["all_tr"]) if tag != fb["tag"]]
            if not others: continue
            xs2.append(fb["my_highest"])
            ys2.append(statistics.mean(others))
        if len(xs2) >= 5:
            rho2, _ = spearman(xs2, ys2)
            print(f"  bot fill 試合の自highest × 同行平均トロ: rho={rho2:+.3f} N={len(xs2)}")

    # ボット名らしきパターン抽出 (人間が命名した可能性除外して、 tagが特異な物のみ)
    print()
    print("="*80)
    print("=== タグパターン異常 (= 真のbot 候補) の抽出 ===")
    print("="*80)
    # 公式タグは ^[A-Z0-9]{6,12}$ 形式
    weird_tags = Counter()
    weird_examples = []
    for r in rows:
        try:
            raw = json.loads(r["raw_json"])
        except Exception:
            continue
        battle = raw.get("battle") or {}
        teams = battle.get("teams") or []
        for team in teams:
            for p in team:
                tag = p.get("tag", "")
                if not tag.startswith("#"):
                    weird_tags[("nostart", tag[:20])] += 1
                    continue
                body = tag[1:]
                if not body.isalnum() or len(body) < 6 or len(body) > 12:
                    weird_tags[("badformat", tag[:20])] += 1
                    if len(weird_examples) < 10:
                        weird_examples.append({"tag": tag, "name": p.get("name", ""), "br": (p.get("brawler") or {}).get("name", ""), "tr": (p.get("brawler") or {}).get("trophies", 0)})
    print(f"  異常タグ パターン数: {len(weird_tags)}")
    for (kind, tag), n in weird_tags.most_common(10):
        print(f"    [{kind}] {tag!r}: {n}件")
    print("  サンプル:")
    for ex in weird_examples[:10]:
        print(f"    {ex}")

    print()
    print("=== END ===")


if __name__ == "__main__":
    main()
