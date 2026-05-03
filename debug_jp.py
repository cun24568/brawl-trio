"""JP マッピングのdebug"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DATA = Path(__file__).parent / "data"

brawlers = json.loads((DATA / "brawlers.json").read_text(encoding="utf-8"))
manual = json.loads((DATA / "manual_mappings.json").read_text(encoding="utf-8"))
jp = manual.get("brawler_jp_names", {})

# 探す対象 (英表記が残ってる疑いの)
TARGETS = ["EL PRIMO", "EL-PRIMO", "EL_PRIMO", "ELPRIMO", "JAE-YONG", "KAZE", "NANI", "GLOWBERT"]

print("=== brawlers.json から該当 ===")
for x in brawlers:
    n = x.get("name", "")
    if any(t in n.upper() for t in ["PRIMO", "JAE", "KAZE", "NANI", "GLOWBERT"]):
        h = x.get("hash", "")
        mapped = jp.get(h.lower(), "<missing>")
        print(f"  EN={n:<15} hash={h:<25} JP={mapped}")
