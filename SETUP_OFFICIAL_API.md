# Brawl Stars 公式API セットアップ

## 1. アカウント作成

https://developer.brawlstars.com/#/register

- メアドとパスワードを入力 → メール認証
- ログイン

## 2. API Key 作成

ログイン後の画面で「Create New Key」：

| 項目 | 入力値 |
|---|---|
| Name | brawl-trio-dev |
| Description | (任意) |
| Allowed IP Addresses | **60.73.197.33** |

→ Create を押すと長いトークン文字列が表示される（**この画面を閉じると再表示できない**ので必ずコピー）

> ⚠ IPが変わったら、Key画面で「Edit」→ 新IPを追加。`Get-NetIPAddress` ではなく必ず外部から見えるグローバルIPを使う（`api.ipify.org`で確認）。

## 3. .env ファイル作成

このプロジェクトの `.env` にトークンを保存：

```bash
# C:\Users\himas\OneDrive\デスクトップ\code\brawl-trio\.env
BRAWL_API_TOKEN=eyJ0eXAiOiJKV1QiLCJhbGc...(コピーしたトークン)
```

`.env.example` をコピーして `.env` にリネームしてもOK。

## 4. テスト実行

自分のプレイヤータグ（プロフィールに表示される `#XXXXXXX` 形式）で疎通確認：

```bash
py official_api_test.py "#YOUR_TAG"
```

成功すれば、プレイヤー名・トロフィー・所持ブロウラー数・直近1戦が表示される。

## トラブルシューティング

| 症状 | 原因 |
|---|---|
| 403 Forbidden | IPが許可リストに無い → Edit Keyで現IPを追加 |
| 401 Unauthorized | トークンが間違っているか、有効期限切れ |
| 404 Not Found | プレイヤータグの `#` を `%23` に変換し忘れ（テストスクリプトは自動変換するので通常起きない） |
| 429 Too Many Requests | レート制限。数秒待つ |

## .env を Git に上げない

`.gitignore` に `.env` が入っていることを必ず確認。トークン漏洩は致命的。
