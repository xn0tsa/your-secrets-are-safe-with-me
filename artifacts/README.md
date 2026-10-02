# Audit artifacts

Hardware/static artifacts for the device findings, retested on **2026-09-01**
(see `../poc/RETEST.md`). The repository stays lean and readable: only small, meaningful proof files are
committed. Everything else: the release XAPK, OTA zips, the 3.61 GB AI Station
image, the 132 MB debug APK, Windows installers, the admin SPA: is fetched
on demand by `fetch_artifacts.sh` from Energizelab's public CDNs (all served
without authentication, [EK-23](../findings/01-cloud-api.md#EK-23)). The admin SPA is also directly copyable from
`https://energizelab.com.cn` (see [EK-45](../findings/06-privacy.md#EK-45)).
Historical working documents kept as-is are noted below.

| Directory | Contents | Findings |
|---|---|---|
| `apk/` | `BuildConfig.java` (RSA key + hardcoded URLs) + `AndroidManifest.xml`: the smoking-gun files; full APK via fetch script | [EK-38](../findings/04-clients.md#EK-38)–[EK-43](../findings/04-clients.md#EK-43) |
| `firmware/104000/` | `version.json` + the extracted init scripts (`S99eilik`, `S50dropbear`, …): the unsigned-OTA evidence; OTA zips via fetch script | [EK-32](../findings/03-firmware.md#EK-32) / [EK-34](../findings/03-firmware.md#EK-34) / [EK-37](../findings/03-firmware.md#EK-37) |
| `firmware/webapp_custom/` | `eilik_flash_full.py`: the flasher that pushed custom firmware onto my own robot over USB ([EK-35](../findings/03-firmware.md#EK-35)) | [EK-35](../findings/03-firmware.md#EK-35) |
| `keys/` | `extract_aes_key.py`: parses the ELF symtab and extracts `kEmbeddedAesKey` (**MATCH verified 2026-09-01** on a fresh CDN binary) | [EK-33](../findings/03-firmware.md#EK-33) |
| `usb_desktop/` | `eilik_usb_poc.py` (full serial protocol: flash 0x04/05, format 0x42, servos 0xA2, display 0xA4), `eilik_agent.py` (custom conversational agent on the unauthenticated AI endpoints + USB body), USB reverse report | [EK-35](../findings/03-firmware.md#EK-35) / [EK-44](../findings/04-clients.md#EK-44), also demonstrates [EK-02](../findings/01-cloud-api.md#EK-02) |
| `privacy/` | `privacy_queries.sql`: read-only retest queries (profiling, orphans, admin hash) with 2026-09-01 results | [EK-45](../findings/06-privacy.md#EK-45) / [EK-46](../findings/06-privacy.md#EK-46) / [EK-47](../findings/06-privacy.md#EK-47) / [EK-49](../findings/02-infra.md#EK-49) |
| `fetch_artifacts.sh` | Downloads the large public binaries (AI Station, debug APK, Windows apps, MCU firmware) | [EK-33](../findings/03-firmware.md#EK-33) / [EK-34](../findings/03-firmware.md#EK-34) / [EK-43](../findings/04-clients.md#EK-43) / [EK-44](../findings/04-clients.md#EK-44) |

## Artifact retest results (2026-09-01)

| Check | Result |
|---|---|
| AES key `kEmbeddedAesKey` (offset 113720, freshly downloaded CDN binary: `firmware/104000/` zips via fetch script) | ✅ **MATCH**: `79e610de…fd080a5e` ([EK-33](../findings/03-firmware.md#EK-33)) |
| `S99eilik`: OTA unzip with no signature verification | ✅ confirmed in `extracted/sh/` ([EK-32](../findings/03-firmware.md#EK-32)) |
| `S50dropbear`: SSH at boot, `DROPBEAR_ARGS=-R` | ✅ confirmed ([EK-34](../findings/03-firmware.md#EK-34)) |
| Cleartext firmware distribution (main.zip = 2.3 MB unstripped ELF) | ✅ confirmed ([EK-37](../findings/03-firmware.md#EK-37)) |
| Profiling pipeline: 24 fields, 31,450 profiles, 47,391 runs | ✅ active and growing ([EK-45](../findings/06-privacy.md#EK-45)) |
| Orphan AI Stations: 3,110/3,110 (0% linked) | ✅ worse ([EK-46](../findings/06-privacy.md#EK-46)) |
| Super-admin id=1 hash = `md5(md5("123456")+salt)` | ✅ confirmed offline ([EK-49](../findings/02-infra.md#EK-49)) |

The [EK-15](../findings/01-cloud-api.md#EK-15) / [EK-17](../findings/01-cloud-api.md#EK-17) findings (robot theft, account deletion) were replayed on the
auditor's own devices/accounts: PoCs in `../poc/hijack/`.

*Note: the firmware flasher source in `firmware/webapp_custom/` is kept as a
historical working artifact.*

The `backoffice_spa/` copy (92 chunks navigated with a forged JWT) was removed
for readability: grab it from `https://energizelab.com.cn` and see P42/[EK-45](../findings/06-privacy.md#EK-45)
for the token-injection walkthrough.
