# Brawl Stars Trio Showdown Meta DB

ブロスタ トリオサバイバルの実戦データから自動でメタ・推奨編成を集計するサイト。

## 構成

- **データ収集**: Brawl Stars 公式API + Brawlify API
- **集計**: Python (標準ライブラリのみ)
- **UI**: 静的 HTML/JS + Tailwind CDN
- **デプロイ**: Vercel (静的ホスティング)

## ローカル実行

```bash
# 1. .env に APIトークンを設定
cp .env.example .env
# (BRAWL_API_TOKEN を貼る)

# 2. マスタデータ取得
py fetch_data.py

# 3. クロール (10分程度)
py crawl_full.py

# 4. DB再ビルド
py build_db.py

# 5. UI起動
py -m http.server 8765
# → http://localhost:8765/ui/index.html
```

## 自動更新

`daily_update.bat` を Windows タスクスケジューラに登録：
```
powershell -ExecutionPolicy Bypass -File register_schedule.ps1
```

3時間ごとにクロール+DB更新が走る。

## ファイル

| ファイル | 役割 |
|---|---|
| `crawl_full.py` | 公式APIから複数プレイヤーのバトルログ収集 |
| `build_db.py` | CSVから UI用 db.json を生成 |
| `fetch_data.py` | Brawlifyからブロウラー/マップマスタ取得 |
| `manual_mappings.json` | 日本語名・現行ローテのオーバーレイ |
| `daily_update.bat` | クロール→DB更新の自動実行 |
| `register_schedule.ps1` | タスクスケジューラ登録 (3時間ごと) |
| `ui/` | フロントエンド (HTML/JS) |
| `data/db.json` | UIが読む統合データ |

## ライセンス

Brawl Stars 関連の画像・名称は Supercell の所有物。本リポジトリはファンメイドツール。
