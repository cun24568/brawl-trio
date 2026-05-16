"""🌓 と 🌗 のタグを探す + ブロウラー別マッチ間隔比較。"""
import sqlite3
import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def parse_bt(bt):
    try:
        return datetime.strptime(bt[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def analyze(tag, con, mode="trioShowdown", max_int=1800):
    rows = con.execute(
        "SELECT battle_time, brawler, rank, raw_json FROM battles "
        "WHERE tag = ? AND mode = ? ORDER BY battle_time",
        (tag, mode),
    ).fetchall()
    battles = []
    for r in rows:
        t = parse_bt(r["battle_time"])
        if t is None: continue
        try:
            raw = json.loads(r["raw_json"])
        except Exception:
            continue
        battles.append({
            "time": t,
            "duration": (raw.get("battle") or {}).get("duration", 0) or 0,
            "brawler": r["brawler"] or "",
            "rank": r["rank"] or 0,
        })
    by_br = defaultdict(list)
    picks = defaultdict(int)
    for i, b in enumerate(battles):
        picks[b["brawler"]] += 1
        if i == 0: continue
        gap = (b["time"] - battles[i-1]["time"]).total_seconds() - b["duration"]
        if 0 <= gap <= max_int:
            by_br[b["brawler"]].append(gap)
    all_gaps = [g for gs in by_br.values() for g in gs]
    return battles, picks, by_br, all_gaps


def main():
    con = sqlite3.connect("/home/soya/brawl-trio/data/users.db")
    con.row_factory = sqlite3.Row
    moon_chars = ["🌓", "🌗"]
    for ch in moon_chars:
        rows = con.execute(
            "SELECT tag, name, trophies, highest_trophies FROM watchlist WHERE name LIKE ?",
            (f"%{ch}%",),
        ).fetchall()
        for r in rows:
            n = r["name"]
            if n in moon_chars or len(n) <= 4:
                print(f"{r['tag']:<14} {r['name']:<10} tro={r['trophies']:>6} highest={r['highest_trophies']}")

    print()
    print("=== 比較する対象タグを直接指定: 🌓, 🌗, 🍣 ===")
    target_tags = []
    for ch in moon_chars + ["🍣"]:
        rows = con.execute(
            "SELECT tag, name FROM watchlist WHERE name = ?", (ch,)
        ).fetchall()
        for r in rows:
            target_tags.append((r["tag"], r["name"]))

    for tag, name in target_tags:
        battles, picks, by_br, all_gaps = analyze(tag, con)
        if not all_gaps:
            print(f"\n--- {name} ({tag}): データなし ---")
            continue
        med = statistics.median(all_gaps)
        prof_row = con.execute("SELECT profile_json FROM watchlist WHERE tag=?", (tag,)).fetchone()
        prof = json.loads(prof_row["profile_json"]) if prof_row and prof_row["profile_json"] else {}
        tro = prof.get("trophies", "?")
        elo = prof.get("rankedElo", "?")
        rk = prof.get("rankedRankName", "?")
        h_elo = prof.get("highestAllTimeRankedElo", "?")
        print(f"\n--- {name} ({tag}) tro={tro} ガチ={rk} Elo={elo} (最高{h_elo}) ---")
        print(f"全 trio battles: {len(battles)}, gap N={len(all_gaps)}, 中央値={med:.0f}s")
        print(f"{'brawler':<14} {'picks':<7} {'gap_n':<6} {'median':<8} {'mean':<8}")
        by_picks = sorted(by_br.items(), key=lambda x: -picks[x[0]])
        for br, gaps in by_picks:
            if picks[br] < 3 or len(gaps) < 2: continue
            m = statistics.median(gaps)
            d = m - med
            bar = "█" * int(m / 30)
            print(f"  {br:<12} {picks[br]:>5}  {len(gaps):>5}  {m:>5.0f}s ({d:+.0f}s)  {bar}")


if __name__ == "__main__":
    main()
