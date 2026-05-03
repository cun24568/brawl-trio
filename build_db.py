"""
trio_meta_full.csv + manual_mappings.json + brawlers.json + maps_pool.json
を統合して UI 用の単一 db.json を出力する。

スキーマ:
{
  "generated_at": "...",
  "maps": [
    {
      "id", "name", "name_jp", "image_url", "in_pool",
      "total_picks", "tier_list": [{"brawler","picks","wins","win_rate","tier"}, ...]
    }
  ],
  "brawlers": [
    {
      "id", "name", "name_jp", "image_url", "rarity",
      "best_maps": [{"map","win_rate","picks"}, ...],
    }
  ]
}
"""
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent
DATA = ROOT / "data"

META_CSV = DATA / "trio_meta_full.csv"
BATTLES_JSON = DATA / "trio_battles_full.json"  # 旧形式 (互換)
BATTLES_JSONL = DATA / "trio_battles.jsonl"  # 新形式 (蓄積型)
MANUAL = DATA / "manual_mappings.json"
BRAWLERS = DATA / "brawlers.json"
MAPS_POOL = DATA / "maps_pool.json"
OUT = DATA / "db.json"

MIN_PICKS_ABS = 5  # 絶対最小pick数
MIN_PICK_RATE = 0.005  # マップ内ピック率最小値 (0.5%)
BAYES_PRIOR = 10  # ベイズ事前分布の強さ
RANK_WEIGHT = 5.0  # 順位優位の重み (composite score 内)
MIN_PICKS_FOR_TRIO = 2
TOP_N_TRIOS = 8
TOP_N_TIER = 25


def build_map_tier_list(brawler_rows, brawler_by_name, rank_dist_for_map=None):
    """
    マップ別ティアリストを生成。
    - ベイズ平均でWRを縮小 (少サンプルがS+にならない)
    - マップ平均WRを基準に相対評価 (マップ間公平)
    - avg_rank を強さスコアに反映 (1位率重視)
    - 使用率フィルタ (メタ外を除外)
    - 強さスコア降順でソート (強い順)
    """
    if not brawler_rows:
        return [], 0.0, 0.0

    total_picks = sum(r["picks"] for r in brawler_rows)
    if total_picks == 0:
        return [], 0.0, 0.0

    total_wins = sum(r["wins"] for r in brawler_rows)
    map_avg_wr = total_wins / total_picks
    map_avg_rank = (
        sum(r["avg_rank"] * r["picks"] for r in brawler_rows) / total_picks
    )

    scored = []
    for r in brawler_rows:
        picks = r["picks"]
        if picks < MIN_PICKS_ABS:
            continue
        pick_rate = picks / total_picks
        if pick_rate < MIN_PICK_RATE:
            continue

        # ベイズ平均: マップ平均を事前分布に
        bayes_wr = (r["wins"] + map_avg_wr * BAYES_PRIOR) / (picks + BAYES_PRIOR)
        rank_adv = map_avg_rank - r["avg_rank"]  # 正なら強い (低順位=好)
        score = bayes_wr * 100 + rank_adv * RANK_WEIGHT
        wr_delta = bayes_wr - map_avg_wr  # マップ平均からの差

        # ティア = マップ平均からの相対deltaで決定
        if wr_delta >= 0.10:
            tier = "S+"
        elif wr_delta >= 0.05:
            tier = "S"
        elif wr_delta >= -0.02:
            tier = "A"
        elif wr_delta >= -0.08:
            tier = "B"
        else:
            tier = "C"

        master = brawler_by_name.get(r["brawler"].upper(), {})
        # 順位分布
        rd = (rank_dist_for_map or {}).get(r["brawler"], {"r1": 0, "r2": 0, "r3": 0, "r4": 0})
        rd_total = rd["r1"] + rd["r2"] + rd["r3"] + rd["r4"]
        rank1_rate = round(rd["r1"] / rd_total, 3) if rd_total else 0
        rank2_rate = round(rd["r2"] / rd_total, 3) if rd_total else 0

        scored.append({
            "brawler": r["brawler"],
            "brawler_id": master.get("id"),
            "image_url": master.get("image_url"),
            "picks": picks,
            "wins": r["wins"],
            "win_rate": r["win_rate"],
            "bayes_wr": round(bayes_wr, 3),
            "avg_rank": r["avg_rank"],
            "rank1_rate": rank1_rate,
            "rank2_rate": rank2_rate,
            "pick_rate": round(pick_rate, 3),
            "score": round(score, 2),
            "tier": tier,
        })

    # 強さスコア降順 (= 強いキャラほど上)
    scored.sort(key=lambda x: -x["score"])
    return scored[:TOP_N_TIER], map_avg_wr, map_avg_rank


