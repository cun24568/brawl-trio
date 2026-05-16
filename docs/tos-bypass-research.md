# C案: 通信解析でマッチング時間を直接取得する手順書

⚠️ **重要**: 本書はゲーム通信プロトコルを解析する手順を扱う。Supercell利用規約 (TOS) では
クライアントの逆解析・自動化・改造系ツールの使用が禁止されている。**研究目的での個人利用に限定し、
収集したデータの公開・共有・自動投稿BOT等への流用は行わない**。本リポジトリには解析結果のみを
集計値として取り込み、生パケットやアカウント識別可能データは載せない。

ban されても文句は言えないリスクがある。**サブ垢で実施**を推奨。

## 目的
B案 (battlelog ポーリング) で取れる `queue_seconds` は「キュー押下〜試合開始」の近似値であり、
- 押下を忘れたら計測されない
- `duration` (試合長) の取得タイミングずれで ±15秒程度の誤差
- 公式APIの battleTime は秒精度かつ更新遅延 30-60秒

C案 (通信解析) なら以下が**真値**で取れる:
- マッチング開始/完了の正確な時刻
- マッチング中のキャンセル
- マッチ成立時の相手側情報 (一部、サーバが送ってくる場合)
- ロビー→ゲーム開始のラグ
- 内部 MMR (もしクライアントに送られていれば)

## アーキテクチャ概要

```
[Brawl Stars Android/iOS]
        ↓ HTTPS (TCP 9339? UDP?)
        ↓ ※Supercellは独自バイナリプロトコル (Magic Tea Protocol)、 RC4/AESで暗号化
[mitmproxy 透過プロキシ] ← Frida で証明書ピン留めバイパス
        ↓ 平文 (バイナリ)
[Wireshark + supercell-protocol-decoder]
        ↓ パケット種別判定 + フィールド抽出
[Python script] → SQLite/JSONL に queue_start/queue_end 時刻保存
```

## 必要環境

### ハードウェア
- 解析用 PC (Linux 推奨、 Windows + WSL2 でも可)
- Android 端末 (root 必須) または iOS (jailbreak 必須)
  - Android エミュレータ (BlueStacks/LDPlayer) は Supercell が検出するので **非推奨**
  - 実機推奨: Pixel 系 root 化済が情報多い

