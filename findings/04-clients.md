# Findings: Client applications (EK-38, EK-39, EK-40, EK-41, EK-42, EK-43, EK-44)

The app stores your password in cleartext and survives logout doing it. Target: `com.energizeLab` v3.0.0 (versionCode 23, React Native 0.77.3, Hermes v96) + the debug build v3.0.3 published on public OSS ([EK-23](01-cloud-api.md#EK-23)). The Hermes bundle was fully decompiled (548,906 lines of recovered JS). Positive controls listed at the end.

> **Retest 2026-09-01**: ❌ all OPEN: revalidated via the committed artifacts
> (`artifacts/apk/`: `BuildConfig.java`: RSA key never rotated,
> `AndroidManifest.xml`: permissions unchanged; full XAPK via fetch script).
> The v3.0.3 debug APK is still publicly served ([EK-23](01-cloud-api.md#EK-23)).

---

<a id="EK-38"></a>
## EK-38 · HIGH · Password stored in cleartext on disk, survives logout

After login, the form password is written **unconditionally** into the persisted Redux store (`persist:root` → AsyncStorage, `user.userInfo.password`): the "remember me" checkbox is a decorative label. `clearUserData` on logout resets `id/username/avatar/nickname` but **not** `password`/`email`/`phone` (Object.assign merge); `wifiSsidPwd` is never purged; a 401 on refresh redirects to Login with no cleanup. Zero `EncryptedSharedPreferences`/Keystore usage.

```js
// L.528980 (login OK)
dispatch(setUserInfo({...res.data.user_info, password: formikValues.password, isLogin: true}))
```

**Fix**: never persist the password (the refresh token suffices); full purge on logout/401; Keystore.

---

<a id="EK-39"></a>
## EK-39 · HIGH · Unsalted MD5 + RSA PKCS#1 v1.5 with predictable RNG

- Login: `password → CryptoJS.MD5(pw) → RSA-2048 PKCS#1 v1.5 → POST /api/auth/login` (over HTTP: [EK-01](01-cloud-api.md#EK-01)). Unsalted MD5 = rainbow tables.
- **Worse**: `POST /api/user/setPassword` sends the MD5 **alone, without RSA**: a replayable password equivalent, sniffable.
- PKCS#1 v1.5 padding confirmed (`pkcs1pad2`); the jsbn RNG falls back to an RC4 pool seeded by `Math.random` (non-cryptographic) under Hermes → predictable padding bytes.

**Fix**: TLS + server-side bcrypt/argon2; ban MD5 and PKCS#1 v1.5.

---

<a id="EK-40"></a>
## EK-40 · HIGH · Hardcoded RSA public key + zero certificate pinning

The complete RSA-2048 key sits in `BuildConfig.java` + `strings.xml` (identical in v3.0.0/v3.0.3: never rotated). With HTTP and no pinning: MITM key substitution is possible; the corresponding **private** key leaked in the vault ([EK-09](01-cloud-api.md#EK-09)): any sniffed login payload is decryptable after the fact. Zero `CertificatePinner`, zero `network_security_config` in the app.

**Fix**: HTTPS + pinning makes the application-layer crypto redundant; otherwise distribute the key via TLS with rotation.

---

<a id="EK-41"></a>
## EK-41 · HIGH · Content injection chain: MITM → `.awe` → BLE

`GET /api/program/getProgramAweFileUrl` (HTTP) → the app pushes the URL to the robot over BLE (04/85) **with no domain validation** → the robot downloads and executes the `.awe` content (raw format, unsigned). An API MITM serves arbitrary content executed by the victim's Eilik through the official flow. WebView extras: geolocation granted **silently** (`onGeolocationPermissionsShowPrompt` auto-grant), DownloadManager forwards cookies to the public `Download/` folder with forged filenames.

**Fix**: domain whitelist before the BLE push + `.awe` signatures; real geolocation prompt; harden DownloadManager.

---

<a id="EK-42"></a>
## EK-42 · MEDIUM · Excessive permissions & cloud face biometrics

`ACCESS_BACKGROUND_LOCATION`, `CAMERA`, legacy external storage: for a toy. The "Upload a Portrait" flow (up to 6 family members) sends the raw JPEG portrait to `POST /api/upload/singleFileUpload` (`type=device_face`), then pushes the URL to the robot which downloads it: **directly contradicting the in-app privacy policy** ("We do not store or transmit your original photos"). `RNWifi.loadWifiList()` exposes SSID+BSSID (geolocatable) to the JS context.

**Fix**: reduce permissions; on-device face processing; align the policy with reality.

---

<a id="EK-43"></a>
## EK-43 · MEDIUM · Dev artifacts & reversibility

Metro IP `192.168.1.20:8088` + `http:127.0.0.1:8012/assets` in the release bundle (dead code in v3), the **debug** APK v3.0.3 published on the public OSS pointing at the internal admin `192.168.0.241:9090` (reveals the VPC topology), readable Hermes bundle, unannounced product names (MiniEiliko, ServoBrainMini, quadruped).

---

## Positive controls (phase 34)

- **No embedded secrets** in the APK (0 API keys, 0 keystores; the June "RSA PRIVATE KEY" pattern = jsencrypt PEM markers, false positive).
- **Healthy, up-to-date native stack**: RN 0.77.3, OkHttp 4.12, libwebp 1.3.2 (CVE-2023-4863 fixed): no applicable CVEs; 12/12 hardened libs (PIE/RELRO/NX).
- **WebView bridge never installed** (June's I-02 reclassified); WebView file-access off, HTTPS-only.
- No deep links, no JS hot-update (CodePush), no third-party analytics SDKs, no MQTT.
- Valid V2+V3 Play App Signing signature; `allowBackup=false`; not debuggable (release).
- The JWT HS256 secret is strong (rockyou + best64: 0 hits): but readable via LFI ([EK-09](01-cloud-api.md#EK-09) / [EK-10](01-cloud-api.md#EK-10)).
- Zero runtime protections (root/anti-debug/frida): aggravates EK-38.

---

Three desktop apps, one shared philosophy: `verify=False`, secrets in the binary, and robot protocols that answer to any software on your PC. Targets: **EnergizeLab desktop** (Python/PyInstaller, 1,095 modules), **ServoStudio** (Electron), **RobotStudio**: all published on the public OSS (`app/`, `energizelab/`: `EnergizeLabSetup-3.1.2-Win.exe` 683 MB, ServoStudio 2.0.10/11).

> **Retest 2026-09-01**: ❌ OPEN: the binaries remain publicly downloadable
> (`artifacts/fetch_artifacts.sh`); the USB protocol reverse and full-control
> PoCs (flash, format, servos, display, custom AI agent) were revalidated on
> our own robot (`artifacts/usb_desktop/`, `artifacts/firmware/webapp_custom/`).

---

<a id="EK-44"></a>
## EK-44 · CRITICAL · Hardcoded secrets, disabled TLS, unauthenticated protocols

### Extracted secrets (static)

| Secret | Value | Impact |
|---|---|---|
| PyInstaller key | `[redacted, extractable from the public installer]` | Decrypts the entire desktop app's code |
| Fernet secret | `[redacted, in the public installer]` (PBKDF2-SHA256, 100K iter.) | Decrypts `~/.config/energizeUser.json` (email, Bearer token): deterministic, offline |
| Frame "encryption" | magic `[redacted, in the public binaries]` | Not real cryptography |

### Blanket `verify=False` (13 call sites, 7 modules)

`login.php` (email + password in cleartext over HTTP), `requestCode.php` (OTP), `updateUser.php`/`deleteUser.php` (Bearer), **firmware downloads without verification**. `verify=False` also kills TLS validation on HTTPS URLs.

### Firmware chain without integrity

`FirmwareUpdate.get_web_file()` downloads from `file.energizelab.com.cn` (diffed by `file_size`/`file_time`, no hash/signature) then **writes directly to the robot's flash** (`FirmwareWriteFlash` 0x04/0x05). A MITM delivers a malicious firmware → full robot compromise (mic, servos, display).

### Unauthenticated robot protocols (USB-serial / TCP)

Frames `AAAAAA | len | inst | data | ~sum` at 1 Mbaud (4.5 Mbaud telemetry): flash (0x04/0x05), **SD format** (0x42), **arbitrary EEPROM** (0x31), **servos** (0xA2), **display** (0xA4), servo bootloader (0xFFFF/0xFDFD). EMS serial protocol `FFFF | ID | len | instr | params | cksum` (ping→factory reset→reboot). ESP32 network: UDP JSON broadcast → TCP, "encryption" by magic string. **Any software on the user's PC** can drive these instructions.

### Unhardened Electron (ServoStudio)

`nodeIntegration: true` + `contextIsolation: false` → any renderer XSS = Node.js RCE; the `load-bin` IPC accepts arbitrary paths (arbitrary file read). Source maps shipped in production (full TypeScript source).

### Public MCU firmware

`http://175.24.102.176/software/energizelab/mcu/{series}/{model}`: downloadable without auth, TLS, or signature (validated live: `/mcu/em3/20301`, `/mcu/eps5030/50301`).

### Telemetry without consent

~200-250 behavioral counters (games, emotions touched, shocks, charging) + 3× chip_id POSTed as bz2 over HTTP to the legacy PHP endpoints: correlated with the account.

**Fix**: remove secrets from binaries, `verify=True` + HTTPS, firmware signature verified before flashing, Electron hardening (`contextIsolation`), serial-protocol authentication, telemetry consent.
