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
import re
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
OFFICIAL_BRAWLERS = DATA / "official_brawlers.json"  # 公式API IDマップ (Brawlify未収録対応)
MAPS_POOL = DATA / "maps_pool.json"
OUT = DATA / "db.json"
BRAWLIFY_CDN = "https://cdn.brawlify.com/brawlers/borders"

MIN_PICKS_ABS = 1  # 絶対最小pick数 (すべてのプレイされたブロウラーを表示)
MIN_PICK_RATE = 0  # マップ内ピック率フィルタ無効
BAYES_PRIOR = 100  # ベイズ事前分布の強さ (少サンプルはマップ平均寄り、強めに)
RANK_WEIGHT = 5.0  # 順位優位の重み (composite score 内)
MIN_PICKS_FOR_TRIO = 5  # 推奨編成最小pick数
TOP_N_TRIOS = 8
TOP_N_TIER = 200  # 全102体収まる
# 順位スコア重み (Brawl Stars トロフィー変動準拠、調整版)
SCORE_R1, SCORE_R2, SCORE_R3, SCORE_R4 = 9, 4, -4, -9
SCORE_MIN = SCORE_R4  # -9
SCORE_MAX = SCORE_R1  # 9
SCORE_RANGE = SCORE_MAX - SCORE_MIN  # 18
# ティア判定に必要な最小サンプル数 (これ未満は「?」)
MIN_PICKS_FOR_RELIABLE_TIER = 50
# 人気ボーナス: pick_rate >= 5% で score を 1.05倍 (条件: WR>マップ平均)
POPULAR_PICK_RATE = 0.05
POPULARITY_BONUS = 1.05
# 使用ボーナス: 各マップ使用率TOP3のキャラに 1.02倍 (注目枠)
USED_BONUS = 1.02
USED_TOP_N = 3
# サンプル少penalty: picks <= 300 で 0.9倍
LOW_PICKS_THRESHOLD = 300
LOW_PICKS_PENALTY = 0.9
# ティア percentile-based 閾値 (上位から %)
TIER_PCT_S_PLUS = 0.10
TIER_PCT_S = 0.25
TIER_PCT_A = 0.55
TIER_PCT_B = 0.80


