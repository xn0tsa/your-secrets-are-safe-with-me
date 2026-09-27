# Findings: Firmware (EK-32 → EK-37, EK-91)

None of the firmware channels below verify a signature. Not the OTA, not the USB update, not the MCU flash. Everything accepts whatever it is given. Products identified: original Eilik (ESP32, mode 4101000: Flash Encryption active, not remotely bypassable), Eiliko (4101000), the new Linux robot **RK3562** (104000), the AI Station camera (104000/ES), Meteer, WealthyGod, MiniEiliko, the ServoBrain hexapod + a quadruped in development, JieLi 3102999, STM32 5103003, Panxer/Maticontroller (MCU). Rockchip RK3562 SoC, Buildroot 2021.11, kernel 5.10 BSP.

> **Retest 2026-09-01**: ❌ all OPEN.
> - **[EK-33](#EK-33)**: `FirmwareUpdater` re-downloaded from the CDN → `kEmbeddedAesKey` at offset 113720 **identical** (`artifacts/keys/extract_aes_key.py`).
> - **[EK-32](#EK-32) / [EK-34](#EK-34)**: `sh.zip` re-downloaded → `S99eilik` (unsigned unzip) and `S50dropbear` (`-R`, no auth) confirmed (`artifacts/firmware/104000/extracted/sh/`).
> - **[EK-37](#EK-37)**: `main.zip` (2.3 MB unstripped aarch64 ELF) served in cleartext.
> - **[EK-35](#EK-35) / [EK-36](#EK-36)**: revalidated on the auditor's own robot: custom firmware flashed via 0x04/0x05 (`artifacts/firmware/webapp_custom/`), PoCs in `poc/hijack/`.

---

<a id="EK-32"></a>
## EK-32 · CRITICAL · OTA supply chain: root RCE on 9 product lines

Chain proven end-to-end (no hardware):

```
free account (EK-18) → user JWT
  → LFI (EK-08) → .env → ACCESS_TOKEN_SECRET (EK-09)
  → forged super-admin JWT (EK-10)
  → /api/oss/signature-url?key=104000/main.zip → pre-signed PUT (EK-22)   [URL obtained; upload stopped short of production]
  → /api/oss/upload-zip → firmware/ overwrite on the public CDN            [proven + restored, P30]
  → CDN refresh → every robot downloads the ZIP
  → S99eilik: unzip -o -q main.zip → ./main   ← NO signature verification
  → root (EK-34)
```

- The `S99eilik` init script: direct `unzip -o -q`; the only check is `grep "release" version.json`.
- The OTA CDN is plain HTTP (WiFi-local MITM achieves the same result with zero cloud access).
- 9 mode_numbers with exact CDN URLs (including factory mode 101999, JieLi, STM32): the `upload-zip` attack covers all 9.

**Fix**: Ed25519 signatures verified on-device, HTTPS CDN, dev/prod bucket separation, OSS prefix restrictions.

---

<a id="EK-33"></a>
## EK-33 · CRITICAL · Universal hardcoded AES-256 key

`kEmbeddedAesKey` (file offset 113720 of the `FirmwareUpdater` binary, unstripped symbols):

```
79e610de213d8966a1e0dde84136ac6072996a828053032e34773951fd080a5e
```

- Decrypts any USB firmware for mode 104000 (AES-256-CBC, `DecryptFirmwareToCanonicalZip`).
- **Reused as the passphrase of the AI Station OTA image** (extracted from the Windows flasher after a manual UPX unpack: AES-256-CBC, PBKDF2-HMAC-SHA512, 500,000 iterations) → the complete 3.61 GB image is decryptable offline by anyone with the public zip.
- The dm-crypt rootfs key for the AI Station travels inside the same image (misc.img).

**Fix**: per-device keys (factory ECDH), signature independent of encryption, stripped release binaries.

---

<a id="EK-34"></a>
## EK-34 · CRITICAL · Trivial root on the devices

| Vector | Detail |
|---|---|
| `root::::::::` | empty hash field in mode 104000's `/etc/shadow` (Dropbear `-B` via supply chain = passwordless SSH root: Docker PoC) |
| Password `rockchip` | AI Station (`$5$…` validated with openssl passwd): default never changed |
| UART | `inittab`: `::respawn:-/bin/sh` → unauthenticated root shell on the serial port |
| Magic USB key | VID `0x3535` PID `0x5678` → S50dropbear starts SSH root |
| Dropbear at boot | undocumented, exposed on the home WiFi |

**Fix**: strong root hash, authenticated getty on UART, disable Dropbear/USB in production, sign the init scripts.

---

<a id="EK-35"></a>
## EK-35 · CRITICAL · Unauthenticated update services (local network / USB)

- **FirmwareUpdater TCP** (mode 104000): binary protocol `[instr:1][len:4LE][payload]`: `FW_START/FW_CHUNK/FW_END/DEPLOY/REBOOT` accepted from any WiFi client → firmware push + reboot = root RCE (protocol reconstruction documented).
- **USB serial / CDC-ACM** (0777): frames `AAAAAA | len | id | instr | data | ~sum`: firmware write (0x04/0x05), **format** (0x42), EEPROM (0x31), servos (0xA2), display (0xA4), servo bootloader (0xFFFF/0xFDFD at 1 Mbaud). Complete EMS protocol (0x01–0x83).
- 4 MCU flash vectors: USB serial, magic key, OTA MITM, STM32 port.

**Fix**: bind to 127.0.0.1 or mutual HMAC authentication; signed firmware verified before deployment.

---

<a id="EK-36"></a>
## EK-36 · HIGH · Unauthenticated BLE

The GATT protocol was fully reconstructed from the decompiled Hermes bundle: service `00008888-…`, characteristic `0000999-…`, frame `aaaaaa|LEN|INSTR|ENCRYPTION(5B, hardcoded to 0)|…|CHECK=~sum`: 33 commands including **04/01: push SSID+WiFi PSK in cleartext hex**, 03/81+04/81: list/write enrolled faces, joystick, actions, program deletion. No bonding, PIN, or challenge: "the UI pairing is cosmetic". The AI Station's HTTP captive portal: `GET /api/get_wifi_info` returns the PSK in cleartext to any LAN client.

**Attacks**: provisioning sniff → WiFi PSK; re-provisioning to an attacker AP → cloud channel + OTA source hijack; face-list exfiltration (family biometrics).

**Fix**: challenge-response from a factory secret, application-layer encryption (the 5-byte field exists and is empty), refuse unpaired GATT.

---

<a id="EK-37"></a>
## EK-37 · MEDIUM · Cleartext firmware + no anti-rollback

- Mode 104000: `main.zip` unstripped aarch64 ELF (debug_info), `lib.zip` 102 MB cleartext, sole embedded URL `http://ai…:8000/get_weather`.
- JieLi 3102999: debug logs printing `SSID: %s Password: %s`, internal GitLab paths.
- STM32 5103003: 125 KB cleartext binary, re-flashable at 1 Mbaud.
- Immediate downgrade to any old version possible (no minimum version).
- `.awe` content (104 raw bytes) has no magic or signature: executable by the robot (see [EK-41](04-clients.md#EK-41)).
- Positive: ESP32 products (original Eilik + new lines) have Flash Encryption active, firmware encrypted at rest.

**Fix**: anti-rollback, remove credential logs, encrypt + sign every distributed artifact.

---

<a id="EK-91"></a>
## EK-91 · HIGH · Factory flasher: signature checks disabled, secure-boot efuse never burned

The Windows flasher for the AI Station (a rebranded Rockchip FactoryTool) was reverse-engineered offline. It talks to the device over 4 physical vectors — USB mass-storage, ADB (push + `factory_unzip`, `fw_setenv`), UVC (a camera control reboots the unit into Loader), and rockusb maskrom/loader (VID 0x2207) — and the `fwupd` serial protocol itself has **no authentication** (`PING → SWITCH_USB_MODE → REBOOT_LOADER → DEPLOY`): the device puts itself into Loader mode on command, no maskrom pin needed. The protections exist in code but are all switched off in the shipped tool: signature verification `FW_NOT_CHECK=true`, secure-boot **efuse never burned at the factory**, anti-rollback off, flash locking off. Physical access therefore equals **arbitrary flash, full dump, brick, or falsified `serial_id` provisioning** on any unit, compounded by the universal image key ([EK-33](#EK-33)).

**Retest 2026-09-01**: ❌ OPEN (flasher tool and 3.43 GB firmware zip remain publicly downloadable — [EK-23](01-cloud-api.md#EK-23)).
**Fix**: burn the secure-boot efuse and enforce signature + anti-rollback in the factory tool before the next production run.
