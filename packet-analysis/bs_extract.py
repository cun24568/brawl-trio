"""mitmproxy addon: Brawl Stars プロトコル (Magic Tea) パケットを識別 → queue_log.jsonl 保存.

起動:
  mitmdump -s bs_extract.py --mode transparent -p 8080

依存: mitmproxy 12.x。 仮想環境内で動かす:
  source /home/soya/brawl-trio/packet-analysis/venv/bin/activate

注:
  - Brawl Stars は HTTPS ではなく独自 TCP/UDP プロトコルを使う場合がある。
    その場合 mitmproxy --mode transparent では掴まらず、 raw TCP プロキシが必要。
    代替: --mode tcp / pwntools / Bettercap で TCP intercept。
  - msgType は version で変動。 起動時にゲーム version をログに残し、 後で校正できるようにする。
  - 暗号鍵 (RC4) は frida-extract で別途取得し、 ここでは平文 payload を前提とする。
"""
import json
import struct
import time
from pathlib import Path

from mitmproxy import http, tcp, ctx

OUT_PATH = Path(__file__).parent / "queue_log.jsonl"

# msgType 推定値 (Brawl Stars v60.x 系。 アップデート毎に校正必要)
MSGTYPE_NAMES = {
    10100: "queue_start",      # GoToMatchmakingMessage
    10101: "queue_cancel",     # MatchmakingCancelMessage
    20578: "queue_status",     # MatchmakingStatusMessage
    20596: "queue_cancelled",  # MatchmakingCancelledMessage
    20104: "battle_start",     # BattleStartMessage / SectorState
    24115: "client_hello",
    20100: "login_ok",
}


def _log(event: str, ts: float, msg_type: int, extra: dict | None = None):
    rec = {"event": event, "ts": ts, "msg_type": msg_type}
    if extra:
        rec.update(extra)
    with OUT_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    ctx.log.info(f"[bs] {event} msg_type={msg_type} ts={ts:.3f}")


def _parse_header(payload: bytes) -> tuple[int, int, int] | None:
    """Magic Tea ヘッダ: 2byte msgType + 3byte length + 2byte version"""
    if len(payload) < 7:
        return None
    msg_type = struct.unpack(">H", payload[0:2])[0]
    length = int.from_bytes(payload[2:5], "big")
    version = struct.unpack(">H", payload[5:7])[0]
    return msg_type, length, version


# --- HTTP/HTTPS イベント (ファイルアップロード/CDN等の補助通信) ---
def request(flow: http.HTTPFlow):
    if "supercell" not in flow.request.host and "brawl" not in flow.request.host:
        return
    ctx.log.info(f"[bs-http] {flow.request.method} {flow.request.url[:120]}")


# --- 生 TCP イベント (本命) ---
def tcp_message(flow: tcp.TCPFlow):
    msg = flow.messages[-1]
    payload = msg.content
    parsed = _parse_header(payload)
    if not parsed:
        return
    msg_type, length, version = parsed
    name = MSGTYPE_NAMES.get(msg_type, f"unknown({msg_type})")
    ts = time.time()
    extra = {
        "name": name,
        "length": length,
        "version": version,
        "direction": "c2s" if msg.from_client else "s2c",
        "host": flow.client_conn.peername[0] if flow.client_conn.peername else None,
    }
    if msg_type in MSGTYPE_NAMES:
        _log(MSGTYPE_NAMES[msg_type], ts, msg_type, extra)
    else:
        # 未知メッセージも一定ログ (後で msgType マッピングを校正するため)
        if msg_type < 30000:  # noise除去
            _log("unknown", ts, msg_type, extra)


def load(loader):
    ctx.log.info(f"[bs] queue extraction addon loaded, log → {OUT_PATH}")
