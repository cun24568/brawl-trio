"""trio_battles.jsonl から名前検索インデックスを SQLite (player_index) に構築。

背景:
  以前は API 起動時に jsonl 全行 (600万行) をメモリ展開して in-memory index を作っていたが、
  ~1.5GB 食って MemoryMax で thrash → index構築が完了せず検索が死ぬ問題があった。

対策:
  jsonl を streaming で読み (O(1)メモリ)、 SQLite の player_index テーブルに upsert。
  API 側は LIKE クエリで直接検索 (メモリに index を持たない)。

実行:
  cron の update.sh から crawl 後に呼ぶ (jsonl streaming なので軽量、 数十秒)。
  手動: python3 api/build_player_index.py
"""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import db  # noqa: E402

JSONL = Path(__file__).parent.parent / "data" / "trio_battles.jsonl"
BATCH = 5000
_INVISIBLE_RE = re.compile(r"[\s　ᅠ⠀​‌‍⁠﻿]")


def is_valid_name(s: str) -> bool:
    if not s:
        return False
    return len(_INVISIBLE_RE.sub("", s)) > 0


def iter_players():
    """jsonl を streaming して (tag, name, trophies) を yield"""
    if not JSONL.exists():
        return
    with open(JSONL, encoding="utf-8") as f:
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
                    ptro = (p.get("brawler") or {}).get("trophies", 0) or 0
                    if ptag and is_valid_name(pname):
                        yield ptag, pname, ptro


def main():
    db.init_db()
    t0 = time.time()
    batch = []
    n = 0
    for tag, name, tro in iter_players():
        batch.append((tag, name, name.lower(), tro))
        if len(batch) >= BATCH:
            db.upsert_player_index(batch)
            n += len(batch)
            batch = []
    if batch:
        db.upsert_player_index(batch)
        n += len(batch)
    total = db.player_index_count()
    print(f"player_index: processed {n} rows, {total} unique tags, {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
