# packet-analysis (C案 仮想環境)

⚠️ TOS違反リスクあり。 サブ垢で実施。 詳細は `docs/tos-bypass-research.md` 参照。

## 環境

VPS (162.43.41.92) `/home/soya/brawl-trio/packet-analysis/venv/` に構築済み:

- mitmproxy 12.2.3
- frida 17.9.10 + frida-tools 14.8.2
- cryptography 48.0.0
- pycryptodome 3.23.0

## 起動方法

```bash
ssh soya@162.43.41.92
cd /home/soya/brawl-trio/packet-analysis
source venv/bin/activate
mitmdump -s bs_extract.py --mode transparent -p 8080 -w capture.mitm
# 別端末で frida
frida -U -f com.supercell.brawlstars -l frida-bypass.js --no-pause
```

## ファイル

- `bs_extract.py` — mitmproxy addon。 Brawl Stars TCPパケットから msgType を識別し
  `queue_log.jsonl` に `{event, ts, msg_type}` を逐次保存。
- `frida-bypass.js` — Android 用 Frida script。 SSL ピン留めを無効化。
- `parse_queue_log.py` — `queue_log.jsonl` を集計して queue_seconds を出力。
- `extract_rc4_key.js` — `libgame.so` の暗号鍵を ランタイムダンプする Frida hook。

## 注意

- Android root + frida-server 配置済 + 端末プロキシ設定 → 全部 user 側準備が必要
- iOS は jailbreak 必要 (同様)
- VPS は解析サーバ側 (mitmproxy + 集計のみ)。 端末→VPS:8080 にトンネルさせる構成想定
- 集計結果は本リポジトリの DB には `notes='packet_capture'` 付きでのみ保存予定 (生payload は載せない)
