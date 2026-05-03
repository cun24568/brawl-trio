"""トークンの特徴だけ抽出して表示する（本体は伏字）。"""
import base64
import hashlib
import json
from pathlib import Path

ENV_FILE = Path(__file__).parent / ".env"


def b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def main():
    text = ENV_FILE.read_text(encoding="utf-8")
    token = ""
    for line in text.splitlines():
        if line.startswith("BRAWL_API_TOKEN="):
            token = line.split("=", 1)[1].strip()
            break

    if not token:
        print("BRAWL_API_TOKEN が空")
        return

    print(f"Total length      : {len(token)}")
    print(f"First 20 chars    : {token[:20]}...")
    print(f"Last 20 chars     : ...{token[-20:]}")
    print(f"Whitespace inside : {sum(1 for c in token if c.isspace())}")
    print(f"SHA256 (確認用)   : {hashlib.sha256(token.encode()).hexdigest()[:16]}...")

    parts = token.split(".")
    print(f"Segments (dot-split): {len(parts)}")
    for i, name in enumerate(["header", "payload", "signature"]):
        if i < len(parts):
            print(f"  {name:10s}: {len(parts[i])} chars")

    # ペイロードを復号して中身を見る
    if len(parts) >= 2:
        try:
            payload = json.loads(b64url_decode(parts[1]))
            print(f"\nPayload decoded:")
            print(f"  iss   : {payload.get('iss')}")
            print(f"  aud   : {payload.get('aud')}")
            print(f"  scopes: {payload.get('scopes')}")
            limits = payload.get("limits", [])
            for l in limits:
                if "cidrs" in l:
                    print(f"  IPs   : {l['cidrs']}  ← ここが '60.73.197.33' であるべき")
                else:
                    print(f"  limit : {l}")
        except Exception as e:
            print(f"\nPayload decode failed: {e}")
            print("→ トークンが破損している証拠")


if __name__ == "__main__":
    main()
