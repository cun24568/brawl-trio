"""trio_battles.jsonl を時間窓でローテーション (古い試合を削除してメモリ/IOを bound)。

背景:
  trio_battles.jsonl は append-only で無限増殖する (41日で17GB/1020万行に到達)。
  これを毎時 crawl_full (dedup) と build_db (集計) が全読みするため、
  ファイル増大に比例してメモリ (peak ~2.8GB) と処理時間が悪化していた。

対策:
  直近 WINDOW_DAYS 日分の試合だけ残す。 ストリーミングで temp に書き出し → atomic rename。
  メモリ O(1)、 ディスクは一時的に 2倍必要 (122GB空きあるので問題なし)。

メタの観点:
  サイトは「現在のメタ」 を表示するので、 古い (旧バランス・旧マップ) 試合はむしろノイズ。
  時間窓で絞る方が統計の鮮度が上がる。 db.json は元々 各マップ top1500 trio に capしているので
  サンプル過小化の心配も小さい。

使い方:
  python3 prune_jsonl.py            # WINDOW_DAYS でprune
  python3 prune_jsonl.py --days 14  # 窓を変更
  python3 prune_jsonl.py --dry-run  # 削除せず統計だけ表示
"""
import argparse
import os
import time
from pathlib import Path

DATA = Path(__file__).parent / "data"
JSONL = DATA / "trio_battles.jsonl"
WINDOW_DAYS = 30  # 残す日数


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=WINDOW_DAYS)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not JSONL.exists():
        print(f"no file: {JSONL}")
        return

    cutoff = time.strftime("%Y%m%dT%H%M%S", time.gmtime(time.time() - args.days * 86400))
    print(f"prune {JSONL.name}: keep battleTime >= {cutoff} (last {args.days} days)")

    size_before = JSONL.stat().st_size
    kept = 0
    dropped = 0
    malformed = 0
    tmp = JSONL.with_suffix(".jsonl.tmp")

    # battleTime は各行の先頭付近 ({"battleTime": "20260613T...") にあるので、
    # json parse せず文字列スライスで高速に日時判定する。
    out = None if args.dry_run else open(tmp, "w", encoding="utf-8")
    try:
        with open(JSONL, encoding="utf-8") as f:
            for line in f:
                # 行頭 '{"battleTime": "YYYYMMDDTHHMMSS...' を想定。 引用符位置で抽出。
                bt = ""
                i = line.find('"battleTime"')
                if i != -1:
                    q1 = line.find('"', i + 12)
                    if q1 != -1:
                        q2 = line.find('"', q1 + 1)
                        if q2 != -1:
                            bt = line[q1 + 1:q2]
                if not bt:
                    malformed += 1
                    # battleTime 不明な行は安全側で残す
                    if out:
                        out.write(line)
                    kept += 1
                    continue
                if bt[:15] >= cutoff:
                    if out:
                        out.write(line)
                    kept += 1
                else:
                    dropped += 1
    finally:
        if out:
            out.close()

    print(f"  kept={kept:,}  dropped={dropped:,}  malformed_kept={malformed:,}")
    if args.dry_run:
        print("  (dry-run, no changes)")
        tmp.unlink(missing_ok=True)
        return

    # atomic 置換
    os.replace(tmp, JSONL)
    size_after = JSONL.stat().st_size
    print(f"  size: {size_before/1e9:.2f}GB → {size_after/1e9:.2f}GB "
          f"({(1 - size_after/size_before)*100:.0f}% 削減)")


if __name__ == "__main__":
    main()
