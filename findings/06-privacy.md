# Findings: Privacy & compliance (EK-45 → EK-48, EK-56)

Analyzed corpus (census 2026-09-01): 8,301,976 stored conversations across 55,457 robots (all product lines), 103,956 distinct home IPs on the Eiliko line alone. Mostly children, because that is who a companion robot marketed to kids talks to. Entity: Shenzhen Zhuneng Technology Co., Ltd (Shenzhen): data hosted in Beijing/HK (GDPR Art. 46 transfers with no identified safeguards).

> **Retest 2026-09-01** (read-only MySQL, `artifacts/privacy/privacy_queries.sql`): ❌ all OPEN and **getting worse**:
> - **[EK-45](#EK-45)**: profiling pipeline active: 24 fields, **31,450 extracted profiles** (30,824 end of August), **47,391 collect runs**.
> - **[EK-46](#EK-46)**: **3,110/3,110** orphan AI Stations (3,004 end of August).
> - **[EK-47](#EK-47)**: the `chat_data` database is still in production and accessible ([EK-25](02-infra.md#EK-25)).
> - **[EK-49](02-infra.md#EK-49)**: the super-admin's hash (id=1) is still `md5(md5("123456")+salt)`: verified offline, zero login attempts.

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
| Users self-declaring an age of 3–12 to the robot | 1,674 | **1,080** |

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
| `energize-cn` — **oss-cn-beijing** | the entire collection | the bulk of it | (regional CN users) |
| `energize-hk` — oss-cn-hongkong | **0 objects** | 9 | 1,950 (international users) |
| mirror on the US file server | full copy | full copy | — |

- The international API server (`45.32.81.33`) that serves US/EU devices runs with
  `SERVER_AREA=domestic` and pushes its uploads (container logs: `OSS multipart` →
  `wake_up/...` keys) to the **Beijing** bucket. Avatars are the one type routed
  correctly per region (`avatar_bucket:"hk"` in the audit payloads) — the routing
  exists and was not applied to the biometric types.
- Net effect for a European or American household: the wake-word recordings of the
  home and the family's face photos are stored in **mainland-China jurisdiction**
  and mirrored on a US box — two extra jurisdictions, neither of them the one the
  product's international servers imply — on top of the Beijing RDS holding the
  transcripts ([EK-25](02-infra.md#EK-25)).
- Fleet refinement (census 2026-09-05): the `wake_up` corpus is produced exclusively
  by the legacy Eilik line (3,871/3,872 device folders are 16-hex legacy ids; the
  current Eiliko product does not upload wake-word trainings — verified on my own
  device: training completed, nothing uploaded anywhere). The collection switch
  remains globally ON with a `video` type in reserve
  ([audio-collect-info](02-infra.md#EK-27)).

**Qualification**: GDPR Art. 44-49 (transfer to a third country without safeguards —
the wake-word and face data are the Art. 9-adjacent categories of [EK-23](01-cloud-api.md#EK-23));
PIPL art. 38-40 for the inverse flow. The routing is fixable in one line, which makes
six months of US/EU voice recordings in `energize-cn` a documented choice by inertia.
