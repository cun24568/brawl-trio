"""FastAPI サーバ: ユーザータグ単位のトリオサバイバル戦績API。

エンドポイント:
  GET  /api/player/{tag}        集計結果を返す (キャッシュ済データ)
  POST /api/player/{tag}/refresh 強制更新 (30分クールダウン)
  GET  /api/watchlist           現在のウォッチリスト一覧 (デバッグ/管理)
  GET  /api/health              ヘルスチェック
"""
import sys
import time
from pathlib import Path
from urllib.error import HTTPError

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# ローカルimport
sys.path.insert(0, str(Path(__file__).parent))
import brawl_api  # noqa: E402
import db  # noqa: E402

ALLOWED_ORIGINS = [
    "https://brawl-showdown.com",
    "https://www.brawl-showdown.com",
    "https://brawl-trio.vercel.app",
    "http://localhost:8000",
    "http://localhost:5173",
    "http://127.0.0.1:8000",
]

limiter = Limiter(key_func=get_remote_address, default_limits=["30/minute"])
app = FastAPI(title="brawl-trio user API", version="1.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    allow_credentials=False,
)


@app.on_event("startup")
def _startup():
    db.init_db()
    # 名前検索インデックスは初回検索リクエスト時 on-demand 構築 (起動時の jsonl 745MB 全読込を回避)
    # クラブインデックスは小さい (各国TOP200のみ) のでそのまま background 起動
    import threading as _t
    _t.Thread(target=_build_club_index, daemon=True).start()


@app.get("/api/health")
def health():
    return {"ok": True, "ts": int(time.time())}


# ============================================================
# 名前検索インデックス
# ============================================================
import json
import os
import threading
from urllib.parse import quote

_PLAYER_INDEX = None  # list[(name_lower, name, tag, trophies)]
_PLAYER_INDEX_LOCK = threading.Lock()
_PLAYER_INDEX_BUILT_AT = 0
_JSONL_PATH = Path(__file__).parent.parent / "data" / "trio_battles.jsonl"

_CLUB_INDEX = []  # list of dict {tag, name, trophies, country}
_CLUB_INDEX_BUILT_AT = 0
_CLUB_INDEX_REFRESH_SEC = 12 * 3600  # 12h


import re as _re
_INVISIBLE_RE = _re.compile(r'[\s ᅠ　⠀​‌‍⁠﻿]')


def _is_valid_name(s: str) -> bool:
    """空文字 / 全角スペース / ブレイル空白等の不可視文字だけのnameを除外"""
    if not s:
        return False
    cleaned = _INVISIBLE_RE.sub("", s)
    return len(cleaned) > 0


def _build_player_index():
    """jsonl 全件 streaming で (name → tag) を収集。
    各タグは「最新の trophies」と「最新の name」で1エントリ。
    名前が空白系のみのプレイヤーは除外。"""
    global _PLAYER_INDEX, _PLAYER_INDEX_BUILT_AT
    with _PLAYER_INDEX_LOCK:
        if not _JSONL_PATH.exists():
            _PLAYER_INDEX = []
            _PLAYER_INDEX_BUILT_AT = int(time.time())
            return
        latest = {}  # tag → (name, trophies)
        with open(_JSONL_PATH, encoding="utf-8") as f:
            for line in f:
                try:
                    b = json.loads(line)
                except Exception:
                    continue
                teams = (b.get("battle") or {}).get("teams") or []
                for team in teams:
                    for p in team:
                        ptag = p.get("tag")
                        pname = p.get("name", "")
                        ptro = (p.get("brawler") or {}).get("trophies", 0)
                        if not ptag or not _is_valid_name(pname):
                            continue
                        latest[ptag] = (pname, ptro)
        index = []
        for tag, (name, tro) in latest.items():
            index.append((name.lower(), name, tag, tro))
        _PLAYER_INDEX = index
        _PLAYER_INDEX_BUILT_AT = int(time.time())


