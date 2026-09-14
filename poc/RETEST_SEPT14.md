# Retest September 14, 2026

Full automated retest of all 44 remotely testable findings (`retest_sept14.py`).

| Result | Count |
|---|---|
| **OPEN** | 42 |
| **FIXED** | 2 |
| **PARTIAL** | 1 |

## The only two fixes in 12 days

1. **EK-12** — `GET /api/user/list` without Bearer now returns 401 (was: 200).
2. **EK-23/56** — `device_face/` and `wake_up/` folders partially cleaned on the international CDN. Avatars and firmware OTA remain publicly downloadable. Chinese CDN status indeterminate (522).

## Everything still OPEN (highlights)

- LFI: `.env` still readable, **every secret unchanged** (ACCESS_TOKEN_SECRET, Redis, MySQL, Aliyun AK, RSA keys)
- Webshells from the third-party compromise: **still on the server**
- Pickle RCE on the AI inference server: **re-confirmed** (deserialization of benign pickle proven again)
- 5 third-party super_admin accounts: **still active**
- 35 SSRF probe rows in the routing table: **still present**
- Forged JWT works on **both** regions' admin APIs
- Redis CONFIG SET/MODULE LOAD: **still enabled** (full host takeover)
- File write on AI server via `detection_skills_file`: **still unauthenticated**
- ATO via legacy PHP `updateUser.php`: **still accepts forged 100-year JWTs**
- DashScope + Azure OpenAI keys: **both still generate text**
- Content moderation, CDN purge, Feishu messaging: **all still unauthenticated**

Data continues to grow: 8.19M conversations (+70k since Sept 1), 32,228 extracted profiles.
