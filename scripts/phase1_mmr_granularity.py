"""Phase 1: MMR粒度検証 — 「トリオの結果」 と「他モードの直近勝敗」 の相関を分析。

仮説:
  - MMRがモード共通なら、 他モードで連勝直後のトリオ試合は「強い敵に当たる→平均順位悪化」 傾向
  - モード別なら、 他モードの直近結果は無相関

入力:
  scripts/export_player.py で生成した CSV (出力例: out/player_YQ8YY09R.csv)

出力:
  per-player の指標 + 全プレイヤー集約レポート (stdout)
  ・トリオ試合 N
  ・直近他モードを K=10戦窓で「最近の勝率」 を計算
  ・トリオ rank との Spearman 相関
  ・トリオ rank<=2 (top2) を二値ラベルにし logistic 回帰の傾き


使い方:
  python scripts/phase1_mmr_granularity.py out/player_YQ8YY09R.csv
  python scripts/phase1_mmr_granularity.py out/player_*.csv

依存:
  pip install pandas scipy numpy
"""
import argparse
import csv
import sys
from pathlib import Path

try:
    import pandas as pd
    import numpy as np
    from scipy import stats
except ImportError:
    sys.exit("依存パッケージが必要: pip install pandas scipy numpy")


def is_win_for_mode(row) -> float | None:
    """モードごとに「勝ち=1, 負け=0, 引分/不明=None」 を返す。
    trio/duo/solo: rank<=2 で勝ち判定 (showdown 系)
    3v3: rank が無いので raw_json の result を見る (CSV にはまだ含めてない → None で返す)
    """
    mode = (row.get("mode") or "")
    rank = row.get("rank") or 0
    if mode in ("trioShowdown", "duoShowdown", "soloShowdown"):
        if rank <= 0:
            return None
        # solo は 10人で 1-5位が勝ち、 trio/duo は 1-2位が勝ち
        threshold = 5 if mode == "soloShowdown" else 2
        return 1.0 if rank <= threshold else 0.0
    # 3v3 系 (gemGrab, brawlBall, ...) は raw_json の battle.result が要る
    # 本スクリプトでは未対応 → None
    return None


def analyze_one(csv_path: Path, recent_window: int = 10):
    df = pd.read_csv(csv_path)
    if df.empty:
        return None
    df = df.sort_values("battle_time").reset_index(drop=True)
    df["win"] = df.apply(is_win_for_mode, axis=1)

    trio = df[df["mode"] == "trioShowdown"].copy()
    if trio.empty:
        return None

    # 各トリオ試合について、 その直前 recent_window 試合 (他モード含む) の勝率を計算
    recent_rates = []
    for idx in trio.index:
        prev = df.loc[:idx - 1]
        # 他モード (= trioShowdown以外) で win!=None のものから直近 recent_window
        other = prev[(prev["mode"] != "trioShowdown") & prev["win"].notna()].tail(recent_window)
        recent_rates.append(other["win"].mean() if len(other) > 0 else np.nan)
    trio = trio.assign(recent_other_win_rate=recent_rates)
    trio_valid = trio.dropna(subset=["recent_other_win_rate"])
    if len(trio_valid) < 20:
        return {"csv": csv_path.name, "trio_total": len(trio), "trio_valid": len(trio_valid), "note": "サンプル不足 (20未満)"}

    # 相関: 直近他モード勝率 vs トリオの rank (低い方が勝ち)
    spearman_rank, p_rank = stats.spearmanr(trio_valid["recent_other_win_rate"], trio_valid["rank"])
    # 二値: トリオ top2 と 直近他モード勝率
    trio_valid_top2 = (trio_valid["rank"] <= 2).astype(int)
    if trio_valid_top2.nunique() < 2:
        log_slope, log_p = (np.nan, np.nan)
    else:
        # ロジスティック回帰の代わりに 単純線形回帰 (近似)
        slope, intercept, r, p, se = stats.linregress(
            trio_valid["recent_other_win_rate"], trio_valid_top2
        )
        log_slope, log_p = slope, p

    return {
        "csv": csv_path.name,
        "trio_total": len(trio),
        "trio_valid": len(trio_valid),
        "trio_top2_rate": float(trio_valid_top2.mean()),
        "spearman_rank_vs_recent": float(spearman_rank),
        "p_rank": float(p_rank),
        "linreg_slope_top2_vs_recent": float(log_slope) if not np.isnan(log_slope) else None,
        "p_top2": float(log_p) if not np.isnan(log_p) else None,
        "interpretation": _interpret(spearman_rank, p_rank),
    }


def _interpret(rho, p):
    if rho is None or np.isnan(rho):
        return "データ不足"
    if p > 0.1:
        return "無相関 (p>0.10) → モード別の可能性 (他モード勝敗がトリオ結果に効かない)"
    if rho > 0:
        return f"正の相関 (rho={rho:.3f}, p={p:.3f}) → 他モード連勝後にトリオでランク悪化 ＝ MMR共通の傾向"
    return f"負の相関 (rho={rho:.3f}, p={p:.3f}) → 他モード連勝後にトリオでランク向上 (意外、 別要因か)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csvs", nargs="+", help="player CSVファイル (複数可)")
    ap.add_argument("--window", type=int, default=10, help="直近何戦の他モード勝率を見るか")
    args = ap.parse_args()

    results = []
    for p in args.csvs:
        path = Path(p)
        r = analyze_one(path, recent_window=args.window)
        if r:
            results.append(r)
            print("---")
            for k, v in r.items():
                print(f"  {k}: {v}")

    if len(results) > 1:
        print("\n=== 全プレイヤー集約 ===")
        rhos = [r["spearman_rank_vs_recent"] for r in results if isinstance(r.get("spearman_rank_vs_recent"), float)]
        if rhos:
            print(f"  spearman 平均: {np.mean(rhos):.3f}  中央値: {np.median(rhos):.3f}  N={len(rhos)}")
            pos = sum(1 for r in rhos if r > 0.05)
            neg = sum(1 for r in rhos if r < -0.05)
            print(f"  正の相関プレイヤー: {pos}, 負: {neg}, ほぼ無: {len(rhos) - pos - neg}")
        print()
        print("解釈ガイド:")
        print("  - 全体的に正の相関 (rho>0) が多い → MMR共通の可能性")
        print("  - ほぼ無相関 → MMR別の可能性")


if __name__ == "__main__":
    main()