@app.get("/api/search/players")
@limiter.limit("30/minute")
def search_players(request: Request, q: str = "", limit: int = 30):
    """プレイヤー名で部分一致検索 (case insensitive)。
    完全一致 → 開始一致 → 部分一致 の順 (各群はトロフィー降順)。"""
    if _PLAYER_INDEX is None:
        _build_player_index()
    q = (q or "").strip().lower()
    if not q:
        return {"results": [], "total": 0, "query": q}
    if limit > 100:
        limit = 100
    exact = []
    starts = []
    contains = []
    for name_lower, name, tag, tro in _PLAYER_INDEX:
        item = {"tag": tag, "name": name, "trophies": tro}
        if name_lower == q:
            exact.append(item)
        elif name_lower.startswith(q):
            starts.append(item)
        elif q in name_lower:
            contains.append(item)
    exact.sort(key=lambda x: -x["trophies"])
    starts.sort(key=lambda x: -x["trophies"])
    contains.sort(key=lambda x: -x["trophies"])
    merged = exact + starts + contains
    return {"results": merged[:limit], "total": len(merged), "query": q}


@app.post("/api/search/players/rebuild")
@limiter.limit("2/minute")
def rebuild_player_index(request: Request):
    _build_player_index()
    return {
        "ok": True,
        "size": len(_PLAYER_INDEX) if _PLAYER_INDEX else 0,
        "built_at": _PLAYER_INDEX_BUILT_AT,
    }


def _build_club_index():
    """各国クラブランキングからクラブ名インデックスを作成。"""
    global _CLUB_INDEX, _CLUB_INDEX_BUILT_AT
    countries = ["global", "JP", "KR", "US", "TW", "DE", "BR", "MX", "GB"]
    seen = {}
    for country in countries:
        try:
            data = brawl_api.fetch(f"/rankings/{country}/clubs")
        except Exception:
            continue
        for c in data.get("items", []):
            ctag = c.get("tag")
            if not ctag:
                continue
            existing = seen.get(ctag)
            if not existing or c.get("trophies", 0) > existing.get("trophies", 0):
                seen[ctag] = {
                    "tag": ctag,
                    "name": c.get("name", ""),
                    "trophies": c.get("trophies", 0),
                    "country": country,
                }
    _CLUB_INDEX = list(seen.values())
    _CLUB_INDEX_BUILT_AT = int(time.time())


@app.get("/api/search/clubs")
@limiter.limit("30/minute")
def search_clubs(request: Request, q: str = "", limit: int = 30):
    """クラブ名で部分一致検索。 各国TOP200クラブのみ対象 (公式API制限)。"""
    global _CLUB_INDEX_BUILT_AT
    now = int(time.time())
    if not _CLUB_INDEX or now - _CLUB_INDEX_BUILT_AT > _CLUB_INDEX_REFRESH_SEC:
        _build_club_index()
    q = (q or "").strip().lower()
    if not q:
        return {"results": [], "total": 0, "query": q}
    matches = [c for c in _CLUB_INDEX if q in c["name"].lower()]
    matches.sort(key=lambda x: -x["trophies"])
    return {"results": matches[:limit], "total": len(matches), "query": q, "index_size": len(_CLUB_INDEX)}


@app.get("/api/watchlist")
@limiter.limit("10/minute")
def watchlist(request: Request):
    return {"watchlist": db.get_watchlist(), "max": db.MAX_WATCHLIST}


def _normalize_or_400(tag: str) -> str:
    tag = db.normalize_tag(tag)
    # ブロウラータグは英数字のみ、長さ ~3-15
    body = tag[1:] if tag.startswith("#") else tag
    if not body or not body.isalnum() or len(body) > 15:
        raise HTTPException(status_code=400, detail="invalid tag format")
    return tag


