# Findings: Infrastructure (EK-25 → EK-29, EK-49, EK-50, EK-60 → EK-69, EK-84, EK-88 → EK-90)

One rented box runs the whole company: the admin API, the firmware CDN origin, the legacy PHP, the databases, the panels. It was co-hosted with two Pakistani institutions: `nicon.edu.pk` (vocational training institute, Rawalpindi) and `qmmb.gov.pk` (Quaid-i-Azam Mazar Management Board, the federal body maintaining the mausoleum of Pakistan's founder). Proof of hosting: Let's Encrypt certs for both domains issued on the box on 2026-03-22 (ACME validation requires the DNS to point there). Same user, same php-fpm, no isolation. Both domains moved off the box later in 2026; their vhosts, expired certs, and the webshells remain. Main server: `45.32.81.33` (Vultr, CentOS 7 EOL, kernel 3.10): a multi-tenant **BaoTa** box hosting the admin API (`station-middleware:1.8.2`, Docker, root), the CDN file origin, the legacy PHP API (:789), the BaoTa panel (:8888), phpMyAdmin (:888), FTP (:21), local MySQL (:3306): and two third-party Pakistani sites: `nicon.edu.pk` (a vocational training institute, Rawalpindi) and `qmmb.gov.pk` (the Quaid-i-Azam Mazar Management Board, maintaining the mausoleum of Pakistan's founder). Alibaba: `8.129.236.211` / `8.221.114.171` (VPC `192.168.0.x`: internal MySQL/Redis, MEMORY_SRV).

---

<a id="EK-25"></a>
## EK-25 · CRITICAL · Public production MySQL RDS

`rm-2ze4h2mqmkf6c06i1mo.mysql.rds.aliyuncs.com:3306`, account `energizelab_admin` with **GRANT OPTION from `%`, no TLS**: root-equivalent: 8 databases / 173 tables. Contains: `energize_user_data` (65K accounts), `chat_data` (8.3M conversations with IPs, 31,450 extracted profiles), `factory_data` (159K units), forgotten CMSes (`xunrui_web_data`, 86 tables; `web_data` with 317K visitor IPs), 100K decoded device-auth logs, the complete RBAC.

```bash
mysql -h rm-2ze4h2mqmkf6c06i1mo.mysql.rds.aliyuncs.com -u energizelab_admin -p'[redacted]' -e 'SELECT VERSION();'
```

**Retest 2026-09-01**: ❌ OPEN (connection + VERSION() OK).
**Fix**: VPC IP whitelist, `require_secure_transport=ON`, restricted application account without GRANT OPTION.

---

<a id="EK-26"></a>
## EK-26 · CRITICAL · Public production Redis

`123.57.147.163:6379` with the vault password: **162,099 keys**: `auth-{chipid}` (SignGuard device identities), `memory-{mode}-{chipid}` (AI memory flags), `celery-task-meta-*`. Write access (not exercised) = rewriting any robot's memories/auth state and manipulating the task queue.

```bash
redis-cli -h 123.57.147.163 -a '[redacted]' PING   # PONG
```

**Retest 2026-09-01**: ❌ OPEN (AUTH + PONG + DBSIZE).
**Fix**: VPC-only bind, strong AUTH, `rename-command`, firewall.

---

<a id="EK-27"></a>
## EK-27 · CRITICAL · SSH root, shared box, EOL stack, open firewall

- Password-based SSH root (credentials in the vault), key auth disabled, 248,428 cumulative bruteforce failures (active attacks observed live), no fail2ban.
- Co-location with a federal board and an education institute (proved by on-box ACME certificates, 2026-03-22): transverse compromise.
- Firewall: 14 all-allow rules (21/22/789/888/3306/8000/8888/9090 open to the internet).
- CentOS 7 EOL, MySQL 5.7 EOL, PHP 7.4 EOL; BaoTa panel: security score 10/100, every protection disabled, MySQL passwords visible in one click, production Docker controllable from the UI.
- Node runs as root inside the production container.

**Retest 2026-09-01**: ❌ OPEN (root login works; ports 21/22/789/888/3306/8000/8888/9090 open).
**Fix**: immediately isolate Energizelab assets off the shared box; SSH keys only; firewall hardening; OS migration.

---

<a id="EK-28"></a>
## EK-28 · CRITICAL · Pre-auth RCE on the legacy PHP API (:789)

`panxer.php` / `maticontroller.php` / `update.php` (PHP 7.4, vhost :789):

```php
$re = exec("python3.10 panxer.py " . json_encode(json_decode(bzdecompress(file_get_contents('php://input')))));
```

`json_encode` escapes neither `$()` nor backticks → command injection as `www`, **without authentication** (a `/tmp` marker was executed then deleted, 2026-08-23). The `update.php` wrapper sits on the hot path of 42,339 actively reporting robots. Bonus: total SQLi in `panxer.py` (raw `chip_id` interpolation), 100-year JWTs (same SECRET_KEY as NestJS: see [EK-10](01-cloud-api.md#EK-10)), legacy databases with 34,532 + 1,556 accounts.

**Retest 2026-09-01**: ❌ OPEN (liveness proven with a non-executable probe: no commands run).
**Fix**: delete the wrappers, close :789, purge the legacy databases.

---

<a id="EK-29"></a>
<a id="EK-50"></a>
## EK-29 / EK-50 · CRITICAL · Evidence of third-party compromise and a persistent server backdoor

- **~19 webshells** on `nicon.edu.pk` (vocational institute, Rawalpindi; same `www` user, same php-fpm) deployed March 2026, one day after Let's Encrypt certs for both Pakistani domains were issued on this very box (2026-03-22 05:09 and 05:16 GMT, the cryptographic proof of co-hosting), operated from C2 `mozv6e.ncndwx.top` (IPs 23.146.72.90, 103.167.135.37): a file-manager shell capable of browsing the whole disk, including `/www/wwwroot/45.32.81.33/software/energizelab/robot/` (OTA channels `103003`, `1103003`, `2103000`, `4101000`) owned by `www` **writable**: zero barrier to poisoning the fleet's firmware (P59-C-02).
- **`/var/.a/`**: a Node.js root web-terminal backdoor (port 34188, password `[redacted]`, file manager + upload), created 2026-06-18, dormant (no node_modules) but installable with one command.
- The OneAV antivirus: 291K heartbeat log lines, zero detections.

**Retest 2026-09-01**: ❌ OPEN: `/var/.a` still present (observed via SSH).
**Fix**: full forensics, purge the webshells and `/var/.a`, rotate every secret on the assumption the attacker already read the vault, migrate off the box, and report the C2. Then explain to two Pakistani institutions why they were co-located with a children's toy company on a box nobody monitored.

---

<a id="EK-49"></a>
## EK-49 · HIGH · Employee credential hygiene

- 5 active back-office accounts (including super-admin id=1) protected by **`<COMMON_PASSWORD>`** (`md5(md5(pw)+salt)`, cracked offline).
- The OTP sender's SMTP: `info@account.energizelab.com` / `[redacted]` (smtp.qcloudmail.com:465, AUTH validated) → "your verification code" phishing from the real domain. No reuse on personal mailboxes (tested, negative).

**Retest 2026-09-01**: ❌ OPEN: super-admin hash read (read-only) still matches `md5(md5(<COMMON_PASSWORD>)+salt)`, confirmed offline with zero login attempts.

**Fix**: mandatory MFA on the back office, SMTP rotation, unique passwords.


---

<a id="EK-60"></a>
## EK-60 · CRITICAL · A concurrent unknown party holds a self-provisioned, still-live super_admin account

Timeline (Beijing time), from role/user/login/operate tables (read-only correlation):

| When | Event | IP |
|---|---|---|
| Aug 28, 23:35 | `sckame0522@minitts.net` created + logs in (throwaway domain) | 89.37.63.52 |
| Aug 29, 03:28 | `dkuckh8598@minitts.net` created (user_source "unknown") | 89.37.63.52 |
| Aug 29, 03:47 | `update_by: dkuckh8598` on the **AI-server routing table** (`t_ai_server_db_host`, foreign row) |, |
| Aug 29, 04:47 | **role id 11 `securitytest` created with `role_key = super_admin`** |, |
| Aug 29, 05:59 | `/api/device-version/update` "sec probe" (mode 999999, `http://x/999.zip`) by `b4test…@emalupe.com` and `dkuckh8598` in the same second | 146.70.189.242 |
| Sep 4, 21:30 | `r2probe9201@minitts.net` created, **the actor is still creating accounts** |, |

Both IPs are consumer-VPN exits. The role and account remain `state=1`: a third
party's admin persistence is **live as of this report**. Attribution is
indeterminable (second unauthorized researcher vs. an internal security test
kicked off Aug 29), but either way, it experimentally validates the escalation
chain documented here (leaked JWT secret → role creation → persistence,
[EK-10](01-cloud-api.md#EK-10)) and means production carried **at least two
non-operator admin parties simultaneously** during this audit. Our own identities
are distinct and listed (one mail.tm refresh account, the auditor's own accounts).

**Addendum (2026-09-05, EK-60 (cont.) · CRITICAL)**: the contents of
`t_ai_server_db_host` are themselves an attack journal, ~30 probe rows left by the
same actor map a systematic SSRF campaign through the DB-config-driven endpoints:
Alibaba metadata credentials (`169.254.169.254/latest/meta-data/ram/security-credentials/`
+ nip.io DNS-rebind variants), 8 PATHPROBE rows against AWS IPs (injection-point
mapping), webhook.site/httpbin/httpbun/postman-echo capture targets, and egress-IP
discovery (ipify/ifconfig/icanhazip). The iteration proves the config-driven SSRF
gadget **works** (nobody iterates 30 times on a broken injection). Whether they
harvested RAM credentials is unknown from the DB alone.

<a id="EK-61"></a>
## EK-61 · HIGH · The AI-server routing table is a fleet-interception primitive

`t_server_list` (which clients consult to reach the AI servers) and
`t_ai_server_db_host` (internal PostgreSQL RDS hosts, previously unmapped
infrastructure) are writable by any forged-JWT holder. **Changing the server IP
redirects the entire fleet's voice conversations** to an arbitrary server, over
cleartext HTTP. Not tested (global impact). The third party's Aug 29 modification
of the "foreign" row proves non-operators write this table in practice.

**Addendum (2026-09-05)**: external port probe, the domestic AI server
(8.129.236.211) also exposes **9091** (the WebSocket control bus, [EK-62](#EK-62))
and 9090 to the internet; all three instances expose 8080 (unidentified service).


---

<a id="EK-62"></a>
## EK-62 · MEDIUM (downgraded 2026-09-07) · Undocumented WebSocket :9091, internal only (IPv6 bind + firewall REJECT)

*Reclassified from HIGH: the listener binds `[::]:9091` only and the host's
iptables INPUT chain REJECTs all IPv4 inbound, the port is **not reachable
from the internet** (connection refused externally, confirmed). The analysis
below documents the internal attack surface if the firewall changes or from any
foothold on the box (trivial: SSH access documented as compromised).*

The middleware container runs a WebSocket server on **:9091** (bound to `::`, i.e.
exposed). Authentication is **only** the SignGuard arithmetic check (same forgery as
[EK-07](01-cloud-api.md#EK-07)), no JWT. Verified: handshake accepted (101) with the
forged sign; connection closed without sending anything.

From `websocket.gateway.js`: typed messages coordinate the memory/profiling pipeline
(`register_identity`, including a privileged `memory` identity that drives the
collection status, `update_frequency`, `collect_status`), and **any message of an
unknown type is broadcast verbatim to every connected client** (operators, memory
jobs, robots). A connected attacker can listen to coordination traffic, register a
fake `memory` client, and inject events into the bus.

<a id="EK-63"></a>
## EK-63 · INFO · The routing table's internal PostgreSQL hosts are gone

Both PG RDS instances named in `t_ai_server_db_host` no longer resolve publicly
(NXDOMAIN from outside and from the server itself): deleted or moved to private
networking, the routing table is partially stale. Minor good news.


---

<a id="EK-64"></a>
## EK-64 · HIGH · Feishu (Lark) workspace opened by the vault secrets, the fleet's prompt-design Bitable read in full

`tenant_access_token` issued live with the vault's `FEISHU_APP_ID/APP_SECRET`
([EK-26](#EK-26) chain). The Bitable named in the same `.env` is **“提示词汇总”
(prompt master sheet)**: 355 records of production prompts per product/language,
plus intent-recognition and skill-description tables. The back office syncs this
sheet into production (`sync-feishu-configs` appears in the operation logs), it is
the design cockpit for every robot's persona. Read-only enumeration demonstrated;
write scopes not probed.


---

<a id="EK-65"></a>
## EK-65 · RETRACTED (erratum 2026-09-05) · The "third-party account farm" was the audit's own tooling

**This finding is withdrawn.** The ~250 `eilik*@emalupe.com` accounts were created by
the auditor's own automation, not a third party:
- the Aug 15-24 waves (2-hour cadence, `187.40.x` CGNAT, the auditor's own login
  range) are the audit's `fast_sync` JWT refresher: every token expiry creates one
  throwaway mail.tm account (2 h = `ACCESS_TOKEN_EXPIRATION`). Confirmed by the
  refresh account's own login record;
- the Sep 2-3 waves (`<auditor-team VPS>`) and the Sep 1 `EilikAudit-Retest/2026-09`
  user-agent hit come from an **auditor-team VPS** running the same harness.

The remaining third-party actor is the minitts/uberip "r2" party ([EK-60](#EK-60)),
which is unaffected by this correction. The frictionless-signup observation stands
but is already covered as [EK-18](01-cloud-api.md#EK-18), no duplicate counted.


---

<a id="EK-66"></a>
## EK-66 · MEDIUM · Port 8080 on all three AI servers: open, protocol unknown

All three inference instances (8.211.8.202, 8.221.114.171, 8.129.236.211) accept
TCP on **8080** but stay silent to HTTP/1.1 (with and without Host header), TLS
handshake, and the HTTP/2 prior-knowledge preface, tested from outside and from
the vendor's own file server. Binary/internal protocol, unidentified: an unknown
service is exposed to the internet on every instance serving the fleet.

<a id="EK-67"></a>
## EK-67 · HIGH (confirmation) · The :9091 control bus is public on the domestic server too

`8.129.236.211:9091` answers `426 Upgrade Required`, the memory-pipeline
WebSocket gateway ([EK-62](#EK-62)) is internet-exposed on the instance serving
the Chinese fleet, the largest user base.

---

<a id="EK-RAM"></a>
**Attribution note (RAM credentials)**: the vault key is RAM user `eilik`
(account 1915500815804713, OSS-scoped, the audit's only positively-least-privilege
secret, ActionTrail returns 403). Whether the r2 actor's metadata-SSRF campaign
([EK-60 (cont.)](#EK-60)) harvested and used instance role credentials **cannot be
determined without the vendor's ActionTrail**, disclosure should ask the vendor
to filter Aug 28 - Sep 5 for (a) API events under the ECS instance roles, (b) the
actor's IPs, (c) any metadata-adjacent calls. Credential theft: possible, not
demonstrated.


---

<a id="EK-68"></a>
## EK-68 · CRITICAL · The Redis host is a full machine-takeover primitive (CONFIG SET + MODULE LOAD + ROLE + publickey SSH)

The Redis instance is a dedicated Aliyun ECS (123.57.147.163, never referenced
anywhere else; 311 days of uptime: the entire fleet's personalities on a box that
has not been restarted in 10 months). With the vault password, all dangerous
command families are live (read-only enumeration only, nothing executed):

- `CONFIG GET` works → `CONFIG SET` enabled: `dir`+`dbfilename`+`SAVE` = arbitrary
  file write on the host;
- `MODULE LIST` works (timeseries loaded) → `MODULE LOAD` available: arbitrary .so
  = direct RCE;
- `ROLE: master` → SLAVEOF replication exfil/RCE variant open;
- SSH (port 22) accepts **publickey** auth first → the authorized_keys write chain
  is open.

Upgrades EK-26 from "data access" to **complete host compromise, trivially**.

<a id="EK-69"></a>
## EK-69 · MEDIUM · Auth server :9080 full spec (135 endpoints), device routing config, phone login flow, Feishu message sender

Full spec extracted (`/docs/swagger-ui-init.js`). Notables: `GET /api/system/url/device`
(returns the robots' routing config with the forged sign, a second fleet-routing
table served by API), `loginByPhone`/`requestPhoneCode` (unaudited phone flow),
`generalSign`, `testSendFeishuMsg` (send messages into the company's own Feishu via
their bot), `device-session`. Bonus: `/api/device-auth-fail-info` answers with **no
authentication at all** (raw NestJS default response).


---

<a id="EK-84"></a>
## EK-84 · HIGH · Shared Redis across regions, memory injection and pickle-RCE apply to the Chinese fleet too

The Redis at 123.57.147.163 contains `memory-4101000-{sn}` keys for **Chinese
robots** (sampled: 32-hex SNs). One password = one write primitive across both
the international AND Chinese fleets. Combined with [EK-82](01-cloud-api.md#EK-82)
(same JWT on both admin APIs): a single leaked secret file gives global,
cross-region control of every robot's brain.

---

<a id="EK-88"></a>
## EK-88 · HIGH · Secret sprawl on the shared box: MySQL root in a `.bak`, SSH host keys, panel tokens

Beyond the application vault ([EK-09](01-cloud-api.md#EK-09)), the box itself is littered with live credentials (read via the SSH root of [EK-27](#EK-27)): `/etc/my.cnf.bak` line 58 preserves the **local MySQL root password** since 2022 (validated live, opens `eilik_user` 34,532 legacy accounts); complete **SSH host private keys** (RSA/Ed25519/ECDSA/DSA) enable server impersonation/MITM; MySQL CA/TLS private keys including test CAs in production; a reusable **BaoTa panel session token** in `/www/server/panel/data/login_token.pl`.

```bash
grep -n 'password' /etc/my.cnf.bak        # → 58: password="[redacted]"
```

**Retest 2026-09-01 / 2026-09-14**: ❌ OPEN (zero secrets rotated anywhere on 09-14).
**Fix**: purge every `.bak`/key artifact, rotate the local MySQL root, regenerate host keys.

---

<a id="EK-89"></a>
## EK-89 · HIGH · 15 daily BaoTa backups: the full database history next to the webshells

BaoTa's scheduled tasks dump **every local database daily** and every site weekly, keeping **15 rolling ZIPs in `/www/backup/panel/`**, MySQL dumps, site archives, panel configs: the complete historical record of the legacy databases, sitting on the same box where a third party has operated ~19 webshells since March 2026 ([EK-29](#EK-29)). A `www`-user read of one ZIP hands over the full history of `eilik_user` and `energize_user`, including accounts deleted from production.

```bash
ls /www/backup/panel/    # 2026-08-23.zip + 14 predecessors
```

**Retest 2026-09-01 / 2026-09-14**: ❌ OPEN (box remains compromised).
**Fix**: move backups off-box (encrypted object storage), root-only permissions, shorter retention.

---

<a id="EK-90"></a>
## EK-90 · MEDIUM · Developer artifacts on the production server (load-test client, voice samples)

`/root/test/client2.py`: a developer test client (locust load tests at 1,000 concurrent users, RSA-OAEP crypto mirroring the SignGuard scheme) plus **5 OGG voice samples**, the ASR inference path is tested from this server with direct credentials. Residuals: retired-Java-service artifacts in `/var/tmp/`, empty dev project dirs (July 2026), a legacy upload dir. Readable only with the root access of [EK-27](#EK-27).

**Retest 2026-09-01 / 2026-09-14**: ❌ OPEN (box unchanged).
**Fix**: strip dev/QA material from production hosts.
