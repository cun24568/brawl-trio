"""
壊れたトークンの自動修復(ブルートフォース)。
segment2 を1文字ずつ削除しながら API に問い合わせ、200 が返る組み合わせを探す。

前提: コピー時に1文字だけ余計に挿入されているケース。
それ以外の壊れ方なら見つからない(その場合はトークン再発行)。
"""
import sys
import time
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError

API = "https://api.brawlstars.com/v1/brawlers"
ENV_FILE = Path(__file__).parent / ".env"


def load_token() -> str:
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("BRAWL_API_TOKEN="):
            return line.split("=", 1)[1].strip()
    return ""


def test(token: str) -> int:
    """戻り値: HTTPステータスコード。成功なら200。"""
    req = Request(
        API,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "brawl-trio/0.1",
        },
    )
    try:
        with urlopen(req, timeout=10) as r:
            return r.status
    except HTTPError as e:
        return e.code


def main():
    token = load_token()
    if not token:
        print("ERROR: トークンが空", file=sys.stderr)
        sys.exit(1)

    parts = token.split(".")
    if len(parts) != 3:
        print(f"ERROR: セグメント数 {len(parts)}", file=sys.stderr)
        sys.exit(1)

    h, p, s = parts
    print(f"Header: {len(h)} / Payload: {len(p)} / Signature: {len(s)}")

    # まず元のままを試す(念のため)
    code = test(token)
    print(f"元のままテスト: HTTP {code}")
    if code == 200:
        print("OK: 元のトークンが既に有効でした")
        return

    print(f"\nペイロード(segment2)から1文字ずつ削除して試行 ({len(p)}回)...")
    found = None
    for i in range(len(p)):
        candidate_p = p[:i] + p[i + 1 :]
        candidate = f"{h}.{candidate_p}.{s}"
        code = test(candidate)
        if code == 200:
            found = (i, p[i], candidate)
            print(f"\n✓ HIT! 位置 {i} の '{p[i]}' を削除すると認証成功")
            break
        if i % 20 == 0:
            print(f"  ...{i}/{len(p)} (last code: {code})", end="\r", flush=True)
        time.sleep(0.25)  # rate limit safety

    if found:
        i, c, fixed = found
        ENV_FILE.write_text(f"BRAWL_API_TOKEN={fixed}\n", encoding="utf-8")
        print(f"\n保存完了: {len(fixed)} chars")
        print("次: py auth_test.py")
    else:
        print("\n見つかりませんでした。1文字削除では復元不能。")
        print("選択肢:")
        print("  1. 別ブラウザ(Edge/Chrome切替)で再発行")
        print("  2. シークレットウィンドウ(拡張機能無効)で再発行")
        print("  3. F12コンソール経由で抽出")


if __name__ == "__main__":
    main()
