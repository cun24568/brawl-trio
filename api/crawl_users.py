"""ウォッチリスト全タグの定期クロール (30分cronから呼ばれる)。
- 並列8でbattlelog取得 → トリオ抽出 → SQLite保存
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


def _fetch_one(tag: str) -> tuple[str, int, str | None]:
    try:
        battles = brawl_api.get_battlelog(tag)
        trio = [b for b in battles if brawl_api.is_trio_battle(b)]
        n = db.upsert_battles(tag, trio) if trio else 0
        db.log_fetch(tag, n)
        return tag, n, None
    except HTTPError as e:
        err = f"HTTP {e.code}"
        db.log_fetch(tag, 0, error=err)
        return tag, 0, err
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        db.log_fetch(tag, 0, error=err)
        return tag, 0, err


def main():
    db.init_db()
    wl = db.get_watchlist()
    if not wl:
        print(f"[{time.strftime('%F %T')}] watchlist empty, nothing to do")
        return
    print(f"[{time.strftime('%F %T')}] crawling {len(wl)} tags ({PARALLEL} parallel)")
    t0 = time.time()
    total_new = 0
    fails = 0
    with ThreadPoolExecutor(max_workers=PARALLEL) as ex:
        futures = {ex.submit(_fetch_one, w["tag"]): w["tag"] for w in wl}
        for fut in as_completed(futures):
            tag, n, err = fut.result()
            total_new += n
            if err:
                fails += 1
                print(f"  {tag:<12} FAIL {err}")
            elif n:
                print(f"  {tag:<12} +{n}")
    print(
        f"[{time.strftime('%F %T')}] done: {total_new} new battles, "
        f"{fails} fails, {time.time() - t0:.1f}s"
    )


if __name__ == "__main__":
    main()