def extract_trios_and_rank_dist(battles):
    """
    raw battles から
    - trio 編成統計 (map → trio_key → 集計)
    - ブロウラー別順位分布 (map → brawler → 1位/2位/3位/4位 count)
    の両方を返す。
    """
    trio_stats = defaultdict(lambda: defaultdict(lambda: {"picks": 0, "wins": 0, "ranks": []}))
    rank_dist = defaultdict(lambda: defaultdict(lambda: {"r1": 0, "r2": 0, "r3": 0, "r4": 0}))
    seen = set()
    for b in battles:
        key = (b.get("battleTime", ""), b.get("_requester_tag", ""))
        if key in seen:
            continue
        seen.add(key)
        ev = b.get("event", {})
        bt = b.get("battle", {})
        teams = bt.get("teams", [])
        ti = b.get("_requester_team_idx")
        if ti is None or ti >= len(teams):
            continue
        team = teams[ti]
        brawlers = sorted(
            [(p.get("brawler") or {}).get("name", "?") for p in team]
        )
        if len(brawlers) != 3:
            continue
        rank = bt.get("rank") or 5
        is_win = rank <= 2
        map_name = ev.get("map", "?")

        # trio 統計
        trio_key = tuple(brawlers)
        s = trio_stats[map_name][trio_key]
        s["picks"] += 1
        if is_win:
            s["wins"] += 1
        s["ranks"].append(rank)

        # 各ブロウラーの順位分布
        for br in brawlers:
            rd = rank_dist[map_name][br]
            if rank == 1:
                rd["r1"] += 1
            elif rank == 2:
                rd["r2"] += 1
            elif rank == 3:
                rd["r3"] += 1
            else:
                rd["r4"] += 1
    return trio_stats, rank_dist


