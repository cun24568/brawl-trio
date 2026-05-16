"""公式 Brawl Stars API の全エンドポイント探索 + 隠しフィールド検出.

ドキュメント記載:
  /players/{tag}
  /players/{tag}/battlelog
  /clubs/{tag}
  /clubs/{tag}/members
  /rankings/{countryCode}/players
  /rankings/{countryCode}/clubs
  /rankings/{countryCode}/brawlers/{brawlerId}
  /rankings/{countryCode}/powerplay/seasons        (古い)
  /rankings/{countryCode}/powerplay/seasons/{id}   (古い)
  /brawlers
  /brawlers/{id}
  /events/rotation

未文書化候補 (推測):
  /players/{tag}/ranked            ← ガチバトル詳細?
  /players/{tag}/season            ← シーズン詳細?
  /rankings/{cc}/ranked            ← ガチバトルランキング?
  /rankings/global/brawlers/{id}/ranked
"""
import json
import urllib.request
import urllib.error
from pathlib import Path
from urllib.parse import quote


def load_token():
    p = Path("/home/soya/brawl-trio/.env")
    for line in p.read_text().splitlines():
        if line.startswith("BRAWL_API_TOKEN="):
            return line.split("=", 1)[1].strip()
    return None


TOKEN = load_token()
BASE = "https://api.brawlstars.com/v1"
TAG = "#YQ8YY09R"
CLUB_TAG = "#2J989V00Y"  # バトロワ勢


def probe(path):
    url = f"{BASE}{path}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            body = r.read()
            data = json.loads(body)
            return 200, data, len(body)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "ignore")[:200], 0
    except Exception as e:
        return -1, str(e), 0


def main():
    # 文書化済 (動作確認)
    documented = [
        f"/players/{quote(TAG)}",
        f"/players/{quote(TAG)}/battlelog",
        f"/clubs/{quote(CLUB_TAG)}",
        f"/clubs/{quote(CLUB_TAG)}/members",
        "/rankings/global/players",
        "/rankings/global/clubs",
        "/rankings/global/brawlers/16000000",  # SHELLY id
        "/brawlers",
        "/brawlers/16000000",
        "/events/rotation",
    ]
    # 推測 (未文書化、 試行)
    speculative = [
        f"/players/{quote(TAG)}/ranked",
        f"/players/{quote(TAG)}/season",
        f"/players/{quote(TAG)}/stats",
        f"/players/{quote(TAG)}/profile",
        f"/players/{quote(TAG)}/seasons",
        f"/players/{quote(TAG)}/matches",
        f"/players/{quote(TAG)}/queue",
        f"/players/{quote(TAG)}/brawlers",
        "/rankings/global/ranked",
        "/rankings/global/powerplay",
        "/rankings/global/elo",
        "/rankings/jp/ranked",
        "/rankings/jp/brawlers/16000000/ranked",
        "/ranked/seasons",
        "/ranked/leaderboard",
        "/matchmaking/queue",
        f"/players/{quote(TAG)}/ranked-history",
    ]

    print("=== ドキュメント済エンドポイント ===")
    for p in documented:
        code, data, n = probe(p)
        if code == 200:
            keys = list(data.keys()) if isinstance(data, dict) else f"list[{len(data)}]"
            print(f"  200 OK ({n:>7,}B)  {p}\n         keys={keys}")
        else:
            print(f"  {code}      {p}  -- {data[:100] if isinstance(data, str) else data}")

    print()
    print("=== 未文書化候補 (試行) ===")
    for p in speculative:
        code, data, n = probe(p)
        if code == 200:
            keys = list(data.keys()) if isinstance(data, dict) else f"list[{len(data)}]"
            print(f"  ★ 200 OK ({n:>7,}B)  {p}\n         keys={keys}")
            print(f"         sample: {json.dumps(data, ensure_ascii=False)[:400]}")
        else:
            print(f"  {code}      {p}")

    # ドキュメント記載のフィールド以外の発見済隠しフィールド (再確認)
    print()
    print("=== /players/{tag} の全フィールド (隠し含む) ===")
    code, data, n = probe(f"/players/{quote(TAG)}")
    if code == 200:
        for k, v in data.items():
            if isinstance(v, (list, dict)):
                print(f"  {k}: ({type(v).__name__})")
            else:
                print(f"  {k}: {v}")
        # brawlers[0] の全フィールド
        if data.get("brawlers"):
            print(f"  brawlers[0]:")
            for k, v in data["brawlers"][0].items():
                if isinstance(v, (list, dict)):
                    print(f"    {k}: ({type(v).__name__})")
                else:
                    print(f"    {k}: {v}")


if __name__ == "__main__":
    main()
