// Frida script: Brawl Stars libgame.so から RC4 (もしくは AES) 暗号鍵をランタイムダンプ。
// 起動: frida -U -f com.supercell.brawlstars -l extract_rc4_key.js --no-pause
//
// 前提:
//   - Brawl Stars APK を radare2 / Ghidra で先に解析、 鍵スケジューリング関数のアドレス特定
//   - 一般に Supercell ゲームの暗号は libg.so/libgame.so 内 nonce+RC4 もしくは ChaCha20
//   - 関数シンボル名は stripped されてる場合多い → アドレスベース hook

function dumpKey() {
    var libGame = Module.findBaseAddress("libg.so") || Module.findBaseAddress("libgame.so");
    if (!libGame) {
        console.log("[-] libg.so not loaded yet, retry in 2s");
        setTimeout(dumpKey, 2000);
        return;
    }
    console.log("[+] libg.so base = " + libGame);

    // パターン1: RC4_set_key シンボル
    var rc4 = Module.findExportByName(null, "RC4_set_key");
    if (rc4) {
        Interceptor.attach(rc4, {
            onEnter: function (args) {
                var keyLen = args[1].toInt32();
                console.log("[KEY] RC4_set_key len=" + keyLen + " key=" + hexdump(args[2], { length: keyLen }));
            },
        });
        console.log("[+] hooked RC4_set_key");
    }

    // パターン2: ChaCha20_init / EVP_CIPHER_CTX_set_key
    var evp = Module.findExportByName(null, "EVP_EncryptInit_ex");
    if (evp) {
        Interceptor.attach(evp, {
            onEnter: function (args) {
                if (args[3] && !args[3].isNull()) {
                    console.log("[KEY] EVP key=" + hexdump(args[3], { length: 32 }));
                }
                if (args[4] && !args[4].isNull()) {
                    console.log("[IV ] EVP iv =" + hexdump(args[4], { length: 16 }));
                }
            },
        });
        console.log("[+] hooked EVP_EncryptInit_ex");
    }

    // パターン3: Supercell 独自関数 (アドレス手動指定)
    // var offset = 0x12345;  // ← Ghidra で確認
    // var customKeyInit = libGame.add(offset);
    // Interceptor.attach(customKeyInit, {
    //     onEnter: function (args) {
    //         console.log("[KEY] custom keyInit args[0]=" + hexdump(args[0], { length: 32 }));
    //     }
    // });
}

dumpKey();
