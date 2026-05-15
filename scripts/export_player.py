"""指定プレイヤータグの全モードバトルログを SQLite (users.db) から抽出し CSV/Parquet 出力。

使い方:
  python scripts/export_player.py "#YQ8YY09R"
    → out/player_YQ8YY09R.csv 生成

  python scripts/export_player.py "#YQ8YY09R" --format parquet
    → out/player_YQ8YY09R.parquet

  python scripts/export_player.py "#YQ8YY09R" --since 20260501T000000.000Z
    → 指定日時以降のみ

出力カラム:
  battle_time, battle_time_iso, mode, map, brawler, rank, trophy_change,
  duration, type, team_size, players_count,
  my_team_tags, my_team_brawlers, my_team_trophies,
  enemy_summary, raw_json
"""
import argparse
import csv
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


def normalize_tag(tag: str) -> str:
    t = (tag or "").strip().upper()
    if not t.startswith("#"):
        t = "#" + t
    return t


def battle_time_to_iso(bt: str) -> str:
    """20260509T141824.000Z → 2026-05-09T14:18:24+00:00"""
    try:
        d = datetime.strptime(bt[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        return d.isoformat()
    except Exception:
        return bt


def extract_row(tag: str, row: sqlite3.Row) -> dict:
    raw = {}
    try:
        raw = json.loads(row["raw_json"])
    except Exception:
        pass
    battle = (raw.get("battle") or {})
    event = (raw.get("event") or {})

    teams = battle.get("teams") or []
    players = battle.get("players") or []  # solo

    my_team_tags = []
    my_team_brawlers = []
    my_team_trophies = []
    enemy_summary = []  # list of [enemy_brawler, enemy_trophies]

    if teams:
        my_idx = None
        for i, team in enumerate(teams):
            if any(p.get("tag") == tag for p in team):
                my_idx = i
                break
        for i, team in enumerate(teams):
            if i == my_idx:
                for p in team:
                    my_team_tags.append(p.get("tag", ""))
                    br = (p.get("brawler") or {})
                    my_team_brawlers.append(br.get("name", ""))
                    my_team_trophies.append(br.get("trophies", 0))
            else:
                for p in team:
                    br = (p.get("brawler") or {})
                    enemy_summary.append([br.get("name", ""), br.get("trophies", 0)])
    elif players:
        # solo の場合 teams 構造なし
        for p in players:
            if p.get("tag") == tag:
                my_team_tags.append(p.get("tag", ""))
                br = (p.get("brawler") or {})
                my_team_brawlers.append(br.get("name", ""))
                my_team_trophies.append(br.get("trophies", 0))
            else:
                br = (p.get("brawler") or {})
                enemy_summary.append([br.get("name", ""), br.get("trophies", 0)])

    return {
        "battle_time": row["battle_time"],
        "battle_time_iso": battle_time_to_iso(row["battle_time"]),
        "mode": row["mode"] or "",
        "map": row["map"] or "",
        "brawler": row["brawler"] or "",
        "rank": row["rank"] or 0,
        "trophy_change": battle.get("trophyChange", 0),
        "duration": battle.get("duration", 0),
        "type": battle.get("type", ""),
        "team_size": len(my_team_tags),
        "players_count": (sum(len(t) for t in teams) if teams else len(players)),
        "my_team_tags": "|".join(my_team_tags),
        "my_team_brawlers": "|".join(my_team_brawlers),
        "my_team_trophies": "|".join(map(str, my_team_trophies)),
        "enemy_summary": json.dumps(enemy_summary, ensure_ascii=False),
        "raw_json": row["raw_json"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tag", help="player tag (e.g. #YQ8YY09R)")
    ap.add_argument("--db", default=str(Path(__file__).parent.parent / "data" / "users.db"))
    ap.add_argument("--out-dir", default=str(Path(__file__).parent.parent / "out"))
    ap.add_argument("--since", default=None, help="battle_time lower bound (e.g. 20260501T000000.000Z)")
    ap.add_argument("--format", choices=["csv", "parquet"], default="csv")
    args = ap.parse_args()

    tag = normalize_tag(args.tag)
    db_path = Path(args.db)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not db_path.exists():
        sys.exit(f"DB not found: {db_path}")

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    where = "tag = ?"
    params = [tag]
    if args.since:
        where += " AND battle_time >= ?"
        params.append(args.since)
    rows = con.execute(
        f"SELECT battle_time, mode, map, brawler, rank, raw_json "
        f"FROM battles WHERE {where} ORDER BY battle_time ASC",
        params,
    ).fetchall()
    if not rows:
        sys.exit(f"no battles for {tag}")

    records = [extract_row(tag, r) for r in rows]
    safe_tag = tag.lstrip("#")
    if args.format == "csv":
        out_path = out_dir / f"player_{safe_tag}.csv"
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(records[0].keys()))
            w.writeheader()
            w.writerows(records)
    else:
        try:
            import pandas as pd
        except ImportError:
            sys.exit("parquet 出力には pandas が必要: pip install pandas pyarrow")
        df = pd.DataFrame(records)
        out_path = out_dir / f"player_{safe_tag}.parquet"
        df.to_parquet(out_path, index=False)
    print(f"wrote {len(records)} rows to {out_path}")
    # mode distribution
    from collections import Counter
    cnt = Counter(r["mode"] for r in records)
    print("mode distribution:")
    for m, n in cnt.most_common():
        print(f"  {n:>6}  {m}")


if __name__ == "__main__":
    main()
