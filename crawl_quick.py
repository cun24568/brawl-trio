"""
クイックトライアル版: クラブメンバーだけ取得して挙動確認。
- 各リクエストごとに何が起きてるかprintで実況
- timeout 短め(5秒)
- 10タグごとに途中保存
- rate limit来たら即停止 (リトライしない)
"""
import csv
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen, Request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API = "https://api.brawlstars.com/v1"
SCRIPT_DIR = Path(__file__).parent
ENV = SCRIPT_DIR / ".env"
OUT = SCRIPT_DIR / "data"
SEED_TAG = "#YQ8YY09R"
DELAY = 0.15
TIMEOUT = 5


def load_token() -> str:
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if line.startswith("BRAWL_API_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("token missing")


TOKEN = load_token()


def fetch(path: str):
    req = Request(
        f"{API}{path}",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/json",
            "User-Agent": "brawl-trio/0.1",
        },
    )
    with urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def save_progress(battles, label):
    out_file = OUT / f"trio_battles_{label}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(battles, f, ensure_ascii=False)
    return out_file


def main():
    OUT.mkdir(exist_ok=True)
    t0 = time.time()

    # Step 1: シードプレイヤーのクラブ
    print(f"[1] {SEED_TAG} のプロフィール取得...")
    try:
        player = fetch(f"/players/{quote(SEED_TAG, safe='')}")
        print(f"    Name: {player.get('name')} / Trophies: {player.get('trophies')}")
    except (HTTPError, URLError) as e:
        print(f"    FAIL: {e}")
        sys.exit(1)
    time.sleep(DELAY)

    club = player.get("club") or {}
    ctag = club.get("tag")
    if not ctag:
        print("    クラブ未所属。終了。")
        return
    print(f"    Club: {club.get('name')} ({ctag})")

    print(f"\n[2] クラブメンバー取得...")
    try:
        cdata = fetch(f"/clubs/{quote(ctag, safe='')}")
    except (HTTPError, URLError) as e:
        print(f"    FAIL: {e}")
        sys.exit(1)
    members = cdata.get("members", [])
    tags = [m["tag"] for m in members]
    print(f"    +{len(tags)} members")
    time.sleep(DELAY)

    print(f"\n[3] 各メンバーのバトルログ取得 ({len(tags)} tags)")
    print("=" * 60)
    battles = []
    fail_count = 0
    for i, tag in enumerate(tags, 1):
        t_start = time.time()
        try:
            data = fetch(f"/players/{quote(tag, safe='')}/battlelog")
            n_total = len(data.get("items", []))
            n_trio = 0
            for b in data.get("items", []):
                bt = b.get("battle", {})
                ev = b.get("event", {})
                # event.mode で判定 (battle.mode はトリオでも"duoShowdown"を返すバグあり)
                # チーム構造 4x3 でも確認
                is_trio = ev.get("mode") == "trioShowdown"
                teams_arr = bt.get("teams", [])
                if not is_trio and len(teams_arr) == 4 and all(len(t) == 3 for t in teams_arr):
                    is_trio = True
                if not is_trio:
                    continue
                b["_requester_tag"] = tag
                idx = None
                for ti, team in enumerate(teams_arr):
                    if any(p.get("tag") == tag for p in team):
                        idx = ti
                        break
                b["_requester_team_idx"] = idx
                battles.append(b)
                n_trio += 1
            elapsed = time.time() - t_start
            print(f"  {i:3d}/{len(tags)}  {tag:<12} {n_total:3d}戦中 trio:{n_trio:2d}  ({elapsed*1000:.0f}ms)")
        except HTTPError as e:
            fail_count += 1
            print(f"  {i:3d}/{len(tags)}  {tag:<12} HTTP {e.code}")
            if e.code == 429:
                print("\n  ⚠ Rate limited! 中断して途中までを保存します")
                break
        except URLError as e:
            fail_count += 1
            print(f"  {i:3d}/{len(tags)}  {tag:<12} timeout/network: {e}")
        except Exception as e:
            fail_count += 1
            print(f"  {i:3d}/{len(tags)}  {tag:<12} ERROR: {e}")
        time.sleep(DELAY)

        # 10タグごとに途中保存
        if i % 10 == 0:
            save_progress(battles, "partial")

    print("=" * 60)
    print(f"完了: {len(battles)} trio battles / 失敗 {fail_count} 件")

    # 最終保存
    out_file = save_progress(battles, "club")
    print(f"Saved: {out_file}")

    # 軽集計
    print("\n--- マップ別picks ---")
    map_counts = defaultdict(int)
    for b in battles:
        map_counts[b.get("event", {}).get("map", "?")] += 1
    for m, c in sorted(map_counts.items(), key=lambda x: -x[1]):
        print(f"  {c:3d}  {m}")

    print(f"\n所要時間: {time.time() - t0:.1f}秒")


if __name__ == "__main__":
    main()