def build_map_tier_list(brawler_rows, brawler_by_name, rank_dist_for_map=None, brawler_jp=None, official_id_map=None):
    """
    マップ別ティアリストを生成。
    - 「重み付き擬似勝率」 (1位×5 + 2位×1) / (picks×5) を主指標に
    - ベイズ平均で少サンプル抑制
    - マップ平均からの相対deltaでティア判定
    - 強さスコア降順でソート
    """
    if not brawler_rows:
        return [], 0.0, 0.0

    total_picks = sum(r["picks"] for r in brawler_rows)
    if total_picks == 0:
        return [], 0.0, 0.0

    map_avg_rank = (
        sum(r["avg_rank"] * r["picks"] for r in brawler_rows) / total_picks
    )

    # マップ全体の重み付きスコア (Brawl Stars トロフィー変動準拠)
    if rank_dist_for_map:
        map_points = sum(
            rd["r1"] * SCORE_R1 + rd["r2"] * SCORE_R2
            + rd["r3"] * SCORE_R3 + rd["r4"] * SCORE_R4
            for rd in rank_dist_for_map.values()
        )
        map_dist_total = sum(
            rd["r1"] + rd["r2"] + rd["r3"] + rd["r4"]
            for rd in rank_dist_for_map.values()
        )
    else:
        map_points = 0
        map_dist_total = 0
    # マップ平均(per pick)、範囲 [SCORE_MIN, SCORE_MAX]
    map_avg_score = map_points / map_dist_total if map_dist_total else 0
    # 0-1正規化
    map_avg_weighted = (map_avg_score - SCORE_MIN) / SCORE_RANGE

    # 互換のため top2 rate も計算
    total_wins = sum(r["wins"] for r in brawler_rows)
    map_avg_wr = total_wins / total_picks

    # 使用率TOP3のブロウラー (USED_BONUS 対象)
    top_used_brawlers = {
        r["brawler"]
        for r in sorted(brawler_rows, key=lambda x: -x["picks"])[:USED_TOP_N]
    }

    scored = []
    for r in brawler_rows:
        picks = r["picks"]
        if picks < MIN_PICKS_ABS:
            continue
        pick_rate = picks / total_picks
        if pick_rate < MIN_PICK_RATE:
            continue

        # 順位分布
        rd = (rank_dist_for_map or {}).get(
            r["brawler"], {"r1": 0, "r2": 0, "r3": 0, "r4": 0}
        )
        rd_total = rd["r1"] + rd["r2"] + rd["r3"] + rd["r4"]
        rank1_rate = round(rd["r1"] / rd_total, 3) if rd_total else 0
        rank2_rate = round(rd["r2"] / rd_total, 3) if rd_total else 0

        # 重み付きポイント合計 (1位×9 + 2位×4 + 3位×-5 + 4位×-11)
        points = (
            rd["r1"] * SCORE_R1 + rd["r2"] * SCORE_R2
            + rd["r3"] * SCORE_R3 + rd["r4"] * SCORE_R4
        )
        # per pick avg
        avg_score = points / rd_total if rd_total else 0
        # 0-1 正規化
        weighted_wr = (avg_score - SCORE_MIN) / SCORE_RANGE

        # ベイズ平均: マップ平均score を事前分布に
        bayes_score = (
            (points + map_avg_score * BAYES_PRIOR) / (rd_total + BAYES_PRIOR)
        )
        bayes_weighted = (bayes_score - SCORE_MIN) / SCORE_RANGE

        # 旧bayes_wr (top2ベース) も互換で残す
        bayes_wr = (r["wins"] + map_avg_wr * BAYES_PRIOR) / (picks + BAYES_PRIOR)

        rank_adv = map_avg_rank - r["avg_rank"]
        # スコアは weighted ベース
        score = bayes_weighted * 100 + rank_adv * RANK_WEIGHT
        # サンプル少penalty (picks <= 300 で 0.9倍)
        if picks <= LOW_PICKS_THRESHOLD:
            score *= LOW_PICKS_PENALTY
        # ボーナス類は全て削除 (人気/使用率TOP3 ボーナス無し)
        delta = bayes_weighted - map_avg_weighted

        master = brawler_by_name.get(r["brawler"].upper(), {})
        br_jp = get_brawler_jp(r["brawler"], brawler_by_name, brawler_jp)
        img = get_brawler_image(r["brawler"], brawler_by_name, official_id_map or {})
        insufficient = picks < MIN_PICKS_FOR_RELIABLE_TIER
        scored.append({
            "brawler": r["brawler"],
            "brawler_jp": br_jp,
            "brawler_id": master.get("id") or (official_id_map or {}).get(r["brawler"].upper()),
            "image_url": img,
            "picks": picks,
            "wins": r["wins"],
            "win_rate": r["win_rate"],
            "bayes_wr": round(bayes_wr, 3),
            "weighted_wr": round(weighted_wr, 3),
            "bayes_weighted": round(bayes_weighted, 3),
            "avg_rank": r["avg_rank"],
            "rank1_rate": rank1_rate,
            "rank2_rate": rank2_rate,
            "pick_rate": round(pick_rate, 3),
            "score": round(score, 2),
            "delta": round(delta, 3),
            "insufficient": insufficient,
            "tier": "",
        })

    # 信頼サンプル(picks>=50)だけでpercentileティア割当
    sufficient = sorted(
        [s for s in scored if not s["insufficient"]], key=lambda x: -x["score"]
    )
    insufficient_list = sorted(
        [s for s in scored if s["insufficient"]], key=lambda x: -x["score"]
    )
    n = len(sufficient)
    for i, s in enumerate(sufficient):
        pct = i / n if n else 1
        if pct < TIER_PCT_S_PLUS:
            s["tier"] = "S+"
        elif pct < TIER_PCT_S:
            s["tier"] = "S"
        elif pct < TIER_PCT_A:
            s["tier"] = "A"
        elif pct < TIER_PCT_B:
            s["tier"] = "B"
        else:
            s["tier"] = "C"
    for s in insufficient_list:
        s["tier"] = "?"

    # 出力: 信頼サンプル(score降順) → 不足サンプル(score降順)
    final = sufficient + insufficient_list
    return final[:TOP_N_TIER], map_avg_wr, map_avg_rank


HIGH_TROPHY_THRESHOLD = 2000  # この値以上の team avg trophy は重み2倍
HIGH_TROPHY_WEIGHT = 2.0


def name_to_hash(name):
    """EN名からBrawlify hash推定 (Brawlify未収録ブロウラー用)"""
    s = (name or "").lower()
    s = re.sub(r"\s*&\s*", "-", s)  # & を - に (LARRY & LAWRIE → larry-lawrie)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


def get_brawler_jp(brawler_name, brawler_by_name, brawler_jp):
    """master優先、無ければEN名からhash推定でJP取得"""
    if not brawler_jp:
        return ""
    master = brawler_by_name.get((brawler_name or "").upper(), {})
    h = master.get("hash") or name_to_hash(brawler_name)
    return brawler_jp.get(h, "")


def get_brawler_image(brawler_name, brawler_by_name, official_id_map):
    """Brawlify masterから取得、無ければ公式API IDからCDN URL構築"""
    master = brawler_by_name.get((brawler_name or "").upper(), {})
    if master.get("image_url"):
        return master["image_url"]
    # fallback: 公式API IDから Brawlify CDN
    bid = official_id_map.get((brawler_name or "").upper())
    if bid:
        return f"{BRAWLIFY_CDN}/{bid}.png"
    return None