def _fetch_and_save(tag: str) -> tuple[int, int]:
    """battlelog 取得 → トリオ抽出 → SQLite保存。
    返値: (新規保存数, 取得した総battle数)
    """
    try:
        battles = brawl_api.get_battlelog(tag)
    except HTTPError as e:
        db.log_fetch(tag, 0, error=f"HTTP {e.code}")
        if e.code == 404:
            raise HTTPException(status_code=404, detail="player tag not found")
        if e.code == 429:
            raise HTTPException(status_code=503, detail="upstream rate limited, retry later")
        raise HTTPException(status_code=502, detail=f"upstream error HTTP {e.code}")
    except Exception as e:
        db.log_fetch(tag, 0, error=str(e))
        raise HTTPException(status_code=502, detail=f"upstream error: {type(e).__name__}")

    trio = [b for b in battles if brawl_api.is_trio_battle(b)]
    inserted = db.upsert_battles(tag, trio) if trio else 0
    db.log_fetch(tag, inserted)
    return inserted, len(battles)


# 非同期 historical import: 同タグの重複起動を防ぐためのロック (in-progress set)
_HISTORICAL_IN_PROGRESS = set()
_HISTORICAL_LOCK = threading.Lock()
_HISTORICAL_LAST_RUN = {}  # tag → unix ts


def _historical_worker(tag: str, jsonl_path):
    try:
        n = db.import_historical_battles(tag, jsonl_path)
        if n:
            print(f"[{tag}] historical import (async): +{n} battles")
    except Exception as e:
        print(f"[{tag}] historical async failed: {type(e).__name__}: {e}")
    finally:
        with _HISTORICAL_LOCK:
            _HISTORICAL_IN_PROGRESS.discard(tag)
            _HISTORICAL_LAST_RUN[tag] = int(time.time())


def _trigger_historical_import_async(tag: str, jsonl_path, min_interval: int = 600):
    """非同期で historical import を起動。 同タグ進行中 or 直近10分以内に実行済ならskip。"""
    with _HISTORICAL_LOCK:
        if tag in _HISTORICAL_IN_PROGRESS:
            return
        last = _HISTORICAL_LAST_RUN.get(tag, 0)
        if int(time.time()) - last < min_interval:
            return
        _HISTORICAL_IN_PROGRESS.add(tag)
    threading.Thread(target=_historical_worker, args=(tag, jsonl_path), daemon=True).start()


def _since_for_period(period: str | None) -> str | None:
    """period 'all' / '7d' / '30d' を battle_time フォーマットの since に変換"""
    if not period or period == "all":
        return None
    days = None
    if period == "7d":
        days = 7
    elif period == "30d":
        days = 30
    elif period == "1d":
        days = 1
    else:
        return None
    from datetime import datetime, timedelta, timezone
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.strftime("%Y%m%dT%H%M%S.000Z")


