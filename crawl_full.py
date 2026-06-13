"""
拡張クロール: クラブ + global TOP200 + JP TOP200 + 高トロフィープレイヤー (永続キャッシュ)
- 20タグごとに途中保存(中断OK)
- 各タグの結果を逐次表示
- 完了後に自動で集計してCSV出力
- バトルログから対戦相手タグを発見 (discovered_tags.json)
- 50,000+トロフィープレイヤーをqualifying_tags.jsonに永続蓄積
- 毎cycleで最大100人ぶんトロチェック (徐々に拡大)
"""
import json
import random
import sys
import threading
import time
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
COUNTRIES = ["global", "JP", "KR", "US", "TW", "DE", "BR", "MX", "GB", "FR", "ES", "RU"]
DELAY = 0.15
TIMEOUT = 15
RETRIES = 3  # API timeoutやネットワークエラー時のリトライ回数
SAVE_EVERY = 200  # 並列化で件数が早く流れるので頻度下げる
PARALLEL_WORKERS = 8  # ulimit -u=200 のため抑制 (crawl_users と uvicorn と共存)

# トロフィー閾値で qualifying プールを永続蓄積
TROPHY_THRESHOLD = 50000
TROPHY_CHECK_LIMIT = 5000  # 1cycleで新規にチェックする数 (qualifying 早期成長)
MAX_QUALIFYING = 30000  # qualifyingプール上限 (上位trophy順で保持)
MAX_DISCOVERED = 2_000_000  # discovered キャッシュ上限
CRAWL_SAMPLE_SIZE = 30000  # 1cycleでqualifyingから sample してクロールする数 (= MAXなら全員)

DISCOVERED_FILE = OUT / "discovered_tags.json"
QUALIFYING_FILE = OUT / "qualifying_tags.json"
BATTLES_JSONL = OUT / "trio_battles.jsonl"  # 1行=1battle、append蓄積
BATTLES_LEGACY_JSON = OUT / "trio_battles_full.json"  # 旧形式 (互換のため残す)


def load_token():
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if line.startswith("BRAWL_API_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("token missing")


TOKEN = load_token()


def fetch(path):
    """timeout / 一時的エラーは自動リトライ。HTTPError(429,4xx,5xx)はそのまま投げる。"""
    last_err = None
    for attempt in range(RETRIES):
        req = Request(
            f"{API}{path}",
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Accept": "application/json",
                "User-Agent": "brawl-trio/0.1",
            },
        )
        try:
            with urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8"))
        except HTTPError:
            raise  # 4xx/5xxはリトライしない
        except (TimeoutError, URLError, OSError) as e:
            last_err = e
            if attempt < RETRIES - 1:
                time.sleep(1 + attempt)  # 1, 2, 3秒の指数バックオフ風
                continue
            raise


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


def battle_key(b):
    """battle dedup key: 同一battleを別プレイヤー視点で取得しても1件"""
    bt = b.get("battleTime", "")
    teams = b.get("battle", {}).get("teams", [])
    tags = sorted([p.get("tag", "") for team in teams for p in team])
    return bt + "|" + "|".join(tags)


def migrate_legacy_json():
    """旧 trio_battles_full.json があれば JSONL に1回限り変換"""
    if BATTLES_JSONL.exists():
        return
    if not BATTLES_LEGACY_JSON.exists():
        return
    print(f"Migrating {BATTLES_LEGACY_JSON.name} → {BATTLES_JSONL.name}")
    try:
        battles = json.loads(BATTLES_LEGACY_JSON.read_text(encoding="utf-8"))
        with open(BATTLES_JSONL, "w", encoding="utf-8") as f:
            for b in battles:
                f.write(json.dumps(b, ensure_ascii=False) + "\n")
        print(f"  migrated {len(battles)} battles")
    except Exception as e:
        print(f"  migration failed: {e}")


