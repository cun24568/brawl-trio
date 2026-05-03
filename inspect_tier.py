"""新しいティアリングが妥当か確認"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
db = json.loads((Path(__file__).parent / "data" / "db.json").read_text(encoding="utf-8"))

for m in db["maps"][:5]:
    print(f"\n=== {m.get('name_jp') or m['name']} (picks={m['total_picks']}) ===")
    print(f"map平均: WR={m['map_avg_wr']*100:.1f}%, rank={m['map_avg_rank']:.2f}")
    print(f"{'Tier':>4} {'Brawler':<15} {'Score':>7} {'WR':>6} {'Bayes':>6} {'Δ':>6} {'picks':>5} {'rank':>5}")
    for t in m["tier_list"][:10]:
        delta = (t["bayes_wr"] - m["map_avg_wr"]) * 100
        print(f"  {t['tier']:>2} {t['brawler']:<15} {t['score']:>7.2f} "
              f"{t['win_rate']*100:>5.1f}% {t['bayes_wr']*100:>5.1f}% "
              f"{delta:+5.1f}% {t['picks']:>5} {t['avg_rank']:>5.2f}")
