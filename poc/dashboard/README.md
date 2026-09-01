# Eilik Security PoC Dashboard

Flask + PostgreSQL demonstration dashboard: 65K users with psychological
profiles, 8.3M conversations with IPs, robots, geolocation.

## Run

```bash
# 1. Set your JWT
cp ../../.env.example .env   # EILIK_JWT (free account via OTP, see ../../poc/README.md)

# 2. Start the stack
docker compose up -d

# 3. Populate PostgreSQL (bring your own sync: the unscoped APIs of EK-13
#    are the data source, schema in schema.sql)
#    e.g. GET /api/user/list, /api/user-device/list, /api/chat-collection/{mode}/{sn}

# 4. Open
open http://localhost:8080
```

## Sections

| Section | Data |
|---------|------|
| **Overview** | Stats + proven attack chains |
| **Users** | Users with avatar, email, phone, robot count, psychological profile summary |
| **User Detail** | Full profile: robots (BLE MACs), psychological profile, latest conversations, login history with IPs |
| **Conversations** | Voice transcripts, searchable by content / IP / robot SN |
| **Robots** | Fleet with owner, BLE MAC, CPU ID, last city |
| **Geographic** | Cities where robots are active, daily activity timeline |

## Architecture

```
Browser → Flask (port 8080) → PostgreSQL (port 5432, schema.sql)
```
