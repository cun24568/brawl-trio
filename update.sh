#!/bin/bash
# 1時間ごと実行用: コード更新 + クロール + DB再生成 + git push
set -e
cd /home/soya/brawl-trio

# 二重起動防止
exec 200>/tmp/brawl-trio.lock
flock -n 200 || { echo "Already running, skip"; exit 0; }

echo "===================="
echo "Run at $(date)"
echo "===================="

# 最新コードに更新 (push後の自分のcommitもfast-forward可能)
git pull --rebase --autostash || echo "git pull failed, continue with current code"

python3 crawl_full.py
python3 build_db.py

# db.json に変更があるときだけ commit & push
git add data/db.json
if ! git diff --cached --quiet; then
    MSG="auto: data update $(date -u +%FT%TZ)"
    git commit -m "$MSG"
    git push
    echo "=== pushed ==="
else
    echo "=== no data changes ==="
fi

echo "=== done $(date) ==="