def main():
    # マスタ読み込み
    manual = json.loads(MANUAL.read_text(encoding="utf-8"))
    map_jp = manual.get("map_jp_names", {})
    brawler_jp = manual.get("brawler_jp_names", {})

    brawlers_raw = json.loads(BRAWLERS.read_text(encoding="utf-8"))
    brawler_by_name = {b["name"].upper(): b for b in brawlers_raw}

    pool_maps = json.loads(MAPS_POOL.read_text(encoding="utf-8"))
    pool_by_hash = {m["hash"]: m for m in pool_maps}

    # メタCSV読み込み
    rows = list(csv.DictReader(META_CSV.open(encoding="utf-8-sig")))
    for r in rows:
        r["picks"] = int(r["picks"])
        r["wins"] = int(r["wins"])
        r["win_rate"] = float(r["win_rate"])
        r["avg_rank"] = float(r["avg_rank"])

    # マップ別グループ
    by_map_name = defaultdict(list)
    for r in rows:
        by_map_name[r["map"]].append(r)

    # 推奨編成 + 順位分布抽出 (JSONL streaming 優先, 互換でJSONも対応)
    if BATTLES_JSONL.exists():
        def battle_iter():
            with open(BATTLES_JSONL, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except Exception:
                        pass
        battles = battle_iter()
    elif BATTLES_JSON.exists():
        battles = json.loads(BATTLES_JSON.read_text(encoding="utf-8"))
    else:
        battles = []
    trio_stats, rank_dist = extract_trios_and_rank_dist(battles)
    print(f"Extracted trio + rank dist for {len(trio_stats)} maps")

    # マップDB生成
    maps_out = []
    for map_name, brawler_rows in by_map_name.items():
        # hash 推定: 名前を kebab-case に
        hash_guess = map_name.lower().replace(" ", "-")
        in_pool = hash_guess in pool_by_hash
        pool_map = pool_by_hash.get(hash_guess, {})

        total = sum(r["picks"] for r in brawler_rows)
        tier_list, map_avg_wr, map_avg_rank = build_map_tier_list(
            brawler_rows, brawler_by_name, rank_dist.get(map_name)
        )

        # 推奨編成: WR降順 + picks降順
        m_trios = trio_stats.get(map_name, {})
        rec_trios = []
        for trio_key, s in m_trios.items():
            if s["picks"] < MIN_PICKS_FOR_TRIO:
                continue
            picks = s["picks"]
            wins = s["wins"]
            wr = wins / picks
            avg_r = sum(s["ranks"]) / len(s["ranks"])
            # 各メンバーの画像URL付き
            members = []
            for br in trio_key:
                bm = brawler_by_name.get(br.upper(), {})
                members.append(
                    {
                        "brawler": br,
                        "image_url": bm.get("image_url"),
                    }
                )
            rec_trios.append(
                {
                    "members": members,
                    "picks": picks,
                    "wins": wins,
                    "win_rate": round(wr, 3),
                    "avg_rank": round(avg_r, 2),
                }
            )
        rec_trios.sort(key=lambda x: (-x["win_rate"], -x["picks"]))
        rec_trios = rec_trios[:TOP_N_TRIOS]

        maps_out.append(
            {
                "id": pool_map.get("id"),
                "hash": hash_guess,
                "name": map_name,
                "name_jp": map_jp.get(hash_guess, ""),
                "image_url": pool_map.get("image_url"),
                "in_pool": in_pool,
                "total_picks": total,
                "map_avg_wr": round(map_avg_wr, 3),
                "map_avg_rank": round(map_avg_rank, 2),
                "tier_list": tier_list,
                "recommended_trios": rec_trios,
            }
        )
    maps_out.sort(key=lambda m: -m["total_picks"])

    # ブロウラーDB生成 (各ブロウラーが強いマップ TOP5)
    by_brawler = defaultdict(list)
    for r in rows:
        by_brawler[r["brawler"]].append(r)

    brawlers_out = []
    for br_name, br_rows in by_brawler.items():
        master = brawler_by_name.get(br_name.upper(), {})
        # 強いマップ: WR降順 (5pick以上)
        valid = [r for r in br_rows if r["picks"] >= MIN_PICKS_ABS]
        best = sorted(valid, key=lambda x: -x["win_rate"])[:5]
        worst = sorted(valid, key=lambda x: x["win_rate"])[:3]
        brawlers_out.append(
            {
                "id": master.get("id"),
                "name": br_name,
                "name_jp": brawler_jp.get((master.get("hash") or "").lower(), ""),
                "image_url": master.get("image_url"),
                "rarity": master.get("rarity"),
                "total_picks": sum(r["picks"] for r in br_rows),
                "best_maps": [
                    {
                        "map": r["map"],
                        "win_rate": r["win_rate"],
                        "picks": r["picks"],
                    }
                    for r in best
                ],
                "worst_maps": [
                    {
                        "map": r["map"],
                        "win_rate": r["win_rate"],
                        "picks": r["picks"],
                    }
                    for r in worst
                ],
            }
        )
    brawlers_out.sort(key=lambda b: -b["total_picks"])

    db = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "total_maps": len(maps_out),
            "maps_in_pool": sum(1 for m in maps_out if m["in_pool"]),
            "total_brawlers": len(brawlers_out),
            "total_picks": sum(m["total_picks"] for m in maps_out),
        },
        "maps": maps_out,
        "brawlers": brawlers_out,
    }

    OUT.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved: {OUT}")
    print(f"  maps: {db['stats']['total_maps']} ({db['stats']['maps_in_pool']} in pool)")
    print(f"  brawlers: {db['stats']['total_brawlers']}")
    print(f"  total picks: {db['stats']['total_picks']}")


if __name__ == "__main__":
    main()
