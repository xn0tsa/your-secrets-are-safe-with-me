# Coordinated Disclosure Timeline

This file documents the disclosure process for the vulnerabilities described in this repository. It is maintained in good faith as part of the coordinated-disclosure process and is updated as events occur.

## Timeline

| Date (2026) | Event |
|---|---|
| June, August | Research phases 1 - 59: static analysis, live API validation (auditor-owned devices first), firmware reverse engineering. Production-impacting checks were limited and restored; individual test scope is recorded in the findings. |
| June 2026 | **First vendor notification attempts** (see Channels below). No response. (see Channels below). No response. |
| **2026-09-01** | Master report finalized (376 raw findings, 93 EKs). **Retest #1**, non-destructive re-verification of all findings. Vendor notified of report availability. No response. |
| **2026-09-09** | **Retest #2**, 8+ days after first notification: LFI still open, **zero secrets rotated**, reported attack paths remain available. No vendor response. |
| 2026-09-15 | 72-hour final deadline communicated to vendor (see below). CFP submitted to POC 2026 conference. |
| **2026-09-14** | **Retest #3**, 12 days after first notification: **42 of 44 remotely testable findings still OPEN**. Only one fix deployed (`/api/user/list` → 401, EK-13) plus one partial cleanup (biometric CDN folders). Zero secrets rotated. Webshells still on the server. Third-party super-admin accounts still active. |
| 2026-09-15 → 18 | 72-hour deadline expired with no vendor response. Third-party actor still active throughout. |
| **2026-09-22** | Phases 84 - 85: AI model hijacking (EK-85) and total persona injection (EK-86) demonstrated end-to-end on the auditor's own physical robots, within time-boxed windows, fully restored. No third-party device touched. |
| 2026-09-27 | CVE distillation finalized (`cve-distilled.md`), hostile CNA review applied, repo history purged of live credentials. |

## Notification channels used (no response on any)

1. **Email**, vendor public/contact addresses, with report summary and proof-of-concept references.
2. **SMTP relay via the vendor's transactional sender** (the OTP sender account), a disclosure message was delivered to vendor inboxes from a vendor-owned address.
3. **Feishu (Lark)**, a disclosure notice with contact details was submitted through the vendor's bot using the exposed test endpoint (EK-71).
4. **In-app feedback ticket**, created through the official feedback API with the researcher's real email address.
5. **Third-party pressure**, a technology journalist (The Verge) contacted the vendor for comment on the findings; no response was received through that channel either.

## Disclosure deadline

| **2026-10-13** | **Retest #5** — 4+ months after first contact: **32 of 40** remotely testable findings still OPEN. 8 fixed total (6 new since Sept 29). Zero root-cause fixes: JWT secret unchanged, Redis/MySQL public, webshells present, r2 accounts active. |

A 72-hour final deadline was communicated on **September 15, 2026** and expired on **September 18, 2026** with no vendor response at any point. As of this document's last update, **no root-cause corrective action has been taken** (32 of 40 findings still open as of October 13), and no secret has been rotated since discovery.

## Publication policy

This repository is currently **private**. It will be published in a redacted form (no live credentials, third-party PII minimized, dangerous tooling gated) once either:

- the vendor deploys fixes for the Tier-1 vulnerabilities in `cve-distilled.md`, or
- the coordinated-disclosure window lapses per CVE/CNVD submission rules.

Criminal third-party activity documented in this repository (webshells, C2 infrastructure, unauthorized super-admin accounts, see findings EK-29/50/60) is maintained **separately from the CVE submission package** for CERT coordination.

## Contact

Researchers: see `README.md`. Disclosure correspondence available to CNAs/CERTs on request.
