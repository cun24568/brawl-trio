"""SQLite wrapper for user watchlist + battlelog storage.

スキーマ:
  watchlist: タグごとの登録情報 (50タグ上限、先着、満杯時は最古退役)
  battles:   タグごとのバトロワ試合履歴 (PK で重複排除)
  fetch_log: 取得履歴 (30分クールダウン判定 + デバッグ)
"""
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "users.db"
MAX_WATCHLIST = 50000  # 受付枠 (実際にcronで回るのはアクティブタグのみ、下記参照)
ACTIVE_WINDOW_DAYS = 28  # cron対象: 過去28日以内に取得実績のあるタグだけ
COOLDOWN_SECONDS = 30 * 60  # 30分


def normalize_tag(tag: str) -> str:
    """'#YQ8YY09R' or 'yq8yy09r' → '#YQ8YY09R'"""
    t = tag.strip().upper()
    if not t.startswith("#"):
        t = "#" + t
    return t


@contextmanager
def conn():
    DB_PATH.parent.mkdir(exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db():
    with conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS watchlist (
                tag TEXT PRIMARY KEY,
                registered_at INTEGER NOT NULL,
                last_fetched_at INTEGER,
                name TEXT,
                trophies INTEGER,
                highest_trophies INTEGER
            );
            CREATE TABLE IF NOT EXISTS battles (
                tag TEXT NOT NULL,
                battle_time TEXT NOT NULL,
                mode TEXT,
                map TEXT,
                brawler TEXT,
                rank INTEGER,
                raw_json TEXT,
                PRIMARY KEY (tag, battle_time)
            );
            CREATE INDEX IF NOT EXISTS idx_battles_tag_mode ON battles(tag, mode);
            CREATE INDEX IF NOT EXISTS idx_battles_tag_map ON battles(tag, map);
            CREATE INDEX IF NOT EXISTS idx_battles_tag_brawler ON battles(tag, brawler);
            CREATE TABLE IF NOT EXISTS fetch_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tag TEXT NOT NULL,
                fetched_at INTEGER NOT NULL,
                new_battles INTEGER NOT NULL,
                error TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_fetch_log_tag_time ON fetch_log(tag, fetched_at DESC);
        """)
        # 既存DBへのカラム追加 (一度きり)
        for col_sql in [
            "ALTER TABLE watchlist ADD COLUMN highest_trophies INTEGER",
            "ALTER TABLE watchlist ADD COLUMN profile_json TEXT",
        ]:
            try:
                c.execute(col_sql)
            except sqlite3.OperationalError:
                pass


def add_to_watchlist(
    tag: str,
    name: str = None,
    trophies: int = None,
    highest_trophies: int = None,
    profile_json: str = None,
) -> tuple[bool, str]:
    """ウォッチリストに追加 / 既登録なら名前・トロフィー・プロフィール更新。"""
    tag = normalize_tag(tag)
    now = int(time.time())
    with conn() as c:
        existing = c.execute("SELECT tag FROM watchlist WHERE tag=?", (tag,)).fetchone()
        if existing:
            if name or trophies is not None or highest_trophies is not None or profile_json is not None:
                c.execute(
                    "UPDATE watchlist SET name=COALESCE(?,name), trophies=COALESCE(?,trophies), highest_trophies=COALESCE(?,highest_trophies), profile_json=COALESCE(?,profile_json) WHERE tag=?",
                    (name, trophies, highest_trophies, profile_json, tag),
                )
            return True, "既に登録済み"
        count = c.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0]
        if count >= MAX_WATCHLIST:
            victim = c.execute(
                "SELECT tag FROM watchlist ORDER BY COALESCE(last_fetched_at, registered_at) ASC LIMIT 1"
            ).fetchone()
            if victim:
                c.execute("DELETE FROM watchlist WHERE tag=?", (victim["tag"],))
        c.execute(
            "INSERT INTO watchlist (tag, registered_at, name, trophies, highest_trophies, profile_json) VALUES (?, ?, ?, ?, ?, ?)",
            (tag, now, name, trophies, highest_trophies, profile_json),
        )
        return True, "登録完了"


def get_watchlist() -> list[dict]:
    with conn() as c:
        rows = c.execute(
            "SELECT tag, registered_at, last_fetched_at, name, trophies FROM watchlist ORDER BY registered_at ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_active_watchlist() -> list[dict]:
    """cronで回す対象: 過去ACTIVE_WINDOW_DAYS日以内に取得実績ありのタグ。
    新規登録 (last_fetched_at IS NULL) も含める (初回クロール猶予)。
    """
    cutoff = int(time.time()) - ACTIVE_WINDOW_DAYS * 86400
    with conn() as c:
        rows = c.execute(
            """SELECT tag, registered_at, last_fetched_at, name, trophies
               FROM watchlist
               WHERE last_fetched_at IS NULL OR last_fetched_at >= ?
               ORDER BY COALESCE(last_fetched_at, registered_at) ASC""",
            (cutoff,),
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_battles(tag: str, battles: list[dict]) -> int:
    """battlelog の各試合を保存。重複は INSERT OR IGNORE で無視。
    各 battle dict は公式APIのフォーマット。
    返値: 新規挿入数
    """
    tag = normalize_tag(tag)
    inserted = 0
    with conn() as c:
        for b in battles:
            bt = b.get("battleTime", "")
            if not bt:
                continue
            ev = b.get("event", {}) or {}
            mode = ev.get("mode", "")
            mp = ev.get("map", "")
            battle = b.get("battle", {}) or {}
            # 自分のブロウラーと順位を抽出
            brawler, rank = _extract_self(tag, battle)
            cur = c.execute(
                """INSERT OR IGNORE INTO battles
                   (tag, battle_time, mode, map, brawler, rank, raw_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (tag, bt, mode, mp, brawler, rank, json.dumps(b, ensure_ascii=False)),
            )
            if cur.rowcount:
                inserted += 1
        # last_fetched_at 更新 (watchlist にいれば)
        c.execute(
            "UPDATE watchlist SET last_fetched_at=? WHERE tag=?",
            (int(time.time()), tag),
        )
    return inserted


def _extract_self(tag: str, battle: dict) -> tuple[str, int]:
    """全モード対応: battle.teams (trio/duo/3v3) または battle.players (solo) から
    自分のブロウラーと順位を取り出す。 3v3 のような順位なしモードは rank=0。"""
    rank = battle.get("rank") or 0
    teams = battle.get("teams") or []
    for team in teams:
        for p in team:
            if p.get("tag") == tag:
                return (p.get("brawler") or {}).get("name", ""), rank
    players = battle.get("players") or []
    for p in players:
        if p.get("tag") == tag:
            return (p.get("brawler") or {}).get("name", ""), rank
    return "", rank


def log_fetch(tag: str, new_battles: int, error: str = None):
    tag = normalize_tag(tag)
    with conn() as c:
        c.execute(
            "INSERT INTO fetch_log (tag, fetched_at, new_battles, error) VALUES (?, ?, ?, ?)",
            (tag, int(time.time()), new_battles, error),
        )


def last_fetch_time(tag: str) -> int | None:
    tag = normalize_tag(tag)
    with conn() as c:
        row = c.execute(
            "SELECT fetched_at FROM fetch_log WHERE tag=? AND error IS NULL ORDER BY fetched_at DESC LIMIT 1",
            (tag,),
        ).fetchone()
        return row["fetched_at"] if row else None


def cooldown_remaining(tag: str) -> int:
    """次回更新可能までの残り秒。0なら即時更新OK。"""
    last = last_fetch_time(tag)
    if not last:
        return 0
    elapsed = int(time.time()) - last
    return max(0, COOLDOWN_SECONDS - elapsed)


def get_player_matchups(tag: str, since: str | None = None, min_seen: int = 5) -> dict:
    """対面相性分析: 自分が使ったブロウラー別に「敵チームに居たブロウラー」 を集計。
    返値: {
      "by_my_brawler": [{my_brawler, enemy_brawler, seen, top2, top2_rate, avg_rank}, ...],
      "global": [{enemy_brawler, seen, top2_rate, avg_rank}, ...]  // 自ブロウラー無視の総合
    }
    """
    tag = normalize_tag(tag)
    extra = " AND mode = 'trioShowdown'"
    params: list = [tag]
    if since:
        extra += " AND battle_time >= ?"
        params.append(since)
    with conn() as c:
        rows = c.execute(
            f"SELECT brawler AS my_brawler, rank, raw_json FROM battles WHERE tag=?{extra}",
            params,
        ).fetchall()

    # 集計: (my_brawler, enemy_brawler) → {seen, top2, rank_sum}
    by_pair = {}
    by_enemy = {}
    for r in rows:
        my = r["my_brawler"] or ""
        rk = r["rank"] or 0
        try:
            raw = json.loads(r["raw_json"])
        except Exception:
            continue
        teams = (raw.get("battle") or {}).get("teams") or []
        # 自分のチームを特定
        my_idx = None
        for i, team in enumerate(teams):
            if any(p.get("tag") == tag for p in team):
                my_idx = i
                break
        if my_idx is None:
            continue
        # 敵チームのbrawlersを抽出 (重複除外: 同じbrawlerが複数チームに居たら1回扱い)
        enemy_brawlers = set()
        for i, team in enumerate(teams):
            if i == my_idx:
                continue
            for p in team:
                br = (p.get("brawler") or {}).get("name", "")
                if br:
                    enemy_brawlers.add(br)
        for eb in enemy_brawlers:
            k = (my, eb)
            s = by_pair.get(k) or {"seen": 0, "top2": 0, "rank_sum": 0}
            s["seen"] += 1
            if rk <= 2:
                s["top2"] += 1
            s["rank_sum"] += rk
            by_pair[k] = s

            ge = by_enemy.get(eb) or {"seen": 0, "top2": 0, "rank_sum": 0}
            ge["seen"] += 1
            if rk <= 2:
                ge["top2"] += 1
            ge["rank_sum"] += rk
            by_enemy[eb] = ge

    by_my = []
    for (my, eb), s in by_pair.items():
        if s["seen"] < min_seen:
            continue
        by_my.append({
            "my_brawler": my,
            "enemy_brawler": eb,
            "seen": s["seen"],
            "top2": s["top2"],
            "top2_rate": s["top2"] / s["seen"],
            "avg_rank": s["rank_sum"] / s["seen"],
        })
    by_my.sort(key=lambda x: x["avg_rank"])
    glob = []
    for eb, s in by_enemy.items():
        if s["seen"] < min_seen:
            continue
        glob.append({
            "enemy_brawler": eb,
            "seen": s["seen"],
            "top2_rate": s["top2"] / s["seen"],
            "avg_rank": s["rank_sum"] / s["seen"],
        })
    glob.sort(key=lambda x: -x["avg_rank"])  # 苦手 (avg_rank高い) が上
    return {"by_my_brawler": by_my, "global": glob}


def get_player_stats(tag: str, since: str | None = None) -> dict:
    """そのタグのトリオサバイバル集計データを返す (全モード保存後も既存挙動維持: trioShowdownフィルタ)。
    since: battle_time の下限 (YYYYMMDDTHHMMSS.000Z 形式)、 None なら全期間。"""
    tag = normalize_tag(tag)
    extra = " AND mode = 'trioShowdown'"
    base_params = [tag]
    if since:
        extra += " AND battle_time >= ?"
        base_params.append(since)

    with conn() as c:
        summary = c.execute(
            f"""SELECT
                  COUNT(*) AS total,
                  SUM(CASE WHEN rank<=2 THEN 1 ELSE 0 END) AS top2,
                  SUM(CASE WHEN rank=1 THEN 1 ELSE 0 END) AS rank1,
                  AVG(CAST(rank AS REAL)) AS avg_rank,
                  MIN(battle_time) AS first_battle,
                  MAX(battle_time) AS last_battle
                FROM battles WHERE tag=?{extra}""",
            base_params,
        ).fetchone()

        brawlers = c.execute(
            f"""SELECT brawler, COUNT(*) AS picks,
                       SUM(CASE WHEN rank<=2 THEN 1 ELSE 0 END) AS top2,
                       SUM(CASE WHEN rank=1 THEN 1 ELSE 0 END) AS rank1,
                       AVG(CAST(rank AS REAL)) AS avg_rank
                FROM battles WHERE tag=?{extra} AND brawler != ''
                GROUP BY brawler ORDER BY picks DESC LIMIT 50""",
            base_params,
        ).fetchall()

        maps = c.execute(
            f"""SELECT map, COUNT(*) AS picks,
                       SUM(CASE WHEN rank<=2 THEN 1 ELSE 0 END) AS top2,
                       SUM(CASE WHEN rank=1 THEN 1 ELSE 0 END) AS rank1,
                       AVG(CAST(rank AS REAL)) AS avg_rank
                FROM battles WHERE tag=?{extra} AND map != ''
                GROUP BY map ORDER BY picks DESC""",
            base_params,
        ).fetchall()

        brawler_map = c.execute(
            f"""SELECT brawler, map, COUNT(*) AS picks,
                       SUM(CASE WHEN rank<=2 THEN 1 ELSE 0 END) AS top2,
                       AVG(CAST(rank AS REAL)) AS avg_rank
                FROM battles WHERE tag=?{extra} AND brawler != '' AND map != ''
                GROUP BY brawler, map HAVING picks >= 3""",
            base_params,
        ).fetchall()

    return {
        "summary": dict(summary) if summary else {},
        "brawlers": [dict(r) for r in brawlers],
        "maps": [dict(r) for r in maps],
        "brawler_map": [dict(r) for r in brawler_map],
    }


def import_historical_battles(tag: str, jsonl_path) -> int:
    """全体クロールが蓄積している trio_battles.jsonl から該当タグの試合を抽出 → battles テーブルに upsert。
    INSERT OR IGNORE なので既存と重複しない。返値: 新規挿入数。
    """
    tag = normalize_tag(tag)
    jsonl_path = Path(jsonl_path)
    if not jsonl_path.exists():
        return 0
    tag_marker = f'"{tag}"'  # 文字列 pre-filter で高速化
    matches = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            if tag_marker not in line:
                continue
            try:
                b = json.loads(line)
            except Exception:
                continue
            teams = (b.get("battle") or {}).get("teams") or []
            in_teams = any(
                p.get("tag") == tag for team in teams for p in team
            )
            if in_teams:
                matches.append(b)
    if not matches:
        return 0
    return upsert_battles(tag, matches)


def get_player_battles(
    tag: str,
    limit: int = 60,
    offset: int = 0,
    brawler: str | None = None,
    map_name: str | None = None,
    rank: int | None = None,
) -> list[dict]:
    """そのタグの試合履歴を新しい順に返す。任意のフィルタ (brawler/map/rank) 対応。"""
    tag = normalize_tag(tag)
    where = ["tag = ?", "mode = 'trioShowdown'"]
    params: list = [tag]
    if brawler:
        where.append("brawler = ?")
        params.append(brawler)
    if map_name:
        where.append("map = ?")
        params.append(map_name)
    if rank is not None:
        where.append("rank = ?")
        params.append(int(rank))
    params.extend([limit, offset])
    where_sql = " AND ".join(where)
    with conn() as c:
        rows = c.execute(
            f"""SELECT battle_time, mode, map, brawler, rank, raw_json
               FROM battles WHERE {where_sql}
               ORDER BY battle_time DESC LIMIT ? OFFSET ?""",
            params,
        ).fetchall()

    result = []
    for r in rows:
        raw = json.loads(r["raw_json"])
        battle = raw.get("battle") or {}
        teams = battle.get("teams") or []
        # 自分のチーム index を特定
        my_idx = None
        for i, team in enumerate(teams):
            if any(p.get("tag") == tag for p in team):
                my_idx = i
                break
        my_team = []
        enemy_teams = []
        for i, team in enumerate(teams):
            members = [
                {
                    "tag": p.get("tag", ""),
                    "name": p.get("name", ""),
                    "brawler": (p.get("brawler") or {}).get("name", ""),
                    "trophies": (p.get("brawler") or {}).get("trophies", 0),
                }
                for p in team
            ]
            if i == my_idx:
                my_team = members
            else:
                enemy_teams.append(members)
        result.append({
            "battle_time": r["battle_time"],
            "mode": r["mode"],
            "map": r["map"],
            "brawler": r["brawler"] or "",
            "rank": r["rank"],
            "trophy_change": battle.get("trophyChange", 0),
            "duration": battle.get("duration", 0),
            "type": battle.get("type", ""),
            "my_team": my_team,
            "enemy_teams": enemy_teams,
        })
    return result


if __name__ == "__main__":
    init_db()
    print(f"DB initialized at {DB_PATH}")
    print(f"Watchlist size: {len(get_watchlist())}/{MAX_WATCHLIST}")
