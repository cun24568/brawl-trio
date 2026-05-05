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


@app.get("/api/health")
def health():
    return {"ok": True, "ts": int(time.time())}


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
    if not is_registered:
        try:
            player = brawl_api.get_player(tag)
            db.add_to_watchlist(tag, name=player.get("name"), trophies=player.get("trophies"))
        except HTTPError as e:
            if e.code == 404:
                raise HTTPException(status_code=404, detail="player tag not found")
            raise HTTPException(status_code=502, detail=f"upstream error HTTP {e.code}")
        # 初回フェッチ (公式API)
        _fetch_and_save(tag)

    # ページ表示のたびに jsonl からの差分も取り込む (重複は INSERT OR IGNORE で無視)
    historical_jsonl = Path(__file__).parent.parent / "data" / "trio_battles.jsonl"
    try:
        n_hist = db.import_historical_battles(tag, historical_jsonl)
        if n_hist:
            print(f"[{tag}] historical import: +{n_hist} battles")
    except Exception as e:
        print(f"[{tag}] historical import failed: {type(e).__name__}: {e}")

    since = _since_for_period(period)
    stats = db.get_player_stats(tag, since=since)
    cooldown = db.cooldown_remaining(tag)
    last_fetched = db.last_fetch_time(tag)

    # プロフィール情報
    with db.conn() as c:
        prof = c.execute(
            "SELECT name, trophies, registered_at FROM watchlist WHERE tag=?", (tag,)
        ).fetchone()

    return {
        "tag": tag,
        "profile": dict(prof) if prof else {},
        "stats": stats,
        "period": period,
        "cooldown_seconds": cooldown,
        "last_fetched_at": last_fetched,
        "watchlist_count": len(db.get_watchlist()),
        "watchlist_max": db.MAX_WATCHLIST,
    }


@app.get("/api/player/{tag}/battles")
@limiter.limit("30/minute")
def get_battles(tag: str, request: Request, limit: int = 100, offset: int = 0):
    tag = _normalize_or_400(tag)
    if limit > 500:
        limit = 500
    if limit < 1:
        limit = 1
    if offset < 0:
        offset = 0
    with db.conn() as c:
        total = c.execute("SELECT COUNT(*) FROM battles WHERE tag=?", (tag,)).fetchone()[0]
    return {
        "tag": tag,
        "limit": limit,
        "offset": offset,
        "total": total,
        "battles": db.get_player_battles(tag, limit=limit, offset=offset),
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