@app.get("/api/player/{tag}")
@limiter.limit("20/minute")
def get_player(tag: str, request: Request, period: str = "all"):
    tag = _normalize_or_400(tag)
    # 初回(未登録 または 試合データなし) → 自動で取得+登録
    wl = db.get_watchlist()
    is_registered = any(w["tag"] == tag for w in wl)
    # 公式 player profile を毎回取得して watchlist 更新 (現在トロ・最高トロ・プロフィール JSON)
    try:
        player = brawl_api.get_player(tag)
        db.add_to_watchlist(
            tag,
            name=player.get("name"),
            trophies=player.get("trophies"),
            highest_trophies=player.get("highestTrophies"),
            profile_json=json.dumps(player, ensure_ascii=False),
        )
    except HTTPError as e:
        if not is_registered:
            if e.code == 404:
                raise HTTPException(status_code=404, detail="player tag not found")
            raise HTTPException(status_code=502, detail=f"upstream error HTTP {e.code}")
        # 既登録なら profile 取得失敗は無視して続行 (battlelog や DB 集計は使える)
    if not is_registered:
        # 初回フェッチ (公式API battlelog)
        _fetch_and_save(tag)

    # historical import は非同期実行 (jsonl 745MB+ で 5-10秒かかるため UI ブロックしない)
    # 次回ページアクセス時には反映される
    historical_jsonl = Path(__file__).parent.parent / "data" / "trio_battles.jsonl"
    _trigger_historical_import_async(tag, historical_jsonl)

    since = _since_for_period(period)
    stats = db.get_player_stats(tag, since=since)
    cooldown = db.cooldown_remaining(tag)
    last_fetched = db.last_fetch_time(tag)

    # プロフィール情報 (DB の watchlist + 保存済 profile_json をparse)
    with db.conn() as c:
        prof_row = c.execute(
            "SELECT name, trophies, highest_trophies, registered_at, profile_json FROM watchlist WHERE tag=?",
            (tag,),
        ).fetchone()
    prof = dict(prof_row) if prof_row else {}
    raw_profile = None
    if prof.get("profile_json"):
        try:
            raw_profile = json.loads(prof.pop("profile_json"))
        except Exception:
            raw_profile = None
    if raw_profile:
        # 公式API から軽量化したフィールドを追加
        prof["expLevel"] = raw_profile.get("expLevel")
        prof["icon"] = raw_profile.get("icon", {}).get("id")
        prof["nameColor"] = raw_profile.get("nameColor")
        prof["club"] = raw_profile.get("club") or {}
        prof["victories_3v3"] = raw_profile.get("3vs3Victories")
        prof["victories_solo"] = raw_profile.get("soloVictories")
        prof["victories_duo"] = raw_profile.get("duoVictories")
        # ガチバトル (Ranked Play) の段位 + Elo
        prof["rankedRankName"] = raw_profile.get("rankedRankName")
        prof["rankedElo"] = raw_profile.get("rankedElo")
        prof["highestSeasonRankedRankName"] = raw_profile.get("highestSeasonRankedRankName")
        prof["highestSeasonRankedElo"] = raw_profile.get("highestSeasonRankedElo")
        prof["highestAllTimeRankedRankName"] = raw_profile.get("highestAllTimeRankedRankName")
        prof["highestAllTimeRankedElo"] = raw_profile.get("highestAllTimeRankedElo")
        prof["totalPrestigeLevel"] = raw_profile.get("totalPrestigeLevel")
        # ブロウラー (軽量化: 必要フィールドだけ)
        brawlers = []
        for b in raw_profile.get("brawlers", []):
            brawlers.append({
                "id": b.get("id"),
                "name": b.get("name"),
                "power": b.get("power"),
                "rank": b.get("rank"),
                "trophies": b.get("trophies"),
                "highestTrophies": b.get("highestTrophies"),
                "gears": len(b.get("gears") or []),
                "starPowers": len(b.get("starPowers") or []),
                "gadgets": len(b.get("gadgets") or []),
                "hyperCharge": 1 if b.get("hyperCharge") else 0,
            })
        prof["brawlers"] = brawlers

    return {
        "tag": tag,
        "profile": prof or {},
        "stats": stats,
        "period": period,
        "cooldown_seconds": cooldown,
        "last_fetched_at": last_fetched,
        "watchlist_count": len(db.get_watchlist()),
        "watchlist_max": db.MAX_WATCHLIST,
    }


@app.get("/api/player/{tag}/matchups")
@limiter.limit("10/minute")
def get_matchups(tag: str, request: Request, period: str = "all", min_seen: int = 5):
    """対面相性分析: 敵に居たブロウラー別の自分の成績。"""
    tag = _normalize_or_400(tag)
    since = _since_for_period(period)
    return {"tag": tag, "period": period, **db.get_player_matchups(tag, since=since, min_seen=min_seen)}


