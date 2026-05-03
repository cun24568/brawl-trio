"""
新しいAPIトークンを安全に .env に保存する。
- Unicode正規化 (NFKC) で全角/特殊文字を半角化
- base64url の許可文字以外を全削除 (ゼロ幅スペース・見えない文字を除去)
- 各クリーニング段階の文字数を表示してどこで何が消えたかが見える

使い方:
  py update_token.py
  プロンプトに右クリックでペースト → Enter
"""
import re
import sys
import unicodedata
from pathlib import Path

ENV_FILE = Path(__file__).parent / ".env"
ALLOWED = re.compile(r"[^A-Za-z0-9._-]")


def main():
    print("新しいトークンを貼り付けて Enter:")
    raw = input()

    print(f"\n--- クリーニング工程 ---")
    print(f"raw 入力             : {len(raw)} chars / {len(raw.encode('utf-8'))} bytes")

    # 各文字のコードポイントで非ASCII見えない文字を検出
    invisible = [(i, c, hex(ord(c))) for i, c in enumerate(raw) if ord(c) > 127 or (c.isascii() and not c.isprintable() and c not in "\t\n\r ")]
    if invisible:
        print(f"非ASCII/不可視文字  : {len(invisible)}個")
        for i, c, h in invisible[:10]:
            print(f"  pos {i}: {h} ({unicodedata.name(c, '?')})")

    # NFKC正規化(全角→半角、互換文字統一)
    nfkc = unicodedata.normalize("NFKC", raw)
    print(f"NFKC正規化後         : {len(nfkc)} chars")

    # base64url許可文字以外を全削除
    cleaned = ALLOWED.sub("", nfkc)
    print(f"base64url外文字削除後: {len(cleaned)} chars")

    parts = cleaned.split(".")
    print(f"セグメント数         : {len(parts)}")
    for i, p in enumerate(parts):
        marker = "OK" if len(p) % 4 != 1 else "NG (mod4=1)"
        print(f"  segment{i + 1}: {len(p)} chars [{marker}]")

    if len(parts) != 3:
        print("\nERROR: JWTは3パーツ必要", file=sys.stderr)
        sys.exit(1)

    if any(len(p) % 4 == 1 for p in parts):
        print("\nERROR: base64長が不正なセグメントあり。コピー時の文字落ちか、サイト側の問題。", file=sys.stderr)
        print("対処:", file=sys.stderr)
        print("  1. ブラウザのデベロッパーツール(F12)→Console で `copy(prompt())` を実行", file=sys.stderr)
        print("  2. 開いた入力欄にトークンを貼り付け→Enter", file=sys.stderr)
        print("  3. クリップボードに正規化された値が入る", file=sys.stderr)
        sys.exit(1)

    ENV_FILE.write_text(f"BRAWL_API_TOKEN={cleaned}\n", encoding="utf-8")
    print(f"\nOK: {len(cleaned)} chars saved to {ENV_FILE}")
    print("次: py auth_test.py")


if __name__ == "__main__":
    main()
