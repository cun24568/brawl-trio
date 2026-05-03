"""公式APIのbrawlersエンドポイントの中身確認"""
import json
import os
import sys
from pathlib import Path
from urllib.request import urlopen, Request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ENV_FILE = Path(__file__).parent / ".env"

# .env load
for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
    if line.startswith("BRAWL_API_TOKEN="):
        os.environ["BRAWL_API_TOKEN"] = line.split("=", 1)[1].strip()

TOKEN = os.environ["BRAWL_API_TOKEN"]
req = Request(
    "https://api.brawlstars.com/v1/brawlers",
    headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"},
)
data = json.loads(urlopen(req, timeout=15).read())
items = data.get("items", [])
print(f"Total: {len(items)}")
if items:
    print(f"Keys in first: {list(items[0].keys())}")
    print()
    print("Sample first 3:")
    for x in items[:3]:
        print(f"  {json.dumps(x, ensure_ascii=False)[:300]}")

# 名前と id だけ全部
print()
print("All names:")
for x in sorted(items, key=lambda y: y.get("id", 0)):
    print(f"  {x.get('id'):8d}  {x.get('name')}")
