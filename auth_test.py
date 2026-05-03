"""
公式API 認証だけ確認するテスト(プレイヤータグ不要)。
.env のトークンが有効かどうかだけチェックする。
"""
import json
import os
import sys
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError

API = "https://api.brawlstars.com/v1"
ENV_FILE = Path(__file__).parent / ".env"


def load_env():
    if not ENV_FILE.exists():
        print("ERROR: .env が見つかりません", file=sys.stderr)
        sys.exit(1)
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def main():
    load_env()
    token = os.environ.get("BRAWL_API_TOKEN", "").strip()
    if not token:
        print("ERROR: BRAWL_API_TOKEN が空", file=sys.stderr)
        sys.exit(1)

    # 形式チェック(JWTは . で3分割)
    parts = token.split(".")
    if len(parts) != 3:
        print(f"ERROR: トークン形式不正 (segments={len(parts)})", file=sys.stderr)
        sys.exit(1)
    print(f"Token format OK ({len(parts)} segments, total {len(token)} chars)")

    # /brawlers は認証必要だがプレイヤータグ不要
    req = Request(
        f"{API}/brawlers",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "brawl-trio/0.1",
        },
    )
    try:
        with urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
            items = data.get("items", [])
            print(f"OK: 認証成功 / {len(items)} brawlers returned")
            if items:
                print(f"  sample: id={items[0].get('id')} name={items[0].get('name')}")
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"FAIL: HTTP {e.code}\n{body}", file=sys.stderr)
        if e.code == 403:
            print("\n→ IPがホワイトリストにないかも。現在のIPを確認:", file=sys.stderr)
        elif e.code == 401:
            print("\n→ トークンが無効。コピーミスの可能性、再発行推奨", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
