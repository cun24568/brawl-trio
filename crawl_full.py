"""
拡張クロール: クラブ + global TOP200 + JP TOP200 + 高トロフィープレイヤー (永続キャッシュ)
- 20タグごとに途中保存(中断OK)
- 各タグの結果を逐次表示
- 完了後に自動で集計してCSV出力
- バトルログから対戦相手タグを発見 (discovered_tags.json)
- 50,000+トロフィープレイヤーをqualifying_tags.jsonに永続蓄積
- 毎cycleで最大100人ぶんトロチェック (徐々に拡大)
"""
import csv
import json
import random
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen, Request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API = "https://api.brawlstars.com/v1"
SCRIPT_DIR = Path(__file__).parent
ENV = SCRIPT_DIR / ".env"
OUT = SCRIPT_DIR / "data"
SEED = "#YQ8YY09R"
# 追加クラブ (シードプレイヤーのクラブに加えて取得)
EXTRA_CLUBS = [
    ("#2CGLLR98V", "祝杯をあげよう"),
    ("#2QG9UVUUY", "バトロワオンリー"),
]
COUNTRIES = ["global", "JP", "KR", "US", "TW", "DE"]
DELAY = 0.15
TIMEOUT = 8
SAVE_EVERY = 100  # 並列化で件数が早く流れるので頻度下げる
PARALLEL_WORKERS = 8

# トロフィー閾値で qualifying プールを永続蓄積
TROPHY_THRESHOLD = 50000
TROPHY_CHECK_LIMIT = 500  # 1cycleで新規にチェックする数
MAX_QUALIFYING = 1_000_000  # qualifyingプール上限 (実質上限なし)
MAX_DISCOVERED = 1_000_000  # discovered キャッシュ上限
CRAWL_SAMPLE_SIZE = 5000  # 1cycleでqualifyingから sample してクロールする数

DISCOVERED_FILE = OUT / "discovered_tags.json"
QUALIFYING_FILE = OUT / "qualifying_tags.json"