RECENT_DEDUP_DAYS = 10  # dedup対象は直近N日分のみ (battlelogは直近しか返さないので十分)
_KEY_MASK = 0xFFFFFFFFFFFFFFFF


def _key_hash(b):
    """battle_key の 64bit ハッシュ (str set より ~5倍省メモリ)"""
    return hash(battle_key(b)) & _KEY_MASK


def load_existing_battle_keys():
    """JSONLから既存battle keysを読み込む(streaming)。
    メモリ削減:
      - 直近 RECENT_DEDUP_DAYS 日分のみ対象 (公式battlelogは直近しか返さないので、
        それより古い試合と新規取得が衝突することはない)
      - キーは 64bit ハッシュ int で保持 (1000万件の文字列setだと ~2GB → int set で ~400MB)
    battleTime は "YYYYMMDDTHHMMSS.000Z" の zero-padded 形式なので文字列比較で日付カットオフ可能。
    """
    keys = set()
    if not BATTLES_JSONL.exists():
        return keys
    cutoff = time.strftime("%Y%m%dT%H%M%S", time.gmtime(time.time() - RECENT_DEDUP_DAYS * 86400))
    with open(BATTLES_JSONL, encoding="utf-8") as f:
        for line in f:
            # battleTime での高速 prefix フィルタ (json parse 前に文字列で足切り)
            # 行頭は {"battleTime": "20260613T..." なので 17文字目あたりに日時がある
            try:
                b = json.loads(line)
            except Exception:
                continue
            bt = b.get("battleTime", "")
            if bt[:15] < cutoff:  # 古い試合は dedup 不要
                continue
            keys.add(_key_hash(b))
    return keys


def append_battles_jsonl(battles):
    """新規battlesをJSONLに追記"""
    with open(BATTLES_JSONL, "a", encoding="utf-8") as f:
        for b in battles:
            f.write(json.dumps(b, ensure_ascii=False) + "\n")


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
    except Exception as e:
        print(f"  seed club FAIL: {type(e).__name__}: {e}")
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
        except Exception as e:
            print(f"  {cname} FAIL: {type(e).__name__}: {e}")

    # 各国
    for country in COUNTRIES:
        try:
            data = fetch(f"/rankings/{country}/players")
            items = data.get("items", [])
            for p in items:
                tags.add(p["tag"])
            print(f"  {country}: +{len(items)} (total {len(tags)})")
            time.sleep(DELAY)
        except Exception as e:
            print(f"  {country} FAIL: {type(e).__name__}: {e}")

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


def _process_one_battlelog(tag, discovered, existing_keys, lock):
    """1タグ分のbattlelog取得 → trio抽出 + dedup + discovered更新。スレッドセーフ。"""
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
        # dedup: 既存JSONLや今cycle内の他workerで取得済みならskip (64bit ハッシュで判定)
        k = _key_hash(b)
        with lock:
            if k in existing_keys:
                continue
            existing_keys.add(k)  # 同cycle内重複も防止
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
    if new_tags_local:
        with lock:
            discovered.update(new_tags_local)
    return tag, trio_battles, None, time.time() - t0