@app.get("/api/player/{tag}/battles")
@limiter.limit("30/minute")
def get_battles(
    tag: str,
    request: Request,
    limit: int = 100,
    offset: int = 0,
    brawler: str | None = None,
    map: str | None = None,
    rank: int | None = None,
):
    tag = _normalize_or_400(tag)
    if limit > 500:
        limit = 500
    if limit < 1:
        limit = 1
    if offset < 0:
        offset = 0
    # filter conditions for total count
    where = ["tag = ?", "mode = 'trioShowdown'"]
    params: list = [tag]
    if brawler:
        where.append("brawler = ?"); params.append(brawler)
    if map:
        where.append("map = ?"); params.append(map)
    if rank is not None:
        where.append("rank = ?"); params.append(int(rank))
    where_sql = " AND ".join(where)
    with db.conn() as c:
        total = c.execute(f"SELECT COUNT(*) FROM battles WHERE {where_sql}", params).fetchone()[0]
    return {
        "tag": tag,
        "limit": limit,
        "offset": offset,
        "total": total,
        "filters": {"brawler": brawler, "map": map, "rank": rank},
        "battles": db.get_player_battles(
            tag, limit=limit, offset=offset, brawler=brawler, map_name=map, rank=rank
        ),
    }


@app.get("/api/leaderboard")
@limiter.limit("30/minute")
def leaderboard(
    request: Request,
    min_battles: int = 50,
    order: str = "rank1_rate",
    period: str = "all",
    limit: int = 100,
):
    """全ウォッチリストタグから戦績ランキング。
    order: rank1_rate / top2_rate / avg_rank / battles
    period: all / 30d / 7d / 1d
    """
    if limit > 300:
        limit = 300
    since = _since_for_period(period)
    extra = ""
    base_params: list = []
    if since:
        extra = " AND b.battle_time >= ?"
        base_params.append(since)
    order_sql = {
        "rank1_rate": "rank1_rate DESC, battles DESC",
        "top2_rate": "top2_rate DESC, battles DESC",
        "rank4_rate_low": "rank4_rate ASC, battles DESC",
        "avg_rank": "avg_rank ASC, battles DESC",
        "battles": "battles DESC, rank1_rate DESC",
    }.get(order, "rank1_rate DESC, battles DESC")
    with db.conn() as c:
        rows = c.execute(
            f"""SELECT
                  b.tag,
                  COUNT(*) AS battles,
                  SUM(CASE WHEN b.rank<=2 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS top2_rate,
                  SUM(CASE WHEN b.rank=1 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS rank1_rate,
                  SUM(CASE WHEN b.rank=4 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS rank4_rate,
                  AVG(CAST(b.rank AS REAL)) AS avg_rank,
                  w.name AS name,
                  w.trophies AS trophies
                FROM battles b
                LEFT JOIN watchlist w ON b.tag = w.tag
                WHERE b.mode = 'trioShowdown' AND b.rank > 0{extra}
                GROUP BY b.tag
                HAVING battles >= ?
                ORDER BY {order_sql}
                LIMIT ?""",
            base_params + [min_battles, limit],
        ).fetchall()
    return {
        "results": [dict(r) for r in rows],
        "params": {"min_battles": min_battles, "order": order, "period": period, "limit": limit},
    }


@app.get("/api/club/{tag}")
@limiter.limit("10/minute")
def get_club(tag: str, request: Request):
    tag = _normalize_or_400(tag)
    from urllib.parse import quote
    try:
        club = brawl_api.fetch(f"/clubs/{quote(tag, safe='')}")
    except HTTPError as e:
        if e.code == 404:
            raise HTTPException(status_code=404, detail="club not found")
        raise HTTPException(status_code=502, detail=f"upstream HTTP {e.code}")
    members_raw = club.get("members", [])
    members = []
    for m in members_raw:
        mtag = m.get("tag")
        if not mtag:
            continue
        stats = db.get_player_stats(mtag)
        members.append({
            "tag": mtag,
            "name": m.get("name", ""),
            "role": m.get("role", ""),
            "trophies": m.get("trophies", 0),
            "summary": stats["summary"],
            "tracked": bool(stats["summary"].get("total", 0)),
        })
    return {
        "tag": tag,
        "name": club.get("name", ""),
        "description": club.get("description", ""),
        "trophies": club.get("trophies", 0),
        "type": club.get("type", ""),
        "member_count": len(members),
        "members": members,
    }


