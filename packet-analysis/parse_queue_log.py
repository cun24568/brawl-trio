"""queue_log.jsonl をペアリング → queue_seconds 集計.

入力: bs_extract.py が吐く queue_log.jsonl
  各行: {"event": "queue_start"|"battle_start"|"queue_cancelled", "ts": float, "msg_type": int, ...}

出力: 標準出力に統計 + queue_pairs.jsonl に対応付け結果
"""
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).parent
LOG = HERE / "queue_log.jsonl"
OUT = HERE / "queue_pairs.jsonl"


def main():
    if not LOG.exists():
        print(f"no log file at {LOG}")
        sys.exit(1)
    events = []
    with LOG.open(encoding="utf-8") as f:
        for line in f:
            try:
                events.append(json.loads(line))
            except Exception:
                continue
    events.sort(key=lambda e: e["ts"])
    pairs = []
    last_start = None
    for e in events:
        ev = e["event"]
        if ev == "queue_start":
            last_start = e
        elif ev in ("queue_cancel", "queue_cancelled"):
            last_start = None
        elif ev == "battle_start" and last_start:
            pairs.append({
                "queue_start_ts": last_start["ts"],
                "battle_start_ts": e["ts"],
                "queue_seconds": e["ts"] - last_start["ts"],
            })
            last_start = None
    with OUT.open("w", encoding="utf-8") as f:
        for p in pairs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    if not pairs:
        print("no pairs found")
        return
    qs = [p["queue_seconds"] for p in pairs]
    qs.sort()
    print(f"N={len(pairs)}")
    print(f"  median = {qs[len(qs)//2]:.1f}s")
    print(f"  mean   = {statistics.mean(qs):.1f}s")
    print(f"  min    = {qs[0]:.1f}s")
    print(f"  max    = {qs[-1]:.1f}s")
    print(f"  p25-p75 = {qs[len(qs)//4]:.1f}-{qs[3*len(qs)//4]:.1f}s")
    print(f"→ output: {OUT}")


if __name__ == "__main__":
    main()
