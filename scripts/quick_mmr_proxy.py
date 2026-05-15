"""簡易MMR共通性チェック (Phase 1 暫定版)

仮説: 累計勝利数(3v3/solo/duo) と トリオtop2率 の相関が高い ⇒ モード共通スキル ⇒ 共通MMR傍証
低相関ならモード別MMR寄り。

ssh soya@vps 'python3 /home/soya/brawl-trio/scripts/quick_mmr_proxy.py' で実行。
"""
import sqlite3
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / "data" / "users.db"
ENV_PATH = ROOT / ".env"


def load_token():
    if not ENV_PATH.exists():
        return None
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("BRAWL_API_TOKEN="):
            return line.split("=", 1)[1].strip()
    return None


def fetch_profile(token, tag):
    enc = tag.lstrip("#").replace("#", "")
    req = urllib.request.Request(
        f"https://api.brawlstars.com/v1/players/%23{enc}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read())


def spearman(x, y):
    n = len(x)
    if n < 3:
        return None
    rx = sorted(range(n), key=lambda i: x[i])
    ry = sorted(range(n), key=lambda i: y[i])
    rank_x = [0] * n
    rank_y = [0] * n
    for i, idx in enumerate(rx):
        rank_x[idx] = i
    for i, idx in enumerate(ry):
        rank_y[idx] = i
    mean_x = sum(rank_x) / n
    mean_y = sum(rank_y) / n
    cov = sum((rank_x[i] - mean_x) * (rank_y[i] - mean_y) for i in range(n))
    var_x = (sum((rank_x[i] - mean_x) ** 2 for i in range(n))) ** 0.5
    var_y = (sum((rank_y[i] - mean_y) ** 2 for i in range(n))) ** 0.5
    if var_x == 0 or var_y == 0:
        return None
    return cov / (var_x * var_y)


def main():
    token = load_token()
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT tag, profile_json FROM watchlist").fetchall()
    print(f"watchlist total: {len(rows)}")
    data = []
    fetched_now = 0
    for r in rows:
        tag = r["tag"]
        p = None
        if r["profile_json"]:
            try:
                p = json.loads(r["profile_json"])
            except Exception:
                p = None
        if p is None and token:
            try:
                p = fetch_profile(token, tag)
                con.execute(
                    "UPDATE watchlist SET profile_json=? WHERE tag=?",
                    (json.dumps(p, ensure_ascii=False), tag),
                )
                con.commit()
                fetched_now += 1
            except Exception:
                continue
        if p is None:
            continue
        t = con.execute(
            "SELECT COUNT(*) AS total, SUM(CASE WHEN rank<=2 THEN 1 ELSE 0 END) AS top2, AVG(CAST(rank AS REAL)) AS avg_rank "
            "FROM battles WHERE tag=? AND mode='trioShowdown'",
            (tag,),
        ).fetchone()
        total = t["total"] or 0
        if total < 30:
            continue
        data.append({
            "tag": tag,
            "name": p.get("name", "?")[:25],
            "trophies": p.get("trophies", 0),
            "v3v3": p.get("3vs3Victories", 0) or 0,
            "vSolo": p.get("soloVictories", 0) or 0,
            "vDuo": p.get("duoVictories", 0) or 0,
            "expLevel": p.get("expLevel", 0) or 0,
            "trio_top2_rate": (t["top2"] or 0) / total,
            "trio_avg_rank": t["avg_rank"] or 0,
            "trio_total": total,
        })
    if fetched_now:
        print(f"(fetched {fetched_now} new profiles from official API)")
    print(f"analyzable players (>=30 trio + profile): {len(data)}")
    if len(data) < 10:
        print("サンプル不足 (10未満)")
        return

    for d in data:
        L = max(d["expLevel"], 1)
        d["v3v3_per_lvl"] = d["v3v3"] / L
        d["vSolo_per_lvl"] = d["vSolo"] / L
        d["vDuo_per_lvl"] = d["vDuo"] / L

    yvar = [d["trio_top2_rate"] for d in data]
    print(f"\n=== Spearman correlation with trio_top2_rate (N={len(data)}) ===")
    for key in ["v3v3", "vSolo", "vDuo", "trophies", "expLevel", "v3v3_per_lvl", "vSolo_per_lvl", "vDuo_per_lvl"]:
        xvar = [d[key] for d in data]
        r = spearman(xvar, yvar)
        if r is None:
            print(f"  {key:<18}: -")
            continue
        sig = "***" if abs(r) >= 0.5 else "**" if abs(r) >= 0.3 else "*" if abs(r) >= 0.15 else ""
        print(f"  {key:<18}: rho={r:+.3f} {sig}")

    print("\n=== 上位/下位プレイヤー (trio_top2_rate順) ===")
    data.sort(key=lambda d: -d["trio_top2_rate"])
    header_name = "name"
    header_top2 = "top2%"
    header_3v3 = "3v3"
    header_solo = "solo"
    header_duo = "duo"
    header_tro = "trophies"
    header_lv = "Lv"
    print(f"{header_name:<28} {header_top2:<7} {header_3v3:<8} {header_solo:<6} {header_duo:<7} {header_tro:<9} {header_lv:<5}")
    for d in data[:5] + data[-5:]:
        nm = (d["name"] + "...")[:25] if len(d["name"]) > 25 else d["name"]
        print(f"{nm:<28} {d['trio_top2_rate']*100:>5.1f}%  {d['v3v3']:>7}  {d['vSolo']:>5}  {d['vDuo']:>6}  {d['trophies']:>8}  {d['expLevel']:>4}")

    print("\n解釈:")
    print("  rho > 0.5  : 強い正相関 → モード共通スキル/MMRの可能性大")
    print("  rho 0.2-0.5: 中程度    → 部分的にモード共通")
    print("  rho < 0.2  : 弱/無相関 → モード別MMR寄り")
    print("\n注: これは累計データによる代理指標。 厳密な共通MMR判定は Phase 1 本番 (時系列分析) 必須。")


if __name__ == "__main__":
    main()