### ソフトウェア
- [mitmproxy](https://mitmproxy.org/) (Python 3.10+)
- [Frida](https://frida.re/) + frida-tools
- [objection](https://github.com/sensepost/objection) (Fridaラッパ)
- [Wireshark](https://www.wireshark.org/) (検証用、 必須ではない)
- [bsdebugger](https://github.com/RoyalDev/bsdebugger) または類似の Brawl Stars 専用パーサ (存在すれば)

## 手順 1: 端末の準備

### Android (root)
```bash
# Magisk + LSPosed 推奨
adb shell su -c "echo done"  # root 確認
# Frida server を端末にプッシュ
wget https://github.com/frida/frida/releases/download/16.x/frida-server-16.x-android-arm64.xz
xz -d frida-server-*.xz
adb push frida-server /data/local/tmp/
adb shell "su -c 'chmod 755 /data/local/tmp/frida-server && /data/local/tmp/frida-server &'"
# ホスト側
frida-ps -U  # プロセス一覧が出れば成功
```

### iOS (jailbreak)
- Frida Cydia Repo: `build.frida.re`
- 同様に `frida-ps -U` で確認

## 手順 2: mitmproxy 透過プロキシ起動

```bash
# ホスト PC で
mitmproxy --mode transparent --showhost -p 8080
# または addons で自動保存
mitmdump -w brawl-capture.mitm --mode transparent
```

端末側のプロキシ設定:
```
Wi-Fi 設定 → プロキシ手動 → ホストPC IP:8080
証明書: mitmproxy-ca-cert.pem を端末にインストール (システム証明書として)
  Android: /system/etc/security/cacerts/ に hash 名でコピー
  iOS: 設定 → 一般 → プロファイル
```

## 手順 3: Brawl Stars の証明書ピン留めバイパス

Supercell ゲームは内部 CA を持つので、 mitmproxy CA を信用させても弾かれる。**Frida script で
SSL_CTX_set_verify を no-op に書き換える**:

```javascript
// brawl-bypass.js
Java.perform(function() {
    var SSLContext = Java.use('javax.net.ssl.SSLContext');
    var X509TrustManager = Java.use('javax.net.ssl.X509TrustManager');
    var TrustManager = Java.registerClass({
        name: 'com.bypass.TrustManager',
        implements: [X509TrustManager],
        methods: {
            checkClientTrusted: function() {}, checkServerTrusted: function() {},
            getAcceptedIssuers: function() { return []; }
        }
    });
    SSLContext.init.overload('[Ljavax.net.ssl.KeyManager;', '[Ljavax.net.ssl.TrustManager;', 'java.security.SecureRandom').implementation = function(km, tm, sr) {
        this.init(km, [TrustManager.$new()], sr);
    };
});

// OkHttp3 ピン留めも潰す
var CertificatePinner = Java.use('okhttp3.CertificatePinner');
CertificatePinner.check.overload('java.lang.String', 'java.util.List').implementation = function(host, certs) { return; };
```

実行:
```bash
frida -U -f com.supercell.brawlstars -l brawl-bypass.js --no-pause
```

## 手順 4: Brawl Stars プロトコル (Magic Tea / Custom Tea) の解読

Supercell ゲームは独自バイナリプロトコル。 HTTP/JSON ではない。 既存研究:
- [royale-server](https://github.com/RoyaleAPI/royale-server) (CR の私設サーバ実装、 プロトコル参考)
- [supercell-proxy](https://github.com/) (用途別に検索) ※ BS 専用は少ない
- [csharp-brawlhalla-emulator] 系の private server コード

**パケットの基本構造**:
```
| 2 byte msgType | 3 byte length | 2 byte version | N byte payload (RC4 暗号) |
```

RC4 鍵の取得が最重要:
1. ハンドシェイク時に nonce 交換
2. APK 内 `libgame.so` を `radare2` or `ghidra` で解析、 鍵スケジューリング関数を特定
3. Frida でランタイム鍵ダンプ:
```javascript
Interceptor.attach(Module.findExportByName("libgame.so", "EncryptionKeyInit"), {
    onEnter: function(args) {
        console.log("Key:", hexdump(args[0], { length: 32 }));
    }
});
```

## 手順 5: マッチング関連メッセージの特定

Brawl Stars のマッチング系メッセージ (推定 msgType):
- `10100` (GoToMatchmakingMessage) ← キュー開始
- `20578` (MatchmakingStatusMessage) ← 待機中
- `20596` (MatchmakingCancelledMessage) ← キャンセル
- `20104` (BattleStartMessage) ← マッチ成立 + サーバ情報送信

(※ msgType は version で変動。 自分で確かめること)

mitmproxy script で抽出:
```python
# bs_extract.py (mitmproxy addon)
import struct, time, json
from datetime import datetime, timezone

OUT = open("queue_log.jsonl", "a", encoding="utf-8")

def request(flow):
    if "supercell" not in flow.request.host: return
    payload = flow.request.raw_content
    if len(payload) < 7: return
    msg_type = struct.unpack(">H", payload[0:2])[0]
    length = int.from_bytes(payload[2:5], "big")
    ts = time.time()
    if msg_type == 10100:
        OUT.write(json.dumps({"event": "queue_start", "ts": ts, "msg_type": msg_type}) + "\n"); OUT.flush()
    elif msg_type == 20104:
        OUT.write(json.dumps({"event": "battle_start", "ts": ts, "msg_type": msg_type}) + "\n"); OUT.flush()
    elif msg_type == 20596:
        OUT.write(json.dumps({"event": "queue_cancel", "ts": ts, "msg_type": msg_type}) + "\n"); OUT.flush()
```

起動:
```bash
mitmdump -s bs_extract.py --mode transparent -p 8080
```

## 手順 6: queue_seconds の正確な計算

```python
import json
events = [json.loads(l) for l in open("queue_log.jsonl")]
pairs = []
last_start = None
for e in events:
    if e["event"] == "queue_start":
        last_start = e["ts"]
    elif e["event"] == "battle_start" and last_start:
        pairs.append({
            "queue_start": last_start,
            "battle_start": e["ts"],
            "queue_seconds": e["ts"] - last_start,
        })
        last_start = None
    elif e["event"] == "queue_cancel":
        last_start = None  # キャンセルは集計から除外
print(f"N={len(pairs)}, median={sorted(p['queue_seconds'] for p in pairs)[len(pairs)//2]:.1f}s")
```

これで B案の ±15秒誤差 → **±0.5秒精度** になる。

## 手順 7: 本リポジトリへの組み込み (集計値のみ)

通信解析サーバ → POST /api/queue/measurement (将来) で
```json
{ "tag": "#YQ8YY09R", "queue_seconds": 137.4, "mode": "trioShowdown", "brawler": "JANET", "ts": 1715900000 }
```
を投稿し、 B案の queue_measurements テーブルに `notes='packet_capture'` 付きで保存。

UI 側は B案も C案も同じテーブルから引くので透過。

## リスク・対策

| リスク | 対策 |
|---|---|
| アカウントBAN | サブ垢専用。 メイン垢は触らない |
| Supercell 検出 (root チェック) | Magisk Hide / Shamiko で root 隠蔽。 ただし完全ではない |
| Frida 検出 | frida-server をリネーム + ポート変更 + magisk module の anti-frida-detect |
| プロトコル変更 (アップデート毎) | msgType ずれる。 アップデート後に再キャリブ必要 |
| 個人情報流出 | 解析対象は自分のアカウントのみ。 他人のセッションを傍受しない |

## 次のアクション (実施判断)

1. **サブ垢を1つ用意** (gmail新規 + Supercell ID)
2. **Pixel 4a 中古 + Magisk** (一番情報多い)
3. **Frida + mitmproxy 環境構築** (~1日)
4. **Brawl Stars インストール、 既存研究の RC4 鍵抽出スクリプト探し** (~1週間、 ここが鬼門)
5. **マッチング系 msgType 特定** (~3日, トライ&エラー)
6. **計測スクリプト実装** (1日)
7. **100戦データ取得 → B案との誤差検証**

合計工数: **2-3週間 + 中古端末代 ~1万円**

費用対効果が見合うかは要判断。 B案 (現実装) で十分なシグナルが取れるなら、 C案は保留が無難。

## 参考リンク

- mitmproxy: https://docs.mitmproxy.org/
- Frida: https://frida.re/docs/home/
- Supercell プロトコル研究 (CoC ベース、 一部 BS にも応用可):
  - https://github.com/clugh/csharp-brawlhalla (※ Brawlhalla 別ゲームなので注意)
- bsdebugger (Brawl Stars private server prototype、 古い):
  - 検索: "github brawlstars private server protocol"
- root 化ガイド (Pixel): https://forum.xda-developers.com/

---

最終更新: 2026-05-17
