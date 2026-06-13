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

# trio_battles.jsonl を時間窓でprune (無限増殖防止、 メモリ/IO bound)。 軽い (streaming, O(1)メモリ)
python3 -u prune_jsonl.py || echo "prune failed (non-fatal)"

python3 -u fetch_official_brawlers.py || echo "official brawlers fetch failed (non-fatal)"

# crawl_full / build_db はメモリを大量に使う (peak ~2.8GB)。
# cgroup スコープで隔離し、 uvicorn (brawl-api.service) のページを追い出さないようにする。
#   MemoryHigh=3000M : これを超えると積極的に reclaim/throttle (soft limit)
#   MemorySwapMax=0  : swap を食わせない (swap thrash で box全体が固まるのを防ぐ)
# systemd-run --user が使えない環境では素の python にフォールバック。
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=${XDG_RUNTIME_DIR}/bus}"
# systemd-run --user の可用性を1回だけ判定 (cron からは dbus 不通のことがある)
CAP_OK=0
if command -v systemd-run >/dev/null 2>&1 \
   && systemd-run --user --scope --quiet -p MemoryHigh=100M -- true >/dev/null 2>&1; then
    CAP_OK=1
else
    echo "(systemd-run --user unavailable, crawl will run uncapped)"
fi
run_capped() {
    # cgroup メモリ隔離で python を実行 (uvicorn を OOM 巻き添えから守る)
    if [ "$CAP_OK" = "1" ]; then
        systemd-run --user --scope --quiet -p MemoryHigh=3000M -p MemorySwapMax=0 \
            -- python3 -u "$@"
    else
        python3 -u "$@"
    fi
}
run_capped crawl_full.py
run_capped build_db.py

# db.json + 月別アーカイブ に変更があるときだけ commit & push
git add data/db.json data/archive/
if ! git diff --cached --quiet; then
    MSG="auto: data update $(date -u +%FT%TZ)"
    git commit -m "$MSG"
    git push
    echo "=== pushed ==="
else
    echo "=== no data changes ==="
fi

echo "=== done $(date) ==="
