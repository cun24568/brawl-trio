"""
Brawlify API からブロウラー & トリオサバイバルマップのマスタデータを取得し、
data/ フォルダに JSON と CSV で出力する。

依存: Python 3.8+ (標準ライブラリのみ)
実行: py fetch_data.py
"""
import json
import csv
from pathlib import Path
from urllib.request import urlopen, Request

API = "https://api.brawlapi.com/v1"
TRIO_SHOWDOWN_MODE_ID = 48000038
SCRIPT_DIR = Path(__file__).parent
OUT = SCRIPT_DIR / "data"
MANUAL = OUT / "manual_mappings.json"


def fetch_json(path: str):
    req = Request(f"{API}{path}", headers={"User-Agent": "brawl-trio-fetcher/1.0"})
    with urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def load_manual():
    if MANUAL.exists():
        with open(MANUAL, encoding="utf-8") as f:
            return json.load(f)
    return {"map_jp_names": {}, "brawler_jp_names": {}, "current_rotation_hashes": []}


def write_csv(path: Path, rows, headers):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def write_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    OUT.mkdir(exist_ok=True)
    manual = load_manual()
    map_jp = manual.get("map_jp_names", {})
    brawler_jp = manual.get("brawler_jp_names", {})
    rotation = set(manual.get("current_rotation_hashes", []))

    # 1. ブロウラー全件
    print("Fetching brawlers...")
    brawlers_raw = fetch_json("/brawlers")
    brawlers = sorted(
        [
            {
                "id": b["id"],
                "name": b["name"],
                "name_jp": brawler_jp.get(b.get("hash", ""), ""),
                "hash": b.get("hash", ""),
                "rarity": (b.get("rarity") or {}).get("name", ""),
                "class": (b.get("class") or {}).get("name", ""),
                "image_url": b.get("imageUrl", ""),
            }
            for b in brawlers_raw["list"]
            # released フィルタ無し: Brawlifyが released=false にしてる新キャラも含める
        ],
        key=lambda x: x["id"],
    )
    write_json(OUT / "brawlers.json", brawlers)
    write_csv(
        OUT / "brawlers.csv",
        brawlers,
        ["id", "name", "name_jp", "hash", "rarity", "class", "image_url"],
    )
    print(f"  -> {len(brawlers)} brawlers")

    # 2. マップ全件 → トリオサバイバル絞り込み
    print("Fetching maps...")
    maps_raw = fetch_json("/maps")
    trio_maps = sorted(
        [
            {
                "id": m["id"],
                "name": m["name"],
                "name_jp": map_jp.get(m.get("hash", ""), ""),
                "hash": m.get("hash", ""),
                "image_url": m.get("imageUrl", ""),
                "environment": (m.get("environment") or {}).get("name", ""),
                "disabled": m.get("disabled", False),
                "in_rotation_pool": m.get("hash", "") in rotation,
            }
            for m in maps_raw["list"]
            if (m.get("gameMode") or {}).get("id") == TRIO_SHOWDOWN_MODE_ID
        ],
        key=lambda x: x["id"],
    )
    active_maps = [m for m in trio_maps if not m["disabled"]]
    pool_maps = [m for m in active_maps if m["in_rotation_pool"]]
    # 同じ hash の重複(環境違い)は1件にdedupe
    seen = set()
    pool_maps_dedup = []
    for m in pool_maps:
        if m["hash"] not in seen:
            seen.add(m["hash"])
            pool_maps_dedup.append(m)

    # Brawlify未収録マップを手動定義から補充
    api_hashes = {m["hash"] for m in trio_maps}
    for mm in manual.get("manual_maps", []):
        h = mm.get("hash", "")
        if h in rotation and h not in seen:
            pool_maps_dedup.append({
                "id": mm.get("id"),
                "name": mm.get("name", ""),
                "name_jp": map_jp.get(h, ""),
                "hash": h,
                "image_url": mm.get("image_url"),
                "environment": mm.get("environment"),
                "disabled": False,
                "in_rotation_pool": True,
                "_source": "manual",
            })
            seen.add(h)

    write_json(OUT / "maps_trio_showdown.json", trio_maps)
    write_csv(
        OUT / "maps_trio_showdown.csv",
        trio_maps,
        ["id", "name", "name_jp", "hash", "image_url", "environment", "disabled", "in_rotation_pool"],
    )
    print(f"  -> {len(trio_maps)} trio showdown maps ({len(active_maps)} active, {len(pool_maps_dedup)} in pool)")

    # 2b. プール12 専用ファイル(現在のローテプール、deduped)
    write_json(OUT / "maps_pool.json", pool_maps_dedup)
    write_csv(
        OUT / "maps_pool.csv",
        pool_maps_dedup,
        ["id", "name", "name_jp", "hash", "image_url", "environment"],
    )

    # ティア・戦略テンプレはプールを使う(まだ揃ってなければ growing)
    target_maps = pool_maps_dedup if pool_maps_dedup else active_maps

    # 3. ティア記入用ワイド形式 CSV (rows=brawlers, columns=maps)
    print("Generating tier template (wide)...")
    map_cols = [m.get("name_jp") or m["name"] for m in target_maps]
    tier_headers = ["brawler_id", "brawler_name", "brawler_name_jp"] + map_cols
    tier_rows = []
    for b in brawlers:
        row = {
            "brawler_id": b["id"],
            "brawler_name": b["name"],
            "brawler_name_jp": b.get("name_jp", ""),
        }
        for col in map_cols:
            row[col] = ""
        tier_rows.append(row)
    write_csv(OUT / "brawler_tiers_wide.csv", tier_rows, tier_headers)
    print(f"  -> {len(tier_rows)} brawlers x {len(map_cols)} maps")

    # 4. マップ別戦略テンプレート
    print("Generating map strategies template...")
    strategy_headers = [
        "map_id",
        "map_name",
        "map_name_jp",
        "tank_line",
        "support_line",
        "flank_line",
        "opening_routes",
        "recommended_comps",
        "key_advice",
    ]
    strategy_rows = [
        {
            "map_id": m["id"],
            "map_name": m["name"],
            "map_name_jp": m.get("name_jp", ""),
            "tank_line": "",
            "support_line": "",
            "flank_line": "",
            "opening_routes": "",
            "recommended_comps": "",
            "key_advice": "",
        }
        for m in target_maps
    ]
    write_csv(OUT / "map_strategies.csv", strategy_rows, strategy_headers)
    print(f"  -> {len(strategy_rows)} map rows")

    # 進捗レポート
    missing = [h for h in rotation if h not in {m["hash"] for m in pool_maps_dedup}]
    print(f"\nMappings: {len(map_jp)} maps, {len(brawler_jp)} brawlers")
    if missing:
        print(f"  WARNING: {len(missing)} hashes in current_rotation_hashes are not in API: {missing}")
    print(f"\nDone. Output dir: {OUT}")


if __name__ == "__main__":
    main()
