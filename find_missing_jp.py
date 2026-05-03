"""未JPマッピングのブロウラーを表示"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DATA = Path(__file__).parent / "data"
brawlers = json.loads((DATA / "brawlers.json").read_text(encoding="utf-8"))
manual = json.loads((DATA / "manual_mappings.json").read_text(encoding="utf-8"))
jp = {k.lower() for k in manual.get("brawler_jp_names", {})}
missing = [b for b in brawlers if b.get("hash", "").lower() not in jp]
print(f"Total brawlers: {len(brawlers)}")
print(f"With JP names : {len(brawlers) - len(missing)}")
print(f"Missing JP    : {len(missing)}")
print()
for b in sorted(missing, key=lambda x: x.get("id", 0)):
    print(f"  hash={b.get('hash'):<30}  EN={b.get('name')}")
