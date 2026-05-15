# Analysis Scripts

`docs/mmr-research.md` の解析プロジェクト用 Python スクリプト集。

## セットアップ

```bash
pip install pandas numpy scipy pyarrow trueskill
```

## 1. プレイヤーデータ抽出 (`export_player.py`)

VPS上の `data/users.db` から特定プレイヤーの全モードバトルログを CSV/Parquet 化。

```bash
# CSV出力 (out/player_YQ8YY09R.csv)
python scripts/export_player.py "#YQ8YY09R"

# Parquet (大量データ向き、 pandas+pyarrow必要)
python scripts/export_player.py "#YQ8YY09R" --format parquet

# 期間指定
python scripts/export_player.py "#YQ8YY09R" --since 20260501T000000.000Z

# 別DB指定 (例: scpで持ってきたユーザーDB)
python scripts/export_player.py "#YQ8YY09R" --db /path/to/users.db
```

## 2. Phase 1: MMR粒度検証 (`phase1_mmr_granularity.py`)

「トリオの結果」 と「他モードの直近勝敗」 の相関を計算。

```bash
# 単一プレイヤー
python scripts/phase1_mmr_granularity.py out/player_YQ8YY09R.csv

# 複数プレイヤー (集約レポート)
python scripts/phase1_mmr_granularity.py out/player_*.csv

# 直近窓を変える
python scripts/phase1_mmr_granularity.py out/player_*.csv --window 20
```

### 解釈

- **rho > 0 で有意** (p<0.05): 他モード連勝後にトリオでランク悪化 = **MMR共通の傾向**
- **rho ≈ 0** (p>0.10): 他モード勝敗がトリオ結果に効かない = **MMR別の傾向**

## ワークフロー

```bash
# 1. VPSから users.db を持ってくる
scp soya@162.43.41.92:/home/soya/brawl-trio/data/users.db data/users.db

# 2. 対象プレイヤー (ウォッチリスト or 任意) をCSV化
for tag in YQ8YY09R GCLU9CUG GYQ9JPJ0Y; do
  python scripts/export_player.py "#$tag"
done

# 3. Phase 1分析
python scripts/phase1_mmr_granularity.py out/player_*.csv
```

## 次フェーズ

Phase 2/3/4 のスクリプトは `docs/mmr-research.md` 参照しながら順次追加予定:

- Phase 2: マッチング挙動の記述統計 (9人のトロフィー分散、 マッチング条件カーブ)
- Phase 3: TrueSkill 適用 (trio専業プレイヤー抽出 or 全モード正規化)
- Phase 4: 仮説検証 (シーズンリセット前後の保持等)
