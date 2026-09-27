-- Eilik PoC: PostgreSQL Schema
-- Energizelab Security Audit: Independent security research 2026

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ─────────────────────────────────────────────
-- USERS (from /api/user/list)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id           INTEGER PRIMARY KEY,
    email        TEXT,
    nickname     TEXT,
    realname     TEXT,
    phone        TEXT,
    avatar_url   TEXT,
    sex          INTEGER,
    login_num    INTEGER DEFAULT 0,
    user_source  TEXT,
    state        INTEGER DEFAULT 1,
    create_time  TIMESTAMPTZ,
    update_time  TIMESTAMPTZ,
    synced_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- ─────────────────────────────────────────────
-- DEVICES (from /api/device/list)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS devices (
    id                  INTEGER PRIMARY KEY,
    device_mac_id       TEXT UNIQUE,
    device_type         TEXT,   -- QL = Eilik/Eiliko, ES = AI Station
    device_nick         TEXT,
    device_origin_name  TEXT,
    cpu_id              TEXT,   -- 32-hex long SN
    device_type_id      TEXT,
    create_time         TIMESTAMPTZ,
    update_time         TIMESTAMPTZ,
    synced_at           TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_devices_mac    ON devices(device_mac_id);
CREATE INDEX IF NOT EXISTS idx_devices_cpu_id ON devices(cpu_id);

-- ─────────────────────────────────────────────
-- USER → DEVICE mapping (from /api/user-device/list)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_devices (
    id              INTEGER PRIMARY KEY,
    user_id         INTEGER REFERENCES users(id) ON DELETE CASCADE,
    user_email      TEXT,
    device_mac_id   TEXT,
    device_type     TEXT,
    upload_way      TEXT,
    create_time     TIMESTAMPTZ,
    synced_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ud_user_id  ON user_devices(user_id);
CREATE INDEX IF NOT EXISTS idx_ud_mac      ON user_devices(device_mac_id);
CREATE INDEX IF NOT EXISTS idx_ud_email    ON user_devices(user_email);

-- ─────────────────────────────────────────────
-- CONVERSATIONS (from /api/chat-data/list)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS conversations (
    id                      BIGINT PRIMARY KEY,
    sn                      TEXT,    -- device identifier (cpu_id prefix)
    user_ip                 TEXT,    -- public IP (may contain "public private")
    public_ip               TEXT,    -- extracted public IP
    private_ip              TEXT,    -- extracted LAN IP
    chat_time               TIMESTAMPTZ,
    question                TEXT,    -- what user said (ASR transcript)
    answer                  TEXT,    -- what robot responded
    mode_number             TEXT DEFAULT '4101000',
    total_token             INTEGER,
    model_output_token      INTEGER,
    model_input_token       INTEGER,
    wakeup                  BOOLEAN,
    synced_at               TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conv_sn       ON conversations(sn);
CREATE INDEX IF NOT EXISTS idx_conv_ip       ON conversations(public_ip);
CREATE INDEX IF NOT EXISTS idx_conv_time     ON conversations(chat_time DESC);
CREATE INDEX IF NOT EXISTS idx_conv_mode     ON conversations(mode_number);

-- ─────────────────────────────────────────────
-- CHAT MEMORY: Psychological Profiles (from /api/chat-memory/list)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_memories (
    id              BIGINT PRIMARY KEY,
    sn              TEXT UNIQUE,
    summary         JSONB,          -- full psychological profile
    name            TEXT,
    age             TEXT,
    sex             TEXT,
    profession      TEXT,
    address         TEXT,
    character       TEXT,
    birthday        TEXT,
    constellation   TEXT,           -- zodiac sign
    family_relations TEXT,
    friends         TEXT,
    pet             TEXT,
    food_preference TEXT,
    game_preferences TEXT,
    movie_preferences TEXT,
    music_preference TEXT,
    parental_information TEXT,
    enabled         BOOLEAN DEFAULT TRUE,
    create_time     TIMESTAMPTZ,
    update_time     TIMESTAMPTZ,
    synced_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mem_sn ON chat_memories(sn);

-- ─────────────────────────────────────────────
-- WEATHER LOGS: Geographic Data (from /api/weather-log/list)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS weather_logs (
    id          BIGINT PRIMARY KEY,
    ip          TEXT,
    chip_id     TEXT,   -- = cpu_id of the device
    city        TEXT,
    weather_raw JSONB,
    temperature TEXT,
    weather_desc TEXT,
    create_time TIMESTAMPTZ,
    synced_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_wlog_chip ON weather_logs(chip_id);
CREATE INDEX IF NOT EXISTS idx_wlog_ip   ON weather_logs(ip);
CREATE INDEX IF NOT EXISTS idx_wlog_city ON weather_logs(city);

-- ─────────────────────────────────────────────
-- TIME LOGS: Robot Clock Sync (from /api/time-log/list)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS time_logs (
    id          BIGINT PRIMARY KEY,
    ip          TEXT,
    chip_id     TEXT,
    local_time  TEXT,
    create_time TIMESTAMPTZ,
    synced_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tlog_chip ON time_logs(chip_id);
CREATE INDEX IF NOT EXISTS idx_tlog_ip   ON time_logs(ip);

-- ─────────────────────────────────────────────
-- LOGIN LOGS (from /api/user-login-info/list)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS login_logs (
    id          BIGINT PRIMARY KEY,
    email       TEXT,
    phone       TEXT,
    login_type  TEXT,
    user_source TEXT,
    ip          TEXT,
    create_time TIMESTAMPTZ,
    synced_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_llog_email ON login_logs(email);
CREATE INDEX IF NOT EXISTS idx_llog_ip    ON login_logs(ip);

-- ─────────────────────────────────────────────
-- FACTORY DEVICES (from /api/factory-device/list)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS factory_devices (
    serial_id       BIGINT PRIMARY KEY,
    cpu_id          TEXT UNIQUE,
    mode_number     TEXT,
    upload_time     TIMESTAMPTZ,
    qualified_time  TIMESTAMPTZ,
    color           TEXT,
    outbound_time   TIMESTAMPTZ,
    area_code       TEXT,
    agent_organization TEXT,
    operation_count INTEGER DEFAULT 0,
    refurbished     BOOLEAN DEFAULT FALSE,
    synced_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fd_cpu_id ON factory_devices(cpu_id);

-- ─────────────────────────────────────────────
-- SYNC STATE: track what's been synced
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sync_state (
    key         TEXT PRIMARY KEY,
    value       TEXT,
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO sync_state(key, value) VALUES
    ('users_synced',         '0'),
    ('devices_synced',       '0'),
    ('conversations_synced', '0'),
    ('memories_synced',      '0'),
    ('weather_synced',       '0'),
    ('time_logs_synced',     '0'),
    ('login_logs_synced',    '0'),
    ('last_sync',            NULL)
ON CONFLICT(key) DO NOTHING;

-- ─────────────────────────────────────────────
-- VIEWS: cross-referenced data
-- ─────────────────────────────────────────────

-- Full user profile: user + their robots + memory profile
CREATE OR REPLACE VIEW v_user_profiles AS
SELECT
    u.id                    AS user_id,
    u.email,
    u.nickname,
    u.realname,
    u.phone,
    u.avatar_url,
    u.login_num,
    u.user_source,
    u.create_time           AS registered_at,
    -- Robots
    COUNT(DISTINCT ud.device_mac_id) AS robot_count,
    STRING_AGG(DISTINCT d.device_origin_name, ', ') AS robot_names,
    STRING_AGG(DISTINCT ud.device_mac_id, ', ')     AS robot_macs,
    STRING_AGG(DISTINCT d.cpu_id, ', ')             AS cpu_ids,
    -- Conversations
    COUNT(DISTINCT c.id)    AS conversation_count,
    MAX(c.chat_time)        AS last_conversation,
    -- Memory
    MAX(m.address)          AS profile_address,
    MAX(m.age)              AS profile_age,
    MAX(m.profession)       AS profile_profession,
    MAX(m.family_relations) AS profile_family,
    MAX(m.character)        AS profile_character,
    MAX(m.food_preference)  AS profile_food,
    MAX(m.game_preferences) AS profile_games,
    -- Login
    COUNT(DISTINCT ll.ip)   AS unique_ips,
    MAX(ll.create_time)     AS last_login
FROM users u
LEFT JOIN user_devices ud ON ud.user_id = u.id OR ud.user_email = u.email
LEFT JOIN devices d       ON d.device_mac_id = ud.device_mac_id
LEFT JOIN chat_memories m ON m.sn = d.cpu_id
LEFT JOIN conversations c ON c.sn LIKE CONCAT(LEFT(d.cpu_id, 20), '%')
LEFT JOIN login_logs ll   ON ll.email = u.email
GROUP BY u.id, u.email, u.nickname, u.realname, u.phone, u.avatar_url,
         u.login_num, u.user_source, u.create_time;

-- Device with owner and memory
CREATE OR REPLACE VIEW v_device_profiles AS
SELECT
    d.id                    AS device_id,
    d.device_mac_id,
    d.device_type,
    d.device_origin_name,
    d.cpu_id,
    ud.user_email           AS owner_email,
    ud.user_id              AS owner_id,
    u.nickname              AS owner_nickname,
    u.avatar_url            AS owner_avatar,
    m.summary               AS psychological_profile,
    m.address               AS location,
    COUNT(c.id)             AS conversation_count,
    MAX(c.chat_time)        AS last_used,
    -- Geographic
    wl.city                 AS last_city,
    wl.ip                   AS last_ip
FROM devices d
LEFT JOIN user_devices ud ON ud.device_mac_id = d.device_mac_id
LEFT JOIN users u         ON u.id = ud.user_id OR u.email = ud.user_email
LEFT JOIN chat_memories m ON m.sn = d.cpu_id
LEFT JOIN conversations c ON c.sn LIKE CONCAT(LEFT(d.cpu_id, 20), '%')
LEFT JOIN LATERAL (
    SELECT city, ip FROM weather_logs
    WHERE chip_id = d.cpu_id
    ORDER BY create_time DESC LIMIT 1
) wl ON TRUE
GROUP BY d.id, d.device_mac_id, d.device_type, d.device_origin_name, d.cpu_id,
         ud.user_email, ud.user_id, u.nickname, u.avatar_url,
         m.summary, m.address, wl.city, wl.ip;

-- Geographic distribution
CREATE OR REPLACE VIEW v_geographic AS
SELECT
    city,
    COUNT(DISTINCT chip_id) AS devices,
    COUNT(*)                AS weather_queries,
    MAX(create_time)        AS last_seen
FROM weather_logs
WHERE city IS NOT NULL AND city != ''
GROUP BY city
ORDER BY devices DESC;