def fetch_battles(tags, discovered, existing_keys):
    new_battles = []
    fail = 0
    rate_limited = False
    lock = threading.Lock()
    n = len(tags)
    print(f"[Phase 2] バトルログ取得 ({n} tags, {PARALLEL_WORKERS} 並列, dedup against {len(existing_keys)} existing)")
    print("=" * 60)
    t_start = time.time()

    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as ex:
        futures = {
            ex.submit(_process_one_battlelog, tag, discovered, existing_keys, lock): tag
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
                for f in futures:
                    f.cancel()
                break
            elif err is not None:
                fail += 1
                print(f"  {completed:4d}/{n}  {tag:<12} {err}")
            else:
                with lock:
                    new_battles.extend(trio_results)
                if completed % 50 == 0 or completed == n:
                    rate = completed / (time.time() - t_start)
                    print(f"  {completed:4d}/{n}  new:{len(trio_results):2d}  ({elapsed*1000:.0f}ms)  cycle_new:{len(new_battles)}  [{rate:.1f} tags/s]")

            # 100件ごとにJSONL flush (中断対策)
            if completed % SAVE_EVERY == 0:
                with lock:
                    flush_batch = list(new_battles)
                    new_battles.clear()
                if flush_batch:
                    append_battles_jsonl(flush_batch)

    # 残りをflush
    if new_battles:
        append_battles_jsonl(new_battles)

    return len(new_battles), fail, rate_limited


def _check_one_player(tag):
    """並列実行用: 1人のtrophy確認。"""
    try:
        data = fetch(f"/players/{quote(tag, safe='')}")
        return tag, data, None
    except HTTPError as e:
        return tag, None, e.code
    except Exception:
        return tag, None, "err"


def get_dynamic_threshold(qualifying):
    """qualifying が上限近くなったら閾値を bottom 5% qualifier の trophy に引き上げ"""
    if len(qualifying) < MAX_QUALIFYING * 0.95:
        return TROPHY_THRESHOLD
    sorted_q = sorted(qualifying, key=lambda x: x.get("trophies", 0))
    idx = max(0, int(len(sorted_q) * 0.05))
    bottom_trophy = sorted_q[idx].get("trophies", TROPHY_THRESHOLD)
    return max(TROPHY_THRESHOLD, bottom_trophy)


def trophy_check_candidates(discovered, qualifying):
    """discovered の中で未確認のタグから N人 トロフィーチェック → qualifying に追加"""
    qual_tags = {q["tag"] for q in qualifying}
    candidates = [t for t in discovered if t not in qual_tags]
    if not candidates:
        return qualifying
    random.shuffle(candidates)
    candidates = candidates[:TROPHY_CHECK_LIMIT]
    threshold = get_dynamic_threshold(qualifying)
    if threshold > TROPHY_THRESHOLD:
        print(f"\n[Phase 4] トロフィーチェック ({len(candidates)} 候補, {PARALLEL_WORKERS} 並列, 動的閾値: {threshold}+)")
    else:
        print(f"\n[Phase 4] トロフィーチェック ({len(candidates)} 候補, {PARALLEL_WORKERS} 並列, 閾値: {threshold}+)")
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
            if tro >= threshold:
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

    # 旧JSON → JSONL 移行 (1回限り)
    migrate_legacy_json()

    tags = collect_tags()
    print(f"\nUnique tags: {len(tags)}\n推定時間: {len(tags) * 0.2:.1f}分 (8並列)\n")
    print("=" * 60)

    discovered = load_discovered()
    print(f"[discovered キャッシュ] {len(discovered)} tags")

    print(f"[既存battlelog読込中...]")
    existing_keys = load_existing_battle_keys()
    print(f"[既存] {len(existing_keys)} battles")

    new_count, fail, rate_limited = fetch_battles(tags, discovered, existing_keys)
    print("=" * 60)
    print(f"完了: +{new_count} new trio battles (累積 {len(existing_keys)+new_count}) / 失敗 {fail} / rate_limited={rate_limited}")
    print(f"discovered: {len(discovered)} tags")
    save_discovered(discovered)

    print(f"Saved: {BATTLES_JSONL}")
    # 集計 + db.json 生成は build_db.py が JSONL から直接行うため、 ここでは行わない
    # (旧 aggregate_from_jsonl + trio_meta_full.csv は未使用 = メモリ/IO の無駄だったので削除)

    # トロフィーチェック → qualifying プール拡大
    if not rate_limited:
        qualifying = load_qualifying()
        qualifying = trophy_check_candidates(discovered, qualifying)
        save_qualifying(qualifying)

    print(f"\n所要時間: {time.time() - t0:.1f}秒")


if __name__ == "__main__":
    main()