def extract_trios_and_rank_dist(battles):
    """
    raw battles から
    - trio 編成統計 (map → trio_key → 集計)
    - ブロウラー別順位分布 (map → brawler → 1位/2位/3位/4位 count, weighted)
    高トロ帯(2000+)バトルは2倍重みでカウント。
    """
    trio_stats = defaultdict(lambda: defaultdict(lambda: {"picks": 0, "wins": 0, "ranks": []}))
    rank_dist = defaultdict(lambda: defaultdict(lambda: {"r1": 0.0, "r2": 0.0, "r3": 0.0, "r4": 0.0}))
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

        # チーム平均トロフィー(各ブロウラーのpersonalトロ)
        team_trophies = [
            (p.get("brawler") or {}).get("trophies", 0) for p in team
        ]
        avg_trophy = (
            sum(team_trophies) / len(team_trophies) if team_trophies else 0
        )
        # 高トロ帯(2000+)は重み2倍、それ以外は1.0
        weight = HIGH_TROPHY_WEIGHT if avg_trophy >= HIGH_TROPHY_THRESHOLD else 1.0

        # trio 統計 (推奨編成は素のpicks/winsで集計)
        trio_key = tuple(brawlers)
        s = trio_stats[map_name][trio_key]
        s["picks"] += 1
        if is_win:
            s["wins"] += 1
        s["ranks"].append(rank)

        # 各ブロウラーの順位分布 (weighted)
        for br in brawlers:
            rd = rank_dist[map_name][br]
            if rank == 1:
                rd["r1"] += weight
            elif rank == 2:
                rd["r2"] += weight
            elif rank == 3:
                rd["r3"] += weight
            else:
                rd["r4"] += weight
    return trio_stats, rank_dist


def main():
    # マスタ読み込み
    manual = json.loads(MANUAL.read_text(encoding="utf-8"))
    map_jp = manual.get("map_jp_names", {})
    brawler_jp = manual.get("brawler_jp_names", {})

    brawlers_raw = json.loads(BRAWLERS.read_text(encoding="utf-8"))
    brawler_by_name = {b["name"].upper(): b for b in brawlers_raw}

    # 公式API ID マップ (Brawlify未収録キャラの画像URL構築用)
    official_id_map = {}
    if OFFICIAL_BRAWLERS.exists():
        official_list = json.loads(OFFICIAL_BRAWLERS.read_text(encoding="utf-8"))
        official_id_map = {o["name"].upper(): o["id"] for o in official_list}
        print(f"Official brawler IDs loaded: {len(official_id_map)}")

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
            brawler_rows, brawler_by_name, rank_dist.get(map_name), brawler_jp, official_id_map
        )

        # 推奨編成 + 全trios (シナジー検索用)
        m_trios = trio_stats.get(map_name, {})
        all_trios = []
        for trio_key, s in m_trios.items():
            if s["picks"] < MIN_PICKS_FOR_TRIO:
                continue
            picks = s["picks"]
            wins = s["wins"]
            wr = wins / picks
            ranks = s["ranks"]
            avg_r = sum(ranks) / len(ranks) if ranks else 0
            r1c = sum(1 for x in ranks if x == 1)
            r2c = sum(1 for x in ranks if x == 2)
            r3c = sum(1 for x in ranks if x == 3)
            r4c = sum(1 for x in ranks if x >= 4)
            members = []
            for br in trio_key:
                bm_jp = get_brawler_jp(br, brawler_by_name, brawler_jp)
                bm_img = get_brawler_image(br, brawler_by_name, official_id_map)
                members.append(
                    {
                        "brawler": br,
                        "brawler_jp": bm_jp,
                        "image_url": bm_img,
                    }
                )
            all_trios.append(
                {
                    "members": members,
                    "picks": picks,
                    "wins": wins,
                    "win_rate": round(wr, 3),
                    "avg_rank": round(avg_r, 2),
                    "rank1_count": r1c,
                    "rank2_count": r2c,
                    "rank3_count": r3c,
                    "rank4_count": r4c,
                }
            )
        all_trios.sort(key=lambda x: (-x["win_rate"], -x["picks"]))
        rec_trios = all_trios[:TOP_N_TRIOS]

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
                "all_trios": all_trios,  # シナジー検索用 (min picks 5以上)
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
                "id": master.get("id") or official_id_map.get(br_name.upper()),
                "name": br_name,
                "name_jp": get_brawler_jp(br_name, brawler_by_name, brawler_jp),
                "image_url": get_brawler_image(br_name, brawler_by_name, official_id_map),
                "rarity": master.get("rarity"),
                "total_picks": sum(r["picks"] for r in br_rows),
                "best_maps": [
                    {
                        "map": r["map"],
                        "map_jp": map_jp.get(r["map"].lower().replace(" ", "-"), ""),
                        "win_rate": r["win_rate"],
                        "picks": r["picks"],
                    }
                    for r in best
                ],
                "worst_maps": [
                    {
                        "map": r["map"],
                        "map_jp": map_jp.get(r["map"].lower().replace(" ", "-"), ""),
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
