"""ウォッチリスト全タグの定期クロール (30分cronから呼ばれる)。
- 並列8で公式API battlelog 取得 + trio_battles.jsonl からの履歴import
- 個別失敗は無視して続行
- ログを stdout に出す (cron経由でファイルにリダイレクト想定)
"""
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).parent))
import brawl_api  # noqa: E402
import db  # noqa: E402

PARALLEL = 8
JSONL_PATH = Path(__file__).parent.parent / "data" / "trio_battles.jsonl"


def _fetch_one(tag: str) -> tuple[str, int, int, str | None]:
    """返値: (tag, 公式APIから取得した新規, jsonlから取り込んだ新規, error)"""
    n_api = 0
    n_hist = 0
    try:
        # 公式API: 直近25試合 (全モード保存、 mode列で識別可能)
        battles = brawl_api.get_battlelog(tag)
        n_api = db.upsert_battles(tag, battles) if battles else 0
    except HTTPError as e:
        db.log_fetch(tag, 0, error=f"HTTP {e.code}")
        return tag, 0, 0, f"HTTP {e.code}"
    except Exception as e:
        db.log_fetch(tag, 0, error=f"{type(e).__name__}: {e}")
        return tag, 0, 0, f"{type(e).__name__}"
    # 全体クロール蓄積分の取り込み (毎回 jsonl 全 streaming, 重複は INSERT OR IGNORE)
    try:
        n_hist = db.import_historical_battles(tag, JSONL_PATH)
    except Exception as e:
        # historical 失敗しても公式API分は保存済なのでこのまま続行
        print(f"  {tag:<12} historical import failed: {type(e).__name__}: {e}")
    db.log_fetch(tag, n_api + n_hist)
    return tag, n_api, n_hist, None


def main():
    db.init_db()
    wl = db.get_active_watchlist()
    total = len(db.get_watchlist())
    if not wl:
        print(f"[{time.strftime('%F %T')}] active watchlist empty (total {total}), nothing to do")
        return
    print(f"[{time.strftime('%F %T')}] crawling {len(wl)} active / {total} total tags ({PARALLEL} parallel)")
    t0 = time.time()
    total_api = 0
    total_hist = 0
    fails = 0
    with ThreadPoolExecutor(max_workers=PARALLEL) as ex:
        futures = {ex.submit(_fetch_one, w["tag"]): w["tag"] for w in wl}
        for fut in as_completed(futures):
            tag, n_api, n_hist, err = fut.result()
            total_api += n_api
            total_hist += n_hist
            if err:
                fails += 1
                print(f"  {tag:<12} FAIL {err}")
            elif n_api or n_hist:
                print(f"  {tag:<12} api+{n_api} hist+{n_hist}")
    print(
        f"[{time.strftime('%F %T')}] done: api+{total_api} hist+{total_hist} battles, "
        f"{fails} fails, {time.time() - t0:.1f}s"
    )


if __name__ == "__main__":
    main()