# ============================================================
# 練習試合 bot 観察記録 (バトルカード prestigeLevel + rankedRank)
# ============================================================
RANKED_RANK_ORDER = [
    "Bronze I", "Bronze II", "Bronze III",
    "Silver I", "Silver II", "Silver III",
    "Gold I", "Gold II", "Gold III",
    "Diamond I", "Diamond II", "Diamond III",
    "Mythic I", "Mythic II", "Mythic III",
    "Legendary I", "Legendary II", "Legendary III",
    "Masters",
    "Pro",
]


@app.post("/api/bot-obs")
@limiter.limit("30/minute")
def add_bot_obs(
    request: Request,
    tag: str,
    bot_brawler: str | None = None,
    bot_prestige_level: int | None = None,
    bot_ranked_rank_name: str | None = None,
    my_brawler: str | None = None,
    mode: str | None = None,
    notes: str | None = None,
):
    """練習試合で目視確認した bot のバトルカード情報を記録。
    bot_ranked_rank_name は "Diamond III" 等の文字列。
    """
    tag = _normalize_or_400(tag)
    if bot_prestige_level is not None:
        if not (0 <= bot_prestige_level <= 50):
            raise HTTPException(status_code=400, detail="bot_prestige_level out of range")
    # bot_ranked_rank_name 正規化
    rank_num = None
    if bot_ranked_rank_name:
        bot_ranked_rank_name = bot_ranked_rank_name.strip()
        if bot_ranked_rank_name in RANKED_RANK_ORDER:
            rank_num = RANKED_RANK_ORDER.index(bot_ranked_rank_name) + 1
    obs_id = db.add_bot_observation(
        tag=tag,
        bot_brawler=bot_brawler.upper() if bot_brawler else None,
        bot_prestige_level=bot_prestige_level,
        bot_ranked_rank_name=bot_ranked_rank_name,
        bot_ranked_rank_num=rank_num,
        my_brawler=my_brawler.upper() if my_brawler else None,
        mode=mode,
        notes=notes,
    )
    return {"ok": True, "id": obs_id, "rank_num": rank_num}


@app.get("/api/bot-obs/{tag}")
@limiter.limit("30/minute")
def get_bot_obs(tag: str, request: Request, limit: int = 50):
    tag = _normalize_or_400(tag)
    if limit > 200:
        limit = 200
    rows = db.get_bot_observations(tag=tag, limit=limit)
    return {"tag": tag, "observations": rows, "rank_options": RANKED_RANK_ORDER}


@app.delete("/api/bot-obs/{obs_id}")
@limiter.limit("10/minute")
def delete_bot_obs(obs_id: int, request: Request, tag: str):
    tag = _normalize_or_400(tag)
    ok = db.delete_bot_observation(obs_id, tag)
    return {"ok": ok}


@app.post("/api/player/{tag}/refresh")
@limiter.limit("10/minute")
def refresh_player(tag: str, request: Request):
    tag = _normalize_or_400(tag)
    cooldown = db.cooldown_remaining(tag)
    if cooldown > 0:
        raise HTTPException(
            status_code=429,
            detail=f"cooldown active, retry in {cooldown}s",
            headers={"Retry-After": str(cooldown)},
        )
    inserted, total = _fetch_and_save(tag)
    return {
        "tag": tag,
        "fetched_battles": total,
        "new_trio_battles": inserted,
        "next_cooldown_seconds": db.COOLDOWN_SECONDS,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8001, reload=False)
