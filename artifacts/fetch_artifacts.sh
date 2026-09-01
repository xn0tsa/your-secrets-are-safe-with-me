#!/usr/bin/env bash
# Fetches the large public artifacts from Energizelab's CDN/file servers
# Energizelab (tous servis sans authentification: cf EK-23).
# These binaries are NOT committed to the repo (size) but are
# downloadable by anyone to reproduce the analyses.
#
# Usage : ./fetch_artifacts.sh [all|firmware|apk|desktop|mcu]
set -u
OUT="$(dirname "$0")/fetched"
mkdir -p "$OUT"/{firmware,apk,desktop,mcu}
WHAT="${1:-all}"

fetch() { # url dest
  echo "→ $2"
  curl -s -m 3600 -o "$2" "$1" && ls -la "$2"
}

[ "$WHAT" = all ] || [ "$WHAT" = firmware ] && {
  echo "== Firmwares & outils (CDN public file/filecn) =="
  # AI Station: full 3.61 GB firmware image + Windows flasher (EK-33/34)
  fetch "http://file.energizelab.com.cn/tools/AI%20Station%20Firmware%20Tool.zip" \
        "$OUT/firmware/AI_Station_Firmware_Tool.zip"
  # Original ESP32 Eilik (encrypted: positive control) and unknown product lines
  fetch "http://filecn.energizelab.com.cn/4101000/update.bin" "$OUT/firmware/4101000_update.bin" || true
  fetch "http://filecn.energizelab.com.cn/5103003/stm32-ota.bin" "$OUT/firmware/5103003_stm32-ota.bin" || true
  fetch "http://filecn.energizelab.com.cn/3102999/app.bin" "$OUT/firmware/3102999_jieli_app.bin" || true
}

[ "$WHAT" = all ] || [ "$WHAT" = apk ] && {
  echo "== APK (OSS public) =="
  # Build DEBUG v3.0.3: points at the internal admin 192.168.0.241 (EK-43)
  fetch "http://file.energizelab.com.cn/apk/app-debug.apk" "$OUT/apk/app-debug-v3.0.3.apk"
  # Release builds (base APK + splits): audited version v3.0.0 (EK-38..43)
  fetch "http://file.energizelab.com.cn/app/app-release.apk" "$OUT/apk/app-release.apk" || true
  fetch "http://file.energizelab.com.cn/energizelab/app-release.apk" "$OUT/apk/app-release.apk" || true
  # Hermes strings (regenerable from any APK): unzip the base APK, then
  #   strings -n 8 assets/index.android.bundle > hermes_strings.txt
}

[ "$WHAT" = all ] || [ "$WHAT" = desktop ] && {
  echo "== Applications desktop Windows (EK-44) =="
  fetch "http://file.energizelab.com.cn/energizelab/EnergizeLabSetup-3.1.2-Win.exe" \
        "$OUT/desktop/EnergizeLabSetup-3.1.2-Win.exe" || \
  fetch "http://file.energizelab.com.cn/app/EnergizeLabSetup-3.1.2-Win.exe" \
        "$OUT/desktop/EnergizeLabSetup-3.1.2-Win.exe" || true
  fetch "http://file.energizelab.com.cn/app/ServoStudio%20Setup%202.0.11.exe" \
        "$OUT/desktop/ServoStudio-2.0.11.exe" || true
}

[ "$WHAT" = all ] || [ "$WHAT" = mcu ] && {
  echo "== Firmwares MCU (175.24.102.176, HTTP sans auth: EK-44) =="
  fetch "http://175.24.102.176/software/energizelab/mcu/em3/20301" "$OUT/mcu/em3_20301.bin" || true
  fetch "http://175.24.102.176/software/energizelab/mcu/eps5030/50301" "$OUT/mcu/eps5030_50301.bin" || true
}

echo "Done: artifacts in $OUT/"
