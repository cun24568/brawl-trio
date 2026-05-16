"""🍣 のシリウス + 他「highest高めだが db.battles に少ない」 キャラを確認。"""
import sqlite3
import json

con = sqlite3.connect("/home/soya/brawl-trio/data/users.db")
row = con.execute("SELECT profile_json FROM watchlist WHERE tag=?", ("#YQ8YY09R",)).fetchone()
p = json.loads(row[0])

print("=== 🍣 SIRIUS (公式APIプロフィール) ===")
for b in p.get("brawlers", []):
    if "SIRIUS" in b.get("name", "").upper():
        print(json.dumps(b, indent=2, ensure_ascii=False))
        break

# キャラ別使用回数 (DB保存分)
counts = dict(con.execute(
    "SELECT brawler, COUNT(*) FROM battles WHERE tag=? AND mode='trioShowdown' GROUP BY brawler",
    ("#YQ8YY09R",)
).fetchall())

print("\n=== 全キャラ: highest順 + DB使用回数 ===")
brawlers = []
for b in p.get("brawlers", []):
    n = b["name"]
    h = b.get("highestTrophies", 0)
    c = b.get("trophies", 0)
    used = counts.get(n, 0)
    pl = b.get("prestigeLevel", 0)
    ms = b.get("maxWinStreak", 0)
    cs = b.get("currentWinStreak", 0)
    brawlers.append((n, h, c, used, pl, ms, cs))

brawlers.sort(key=lambda x: -x[1])
print(f"{'name':<14} {'hi':<6} {'cur':<6} {'db_used':<8} {'prest':<6} {'maxStrk':<8} {'curStrk':<6}")
for n, h, c, u, pl, ms, cs in brawlers[:20]:
    flag = " ★sub-only" if u == 0 and h >= 1500 else ""
    print(f"{n:<14} {h:>5}  {c:>5}  {u:>6}    {pl:>4}    {ms:>5}    {cs:>5}{flag}")
