#!/bin/bash
# 1時間ごと実行用: コード更新 + クロール + DB再生成 + git push
# (Discord通知が要れば export DISCORD_WEBHOOK_URL=https://... を ~/.bashrc 等に)
set -e
cd /home/soya/brawl-trio

# 二重起動防止
exec 200>/tmp/brawl-trio.lock
flock -n 200 || { echo "Already running, skip"; exit 0; }

# 失敗時のDiscord通知
notify_discord() {
    [ -z "${DISCORD_WEBHOOK_URL:-}" ] && return
    curl -s -X POST -H "Content-Type: application/json" \
         -d "{\"content\":\"$1\"}" "$DISCORD_WEBHOOK_URL" >/dev/null 2>&1 || true
}
trap 'notify_discord "❌ brawl-trio cron failed at $(date) (exit $?)"' ERR

echo "===================="
echo "Run at $(date)"
echo "===================="

# 最新コードに更新
git pull --rebase --autostash || echo "git pull failed, continue with current code"

# 旧形式ファイル(JSONL移行後不要)を削除
rm -f data/trio_battles_full.json data/trio_battles_partial.json

python3 -u fetch_official_brawlers.py || echo "official brawlers fetch failed (non-fatal)"
python3 -u crawl_full.py
python3 -u build_db.py

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