def load_token():
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if line.startswith("BRAWL_API_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("token missing")


TOKEN = load_token()


def fetch(path):
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


def load_discovered():
    if DISCOVERED_FILE.exists():
        return set(json.loads(DISCOVERED_FILE.read_text(encoding="utf-8")))
    return set()


def save_discovered(s):
    # 上限超えたら新しいものを残す感じで切り詰め (大雑把: ランダムで)
    lst = list(s)
    if len(lst) > MAX_DISCOVERED:
        random.shuffle(lst)
        lst = lst[:MAX_DISCOVERED]
    DISCOVERED_FILE.write_text(json.dumps(lst, ensure_ascii=False), encoding="utf-8")


def load_qualifying():
    if QUALIFYING_FILE.exists():
        return json.loads(QUALIFYING_FILE.read_text(encoding="utf-8"))
    return []


def save_qualifying(qs):
    QUALIFYING_FILE.write_text(json.dumps(qs, ensure_ascii=False, indent=2), encoding="utf-8")


def collect_tags():
    tags = set()
    print(f"[Phase 1] タグ収集")

    # シードプレイヤーのクラブ
    try:
        player = fetch(f"/players/{quote(SEED, safe='')}")
        ctag = (player.get("club") or {}).get("tag")
        cname = (player.get("club") or {}).get("name", "?")
        if ctag:
            cdata = fetch(f"/clubs/{quote(ctag, safe='')}")
            for m in cdata.get("members", []):
                tags.add(m["tag"])
            print(f"  {cname}: +{len(cdata.get('members', []))} (total {len(tags)})")
    except (HTTPError, URLError) as e:
        print(f"  seed club FAIL: {e}")
    time.sleep(DELAY)

    # 追加クラブ
    for ctag, cname in EXTRA_CLUBS:
        try:
            cdata = fetch(f"/clubs/{quote(ctag, safe='')}")
            members = cdata.get("members", [])
            for m in members:
                tags.add(m["tag"])
            print(f"  {cname}: +{len(members)} (total {len(tags)})")
            time.sleep(DELAY)
        except (HTTPError, URLError) as e:
            print(f"  {cname} FAIL: {e}")

    # 各国
    for country in COUNTRIES:
        try:
            data = fetch(f"/rankings/{country}/players")
            items = data.get("items", [])
            for p in items:
                tags.add(p["tag"])
            print(f"  {country}: +{len(items)} (total {len(tags)})")
            time.sleep(DELAY)
        except (HTTPError, URLError) as e:
            print(f"  {country} FAIL: {e}")

    # 高トロフィー(50k+) qualifying プールから sampling
    qualifying = load_qualifying()
    if qualifying:
        sample_size = min(CRAWL_SAMPLE_SIZE, len(qualifying))
        sampled = random.sample(qualifying, sample_size)
        for q in sampled:
            tags.add(q["tag"])
        print(f"  qualifying ({TROPHY_THRESHOLD}+): sampled {sample_size}/{len(qualifying)} (total {len(tags)})")

    return sorted(tags)


def is_trio_battle(b):
    """event.mode と チーム構造の両方でトリオ判定"""
    ev = b.get("event", {})
    if ev.get("mode") == "trioShowdown":
        return True
    teams = b.get("battle", {}).get("teams", [])
    if len(teams) == 4 and all(len(t) == 3 for t in teams):
        return True
    return False


def _process_one_battlelog(tag, discovered, lock):
    """1タグ分のbattlelog取得 → trio抽出 + discovered更新。スレッドセーフ。"""
    t0 = time.time()
    try:
        data = fetch(f"/players/{quote(tag, safe='')}/battlelog")
    except HTTPError as e:
        return tag, [], e.code, time.time() - t0
    except (URLError, Exception) as e:
        return tag, [], f"err:{e}", time.time() - t0

    trio_battles = []
    new_tags_local = set()
    for b in data.get("items", []):
        if not is_trio_battle(b):
            continue
        b["_requester_tag"] = tag
        idx = None
        for ti, team in enumerate(b["battle"].get("teams", [])):
            if any(p.get("tag") == tag for p in team):
                idx = ti
                break
        b["_requester_team_idx"] = idx
        for team in b["battle"].get("teams", []):
            for p in team:
                t = p.get("tag")
                if t:
                    new_tags_local.add(t)
        trio_battles.append(b)
    # discovered 更新は最後にまとめてロック
    if new_tags_local:
        with lock:
            discovered.update(new_tags_local)
    return tag, trio_battles, None, time.time() - t0


def fetch_battles(tags, discovered):
    battles = []
    fail = 0
    rate_limited = False
    lock = threading.Lock()
    n = len(tags)
    print(f"[Phase 2] バトルログ取得 ({n} tags, {PARALLEL_WORKERS} 並列)")
    print("=" * 60)
    t_start = time.time()

    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as ex:
        futures = {
            ex.submit(_process_one_battlelog, tag, discovered, lock): tag
            for tag in tags
        }
        completed = 0
        for fut in as_completed(futures):
            completed += 1
            tag, trio_results, err, elapsed = fut.result()
            if err == 429:
                fail += 1
                print(f"  {completed:4d}/{n}  {tag:<12} HTTP 429 (rate limit)")
                rate_limited = True
                # キャンセルできるものはキャンセル
                for f in futures:
                    f.cancel()
                break
            elif err is not None:
                fail += 1
                print(f"  {completed:4d}/{n}  {tag:<12} {err}")
            else:
                with lock:
                    battles.extend(trio_results)
                if completed % 50 == 0 or completed == n:
                    rate = completed / (time.time() - t_start)
                    print(f"  {completed:4d}/{n}  trio:{len(trio_results):2d}  ({elapsed*1000:.0f}ms)  total:{len(battles)}  [{rate:.1f} tags/s]")

            if completed % SAVE_EVERY == 0:
                with lock:
                    snapshot = list(battles)
                with open(OUT / "trio_battles_partial.json", "w", encoding="utf-8") as f:
                    json.dump(snapshot, f, ensure_ascii=False)

    return battles, fail, rate_limited


def aggregate(battles):
    agg = defaultdict(lambda: {"picks": 0, "wins": 0, "ranks": []})
    seen = set()
    for b in battles:
        key = (b.get("battleTime", ""), b.get("_requester_tag", ""))
        if key in seen:
            continue
        seen.add(key)
        ev = b.get("event", {})
        bt = b.get("battle", {})
        teams = bt.get("teams", [])
        ti = b.get("_requester_team_idx")
        if ti is None or ti >= len(teams):
            continue
        rank = bt.get("rank") or 5
        is_win = rank <= 2
        for p in teams[ti]:
            br = (p.get("brawler") or {}).get("name", "?")
            mkey = (ev.get("map", "?"), br)
            agg[mkey]["picks"] += 1
            if is_win:
                agg[mkey]["wins"] += 1
            agg[mkey]["ranks"].append(rank)
    return agg, len(seen)


def _check_one_player(tag):
    """並列実行用: 1人のtrophy確認。"""
    try:
        data = fetch(f"/players/{quote(tag, safe='')}")
        return tag, data, None
    except HTTPError as e:
        return tag, None, e.code
    except Exception:
        return tag, None, "err"


def trophy_check_candidates(discovered, qualifying):
    """discovered の中で未確認のタグから N人 トロフィーチェック → qualifying に追加"""
    qual_tags = {q["tag"] for q in qualifying}
    candidates = [t for t in discovered if t not in qual_tags]
    if not candidates:
        return qualifying
    random.shuffle(candidates)
    candidates = candidates[:TROPHY_CHECK_LIMIT]
    print(f"\n[Phase 4] トロフィーチェック ({len(candidates)} 候補, {PARALLEL_WORKERS} 並列)")
    new_count = 0
    rate_limited = False
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as ex:
        futures = {ex.submit(_check_one_player, t): t for t in candidates}
        for fut in as_completed(futures):
            tag, data, err = fut.result()
            if err == 429:
                print("  ⚠ rate limit during trophy check, abort")
                rate_limited = True
                break
            if err is not None or data is None:
                continue
            tro = data.get("trophies", 0)
            if tro >= TROPHY_THRESHOLD:
                qualifying.append({
                    "tag": tag,
                    "trophies": tro,
                    "name": data.get("name", ""),
                    "checked": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                })
                new_count += 1
    qualifying.sort(key=lambda x: -x.get("trophies", 0))
    qualifying = qualifying[:MAX_QUALIFYING]
    print(f"  +{new_count} new qualifying (total {len(qualifying)})")
    return qualifying


def main():
    OUT.mkdir(exist_ok=True)
    t0 = time.time()

    tags = collect_tags()
    print(f"\nUnique tags: {len(tags)}\n推定時間: {len(tags) * 1.0 / 60:.1f}分\n")
    print("=" * 60)

    discovered = load_discovered()
    print(f"[discovered キャッシュ] {len(discovered)} tags")

    battles, fail, rate_limited = fetch_battles(tags, discovered)
    print("=" * 60)
    print(f"完了: {len(battles)} trio battles / 失敗 {fail} / rate_limited={rate_limited}")
    print(f"discovered: {len(discovered)} tags")
    save_discovered(discovered)

    out_raw = OUT / "trio_battles_full.json"
    with open(out_raw, "w", encoding="utf-8") as f:
        json.dump(battles, f, ensure_ascii=False)
    print(f"Saved: {out_raw}")

    print("\n[Phase 3] 集計")
    agg, unique_n = aggregate(battles)
    print(f"unique battles: {unique_n} / cells: {len(agg)}\n")

    # CSV出力
    rows = []
    for (m, br), s in agg.items():
        picks = s["picks"]
        wins = s["wins"]
        wr = wins / picks if picks else 0
        avg_r = sum(s["ranks"]) / len(s["ranks"]) if s["ranks"] else 0
        rows.append(
            {
                "map": m,
                "brawler": br,
                "picks": picks,
                "wins": wins,
                "win_rate": round(wr, 3),
                "avg_rank": round(avg_r, 2),
            }
        )
    rows.sort(key=lambda x: (x["map"], -x["picks"]))
    with open(OUT / "trio_meta_full.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["map", "brawler", "picks", "wins", "win_rate", "avg_rank"],
        )
        w.writeheader()
        w.writerows(rows)
    print(f"Saved: {OUT / 'trio_meta_full.csv'}")

    # マップ別picks サマリ
    map_total = defaultdict(int)
    for r in rows:
        map_total[r["map"]] += r["picks"]
    print("\n--- マップ別picks (上位20) ---")
    for m, c in sorted(map_total.items(), key=lambda x: -x[1])[:20]:
        print(f"  {c:5d}  {m}")

    # トロフィーチェック → qualifying プール拡大
    if not rate_limited:
        qualifying = load_qualifying()
        qualifying = trophy_check_candidates(discovered, qualifying)
        save_qualifying(qualifying)

    print(f"\n所要時間: {time.time() - t0:.1f}秒")


if __name__ == "__main__":
    main()
