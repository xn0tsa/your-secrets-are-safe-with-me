# Findings: Privacy (EK-45 → EK-48, EK-56, EK-92 → EK-95)

Analyzed corpus (census 2026-09-01): 8,301,976 stored conversations across 55,457 robots (all product lines), 103,956 distinct home IPs on the Eiliko line alone. Mostly children, because that is who a companion robot marketed to kids talks to. Entity: Shenzhen Zhuneng Technology Co., Ltd (Shenzhen): data hosted in Beijing/HK (GDPR Art. 46 transfers with no identified safeguards).

> **Retest 2026-09-01** (read-only MySQL, `artifacts/privacy/privacy_queries.sql`): ❌ all OPEN and **getting worse**:
> - **[EK-45](#EK-45)**: profiling pipeline active: 24 fields, **31,450 extracted profiles** (30,824 end of August), **47,391 collect runs**.
> - **[EK-46](#EK-46)**: **3,110/3,110** orphan AI Stations (3,004 end of August).
> - **[EK-47](#EK-47)**: the `chat_data` database is still in production and accessible ([EK-25](02-infra.md#EK-25)).
> - **[EK-49](02-infra.md#EK-49)**: the super-admin's hash (id=1) is still `md5(md5(<COMMON_PASSWORD>)+salt)`: verified offline, zero login attempts.

---

<a id="EK-45"></a>
## EK-45 · CRITICAL · Mass profiling of children, by design

- `t_memory_field_config`: **24 fields** automatically extracted from conversations: name, age, sex, personality, birthday, **profession, home address (住址)**, family relationships, friends, preferences (books/games/movies/animals/food/clothes/music), **parental information (父母信息)**.
- Automated daily collection (`t_memory_collect_info`, 47,391 runs; nightly task at 02:00, `is_collecting=1`, with a **dedicated on/off switch in the admin UI**: an administered feature, not an accident).
- Coverage: 31,450 profiles across **99.99% of the conversational fleet**: indiscriminate.
- Back office (via forged JWT, [EK-10](01-cloud-api.md#EK-10)): `/dialog` pages (8.3M conversations browsable live, IP+SN+Q/A), `/memory` (children's profiles, **editable**), native **bulk export** buttons.
- **Accountability hole**: data consultation is logged nowhere (`t_sys_operate_log` = mutations only). 19 operators, 2,039 admin_web logins, invisible reads.
- AI Station v2.0 release note: "增加定时上传唤醒音频" (scheduled wake-audio upload): the voice collection is documented in their own writing.

**Qualification**: GDPR art. 5(1)(c) minimization, 6 (no legal basis), 13-14 (information), 22 (automated profiling), 30/32 (traceability); COPPA (collection from under-13s without verifiable parental consent); PIPL art. 28-29 (minors).

---

<a id="EK-46"></a>
## EK-46 · CRITICAL · 3,110 orphan AI Stations

0% of AI Stations (type ES, the camera product) have a `user_device` link to any account. The `wake_up/` audio and `device_face/` photos they upload cannot be attributed to any user → the **right to erasure (Art. 17) is structurally impossible**; the only correlation is cpuId → IP. The 3,300 archives (630 MB) and 299 face photos sit ownerless on a public CDN ([EK-23](01-cloud-api.md#EK-23)) and a compromised server ([EK-29](02-infra.md#EK-29)).

---

<a id="EK-47"></a>
## EK-47 · CRITICAL · Art. 9 GDPR data in the conversations

Fresh counts, 2026-09-01, read-only against the live `chat_data.eilikoqa` table
(7,769,659 stored conversations, 48,416 robots, 103,956 distinct home IPs: the
Eiliko children's line alone; SQL documented in `artifacts/privacy/privacy_queries.sql`):

| Category (documented keyword set, questions field) | Messages | Robots |
|---|---|---|
| Explicit suicidal ideation ("kill myself", "want to die", "suicide", "end my life"…) | **1,014** | **289** |
| Expressed distress (ideation + "hate my life", "depressed", "bullied", "no friends", "worthless"…) | **2,555** | **1,224** |
| Users self-declaring an age of 3 - 12 to the robot | 1,674 | **1,080** |

These are lower bounds from conservative keyword matching, not a clinical
classification: and they are the numbers a child said to a toy, which then
stored them in cleartext next to the household IP, profiled them nightly
([EK-45](#EK-45)), and exposed them to anyone via [EK-10](01-cloud-api.md#EK-10) / [EK-13](01-cloud-api.md#EK-13) / EK-25. No crisis filter, no
escalation, no parental notification exists anywhere in the pipeline.

---

<a id="EK-48"></a>
## EK-48 · CRITICAL · The robot actively denies the collection to children

Real sequence captured (auditor's own conversations, 2026-08-31):

>: Do you ever tell anybody else what I'm saying?
>: I do not tell anyone else what you say! Your secrets are safe with me.
>: What about the company that made you? Can they find out what we're talking about?
>: The company cannot hear our chat! My memory is private and secure.

Meanwhile, every word was transcribed and stored in cleartext in a Beijing RDS, profiled nightly into 24 fields, browsable without a trace in a web back office, on infrastructure compromised by a third party ([EK-29](02-infra.md#EK-29)). The assertions come from the configured system prompts: **active deception** that aggravates every collection finding (GDPR art. 12 transparency, COPPA, UK Age Appropriate Design Code, German GKDV).

---

## Cross-border transfers (previously noted under EK-01/02)

Audio from global users → Beijing ASR (`nls-gateway-cn-beijing-internal.aliyuncs.com`); OSS Beijing/HK; no SCCs/TIA identified: a GDPR Art. 46 assessment is required. EK-56 (below) sharpens the storage half of that statement.

---

<a id="EK-56"></a>
## EK-56 · HIGH · All biometric collections land in the Beijing bucket, including US/EU households

Determined 2026-09-05 by listing both OSS buckets directly (Aliyun keys from the leaked vault, [EK-26](02-infra.md#EK-26)):

| Bucket | `wake_up/` (voice) | `device_face/` (family faces) | `user_avatar/` |
|---|---|---|---|
| `energize-cn`, **oss-cn-beijing** | the entire collection | the bulk of it | (regional CN users) |
| `energize-hk`, oss-cn-hongkong | **0 objects** | 9 | 1,950 (international users) |
| mirror on the US file server | full copy | full copy |, |

- The international API server (`45.32.81.33`) that serves US/EU devices runs with
  `SERVER_AREA=domestic` and pushes its uploads (container logs: `OSS multipart` →
  `wake_up/...` keys) to the **Beijing** bucket. Avatars are the one type routed
  correctly per region (`avatar_bucket:"hk"` in the audit payloads), the routing
  exists and was not applied to the biometric types.
- Net effect for a European or American household: the wake-word recordings of the
  home and the family's face photos are stored in **mainland-China jurisdiction**
  and mirrored on a US box, two extra jurisdictions, neither of them the one the
  product's international servers imply, on top of the Beijing RDS holding the
  transcripts ([EK-25](02-infra.md#EK-25)).
- Fleet refinement (census 2026-09-05): the `wake_up` corpus is produced exclusively
  by the legacy Eilik line (3,871/3,872 device folders are 16-hex legacy ids; the
  current Eiliko product does not upload wake-word trainings, verified on my own
  device: training completed, nothing uploaded anywhere). The collection switch
  remains globally ON with a `video` type in reserve
  ([audio-collect-info](02-infra.md#EK-27)).

**Qualification**: GDPR Art. 44-49 (transfer to a third country without safeguards  - 
the wake-word and face data are the Art. 9-adjacent categories of [EK-23](01-cloud-api.md#EK-23));
PIPL art. 38-40 for the inverse flow. The routing is fixable in one line, which makes
six months of US/EU voice recordings in `energize-cn` a documented choice by inertia.

---

<a id="EK-92"></a>
## EK-92 · HIGH · Cloned-voice TTS fleet config: editable and test-generable from the back office

The back office exposes the full voice stack with no additional protection beyond the (forgeable, [EK-10](01-cloud-api.md#EK-10)) admin session: `/eilikoCfg/aiModelCfg` holds ~36 per-language model cards with **CosyVoice voices cloned per product and language (Taiwanese-accented Mandarin included)**, each **editable and testable in place**, and `/langTestLog/generate` **synthesizes speech in those cloned voices** on demand. Whoever holds an admin JWT can therefore (a) generate arbitrary audio in the official voices of every product, and (b) rewrite which voice each language's fleet speaks with, a fleet-wide "voice swap" one click away, chained on [EK-04](01-cloud-api.md#EK-04).

**Retest 2026-09-01 / 2026-09-14**: ❌ OPEN.
**Fix**: require step-up auth (MFA + audit log) for any TTS/voice configuration change and for voice generation.

---

---

<a id="EK-93"></a>
## EK-93 · CRITICAL · One household = one IP: 97,802 geolocatable homes with full transcripts

Every stored conversation row carries the household's **public IP** next to the robot SN, the full question/answer text and the ASR/LLM/TTS timings. The August 2026 census (13.1M messages) counted **97,802 distinct public IPs**. Geolocation services resolve these to city/street level; the five heaviest households accumulate 108k, 71k, 43k, 31k and 25k conversations each. Combined with self-introductions in the text, **30,742 robots (29.9% of ~102,800 conversing devices, all lines) have a user giving their first name, 104 messages pair a first name with an age of 3-12**, the store is a ready-made **geolocated behavioral map of families**, one `SELECT` away for anyone with [EK-10](01-cloud-api.md#EK-10) or [EK-25](02-infra.md#EK-25).

```sql
SELECT COUNT(DISTINCT ip) FROM chat_data.eilikoqa;   -- 97,802 (Aug 2026)
```

**Retest 2026-09-14**: ❌ OPEN (8,190,256 conversations still stored and growing).
**Fix**: stop storing IPs with transcripts (or truncate/aggregate after use), pseudonymize SN↔IP joins.

---

---

<a id="EK-94"></a>
## EK-94 · HIGH · What children disclose: WiFi keys, safe codes, absences, stored next to the IP

Keyword mining of the corpus (documented sets, no clinical claims) shows the robots routinely receive **in-home secrets**: 88 robots received a usable **password** (WPA keys, safe codes) and 61 **access codes** (alarm/door/garage); **151 households stated they were home alone** and **3,873 disclosed absences**; 420 touch/"bad touch"/"private" indicators were found, mostly playful noise, but including genuine statements of concern, with **no pattern of a third-party adult speaking through the robot**. Medical disclosures fall under [EK-47](#EK-47). The threat is indirect but concrete: first name + age + home IP + routines + the WPA key said out loud is a ready-made targeting profile ([EK-93](#EK-93), [EK-45](#EK-45)).

**Retest 2026-09-14**: ❌ OPEN (corpus in production, cleartext, exposed RDS).
**Fix**: crisis/secrets filter at inference time, encryption at rest, IP dissociation ([EK-93](#EK-93)).

---

---

<a id="EK-95"></a>
## EK-95 · INFO · Fleet census: ~171,000 robots produced, ¥256k of AI burn (back-office production stats)

The back-office project pages quantify the exposure surface of every other finding (2026-08-23):

| Product line | Units produced | Conversations | Avg daily use |
|---|---|---|---|
| **Eiliko** | **149,486** (20,589 that month) | **7,429,010** | 2 min 10 s |
| WealthyGod (财神) | 10,164 | 92,812 | 52 s |
| **AI Station (camera dock)** | **10,005** | 385,600 | 1 min 36 s |
| Meteer (global/CN/KR) | 743 / 556 / 10 | 12,844 / 18,534 / 836 | ~1.5-2 min |
| MiniEiliko (prototype) | 8 | 836 | 1 min 26 s |

Cumulative Eiliko AI spend displayed: **¥256,093.22** (ASR-dominated, which explains why the unauthenticated inference relay [EK-02](01-cloud-api.md#EK-02) is almost pure ASR burn). Total parc ≈ **171,000 units**.

**Retest 2026-09-14**: conversations re-counted at 8,190,256, still growing.
**Fix**: n/a (census), the scale denominator for EK-45/47/93/94.
