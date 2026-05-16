"""公式 Brawl Stars API の積極的な探索 (404突破試行).

戦略:
1. ベースパス(/v1)以外のバージョン (/v2, /v3, /beta) 試行
2. キャメル/スネーク/ケバブのバリエーション総当たり
3. クエリパラメータ拡張 (?include=, ?expand=, ?fields=)
4. メソッド変更 (POST, PUT, HEAD, OPTIONS)
5. 既存パスの「変な」 拡張
"""
import json
import urllib.request
import urllib.error
from pathlib import Path
from urllib.parse import quote


def load_token():
    for line in Path("/home/soya/brawl-trio/.env").read_text().splitlines():
        if line.startswith("BRAWL_API_TOKEN="):
            return line.split("=", 1)[1].strip()


TOKEN = load_token()
TAG = "#YQ8YY09R"
TAG_ENC = quote(TAG)


def probe(url, method="GET"):
    req = urllib.request.Request(
        url,
        method=method,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as r:
            body = r.read()
            return r.status, body[:500].decode("utf-8", "ignore"), len(body)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")[:200] if e.fp else ""
        return e.code, body, 0
    except Exception as e:
        return -1, str(e)[:100], 0


# 試行候補
versions = ["v1", "v2", "v3", "beta", ""]  # 末尾"" は /api 直
bases = [f"https://api.brawlstars.com/{v}" if v else "https://api.brawlstars.com" for v in versions]

# 推測パス (player単位)
player_paths = [
    f"/players/{TAG_ENC}/ranked",
    f"/players/{TAG_ENC}/ranked-play",
    f"/players/{TAG_ENC}/rankedPlay",
    f"/players/{TAG_ENC}/ranked_play",
    f"/players/{TAG_ENC}/rankedplay",
    f"/players/{TAG_ENC}/ranked-stats",
    f"/players/{TAG_ENC}/stats",
    f"/players/{TAG_ENC}/season",
    f"/players/{TAG_ENC}/seasons",
    f"/players/{TAG_ENC}/seasons/current",
    f"/players/{TAG_ENC}/season-stats",
    f"/players/{TAG_ENC}/seasonStats",
    f"/players/{TAG_ENC}/match-history",
    f"/players/{TAG_ENC}/matchHistory",
    f"/players/{TAG_ENC}/recent-battles",
    f"/players/{TAG_ENC}/recent",
    f"/players/{TAG_ENC}/history",
    f"/players/{TAG_ENC}/profile",
    f"/players/{TAG_ENC}/info",
    f"/players/{TAG_ENC}/elo",
    f"/players/{TAG_ENC}/rating",
    f"/players/{TAG_ENC}/queue",
    f"/players/{TAG_ENC}/mmr",
    f"/players/{TAG_ENC}/division",
    f"/players/{TAG_ENC}/league",
    f"/players/{TAG_ENC}/leagues",
    f"/players/{TAG_ENC}/brawlers",
    f"/players/{TAG_ENC}/brawlers/16000000",
    f"/players/{TAG_ENC}/brawler/16000000",
]

# 全般
general_paths = [
    "/seasons",
    "/seasons/current",
    "/seasons/44",  # rankedSeasonId
    "/seasons/44/leaderboard",
    "/divisions",
    "/leagues",
    "/leaderboards",
    "/leaderboards/global",
    "/ranked",
    "/ranked/current",
    "/ranked/leaderboard",
    "/ranked/leaderboard/global",
    "/ranked/seasons",
    "/ranked/seasons/current",
    "/modes",
    "/gamemodes",
    "/tiers",
    "/trophyTiers",
    "/trophy-tiers",
    "/news",
    "/events/current",
    "/events/upcoming",
    "/events/all",
    "/maps",
    "/maps/15000955",  # Cavern Churn
    "/icons",
    "/quests",
    "/search/players",
    "/search/clubs",
    "/clubs/search",
    "/club-search",
]

# クエリパラメータ拡張
query_extensions = [
    f"/players/{TAG_ENC}?include=ranked",
    f"/players/{TAG_ENC}?fields=all",
    f"/players/{TAG_ENC}?expand=brawlers",
    f"/players/{TAG_ENC}?verbose=true",
    f"/players/{TAG_ENC}?debug=1",
]

# rankings 拡張
ranking_paths = [
    "/rankings/global/ranked",
    "/rankings/global/rankedPlay",
    "/rankings/global/elo",
    "/rankings/global/division",
    "/rankings/global/seasonal",
    "/rankings/jp/ranked",
    "/rankings/global/players?type=ranked",
    "/rankings/global/players?mode=ranked",
]


def main():
    found = []
    methods = ["GET", "HEAD", "OPTIONS", "POST"]
    print("=== ベースURLバージョン試行 (/v1 と他) ===")
    for base in bases:
        url = f"{base}/players/{TAG_ENC}"
        code, body, n = probe(url)
        status = "★ 200" if code == 200 else f"  {code}"
        print(f"  {status}  {url}")

    print(f"\n=== player単位 推測パス × method ({len(player_paths)}件) ===")
    for path in player_paths:
        for method in ["GET", "POST"]:
            code, body, n = probe(f"https://api.brawlstars.com/v1{path}", method)
            if code != 404 and code != -1:
                print(f"  ★ {code} {method:<6}  {path}  body={body[:80]}")
                found.append((path, method, code, body))

    print(f"\n=== general推測パス ===")
    for path in general_paths:
        code, body, n = probe(f"https://api.brawlstars.com/v1{path}")
        if code != 404 and code != -1:
            print(f"  ★ {code}  {path}  body={body[:80]}")
            found.append((path, "GET", code, body))

    print(f"\n=== クエリパラメータ拡張 ===")
    for path in query_extensions:
        code, body, n = probe(f"https://api.brawlstars.com/v1{path}")
        if code != 200:
            print(f"  {code}  {path}  body={body[:80]}")
        else:
            # 既存と比べて差分があるか確認
            base_code, base_body, base_n = probe(f"https://api.brawlstars.com/v1/players/{TAG_ENC}")
            if abs(n - base_n) > 100:
                print(f"  ★ 200 ({n}B vs base {base_n}B)  {path}")
                found.append((path, "GET", code, "size diff"))
            else:
                print(f"  200 同サイズ {path} ({n}B)")

    print(f"\n=== rankings系拡張 ===")
    for path in ranking_paths:
        code, body, n = probe(f"https://api.brawlstars.com/v1{path}")
        if code != 404 and code != -1:
            print(f"  ★ {code}  {path}  body={body[:80]}")
            found.append((path, "GET", code, body))

    # OPTIONS でルート一覧取れるか
    print(f"\n=== OPTIONS リクエストでルート発見試行 ===")
    for url in ["https://api.brawlstars.com/v1", "https://api.brawlstars.com/v1/", "https://api.brawlstars.com"]:
        code, body, n = probe(url, "OPTIONS")
        print(f"  {code}  {url}  body={body[:100]}")

    print(f"\n=== 結果サマリ ===")
    print(f"探索総数: 多数")
    print(f"突破成功: {len(found)} 個")
    for p, m, c, b in found:
        print(f"  {c} {m:<6} {p}")


if __name__ == "__main__":
    main()
