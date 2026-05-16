// Frida script: Brawl Stars (Android) の SSL 証明書ピン留めをバイパス。
// 起動: frida -U -f com.supercell.brawlstars -l frida-bypass.js --no-pause
//
// 前提: 端末root済 + /data/local/tmp/frida-server 起動済 + mitmproxy CA を端末にインストール済
// 注意: アップデートで TrustManager 実装が変わると効かなくなる。 その場合 hooked メソッドを再特定。

Java.perform(function () {
    console.log("[*] Frida SSL pinning bypass loaded");

    // === 1. 汎用 X509TrustManager 置換 ===
    try {
        var X509TrustManager = Java.use("javax.net.ssl.X509TrustManager");
        var SSLContext = Java.use("javax.net.ssl.SSLContext");
        var TrustManager = Java.registerClass({
            name: "com.bypass.TrustManager",
            implements: [X509TrustManager],
            methods: {
                checkClientTrusted: function (chain, authType) {},
                checkServerTrusted: function (chain, authType) {},
                getAcceptedIssuers: function () { return []; },
            },
        });
        SSLContext.init.overload(
            "[Ljavax.net.ssl.KeyManager;",
            "[Ljavax.net.ssl.TrustManager;",
            "java.security.SecureRandom"
        ).implementation = function (km, tm, sr) {
            console.log("[*] SSLContext.init() bypassed");
            this.init(km, [TrustManager.$new()], sr);
        };
    } catch (e) { console.log("[-] X509TrustManager bypass failed: " + e); }

    // === 2. OkHttp3 CertificatePinner.check 無効化 ===
    try {
        var CertificatePinner = Java.use("okhttp3.CertificatePinner");
        CertificatePinner.check.overload("java.lang.String", "java.util.List").implementation = function (host, list) {
            console.log("[*] OkHttp3 CertificatePinner.check(" + host + ") bypassed");
            return;
        };
    } catch (e) { console.log("[-] OkHttp3 bypass not needed or failed: " + e); }

    // === 3. ネイティブ側 SSL_CTX_set_verify を no-op に (boringssl) ===
    try {
        var SSL_CTX_set_verify = Module.findExportByName("libssl.so", "SSL_CTX_set_verify");
        if (SSL_CTX_set_verify) {
            Interceptor.replace(SSL_CTX_set_verify, new NativeCallback(function () {}, "void", ["pointer", "int", "pointer"]));
            console.log("[*] libssl.so SSL_CTX_set_verify replaced");
        }
    } catch (e) { console.log("[-] native ssl bypass failed: " + e); }

    // === 4. Supercell 独自 cert pin (libg.so 内に存在する場合) ===
    // libgame.so の SSL 検証関数アドレスは IDA/Ghidra で事前特定して以下で hook
    /*
    var libGame = Module.findBaseAddress("libgame.so");
    if (libGame) {
        var verifyAddr = libGame.add(0xXXXXXX);  // ← 事前解析で確定
        Interceptor.replace(verifyAddr, new NativeCallback(function () { return 1; }, "int", []));
        console.log("[*] libgame.so cert verify replaced");
    }
    */
});
