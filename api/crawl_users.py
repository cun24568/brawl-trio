"""ウォッチリスト全タグの定期クロール (cronから呼ばれる)。

軽量化版 (2026-06-05):
- 多重起動防止: /tmp/brawl_crawl_users.lock を fcntl flock (--no-wait 即exit)
- 並列度 8→4
- historical import (jsonl 745MB の全 streaming) は default skip
  → マイページ初検索時の _trigger_historical_import_async (server.py) でカバー済なので不要
  → 必要なら python crawl_users.py --with-historical で明示的に実行 (日次1回想定)

cron例 (毎時0分 + flock で重複起動防止):
  0 * * * * /usr/bin/flock -n /tmp/brawl_crawl_users.lock /home/soya/brawl-trio/api/venv/bin/python /home/soya/brawl-trio/api/crawl_users.py >> /home/soya/brawl-trio/api/crawl_users.log 2>&1
"""
import argparse
import fcntl
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).parent))
import brawl_api  # noqa: E402
import db  # noqa: E402

PARALLEL = 4
JSONL_PATH = Path(__file__).parent.parent / "data" / "trio_battles.jsonl"
LOCK_PATH = "/tmp/brawl_crawl_users.lock"


def _acquire_lock():
    """flock を取る。 取れなければ即exit (多重起動防止)。 返値: lock fd"""
    fd = os.open(LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(f"[{time.strftime('%F %T')}] another crawl_users.py is already running, skip")
        os.close(fd)
        sys.exit(0)
    os.write(fd, f"{os.getpid()}\n".encode())
    return fd


def _fetch_one(tag: str, with_historical: bool) -> tuple[str, int, int, str | None]:
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
    # historical import は重い (jsonl 745MB の全 streaming) のでdefault skip
    if with_historical:
        try:
            n_hist = db.import_historical_battles(tag, JSONL_PATH)
        except Exception as e:
            print(f"  {tag:<12} historical import failed: {type(e).__name__}: {e}")
    db.log_fetch(tag, n_api + n_hist)
    return tag, n_api, n_hist, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-historical", action="store_true",
                        help="jsonl 745MB の historical import も同時に実行 (重い、 日次1回程度推奨)")
    parser.add_argument("--parallel", type=int, default=PARALLEL)
    args = parser.parse_args()

    lock_fd = _acquire_lock()
    try:
        db.init_db()
        wl = db.get_active_watchlist()
        total = len(db.get_watchlist())
        if not wl:
            print(f"[{time.strftime('%F %T')}] active watchlist empty (total {total}), nothing to do")
            return
        mode = "+historical" if args.with_historical else "(API only)"
        print(f"[{time.strftime('%F %T')}] crawling {len(wl)} active / {total} total tags "
              f"({args.parallel} parallel) {mode}")
        t0 = time.time()
        total_api = 0
        total_hist = 0
        fails = 0
        with ThreadPoolExecutor(max_workers=args.parallel) as ex:
            futures = {ex.submit(_fetch_one, w["tag"], args.with_historical): w["tag"] for w in wl}
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
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        except Exception:
            pass


if __name__ == "__main__":
    main()
