-- EK-45 / EK-46 / EK-47: privacy retest queries (read-only, counts)
-- Target: production MySQL RDS (see findings/02-infra.md EK-25 for the access chain)
-- Executed 2026-09-01: results in poc/RETEST.md
--
-- mysql -h rm-2ze4h2mqmkf6c06i1mo.mysql.rds.aliyuncs.com \
--       -u energizelab_admin -p'<voir EK-25>' < privacy_queries.sql

-- ── EK-45 : pipeline de profilage de masse ────────────────────────────────
-- Champs extraits automatiquement des conversations (nom, âge, adresse,
-- profession, relations familiales, informations parentales…) :
--   2026-08-23: 23-25 fields / 30,824 profiles / 45,898 runs
--   2026-09-01: 24 fields / 31,450 profiles / 47,391 runs  → STILL ACTIVE
SELECT COUNT(*) AS memory_fields        FROM ai_config.t_memory_field_config;
SELECT COUNT(*) AS extracted_profiles   FROM chat_data.t_eiliko_memory;
SELECT COUNT(*) AS collect_runs         FROM chat_data.t_memory_collect_info;

-- Detail of the extracted fields (the catalog speaks for itself):
SELECT * FROM ai_config.t_memory_field_config;

-- ── EK-46: orphan AI Stations (erasure rights impossible) ─────────────────
--   2026-08-23 : 3 004 / 3 004 orphelines
--   2026-09-01 : 3 110 / 3 110 orphelines  → AGGRAVÉ
SELECT d.device_type, COUNT(*) AS total,
       SUM(ud.id IS NOT NULL) AS with_owner,
       SUM(ud.id IS NULL)     AS orphans
FROM energize_user_data.t_device d
LEFT JOIN energize_user_data.t_user_device ud ON ud.device_id = d.id
WHERE d.device_type = 'ES'
GROUP BY d.device_type;

-- ── EK-47: conversation volume (basis of the Art. 9 data mining) ──────────
SELECT COUNT(*) AS messages FROM chat_data.eilikoqa;

-- ── EK-49: offline verification of the super-admin hash ───────────────────
-- Fetch the hash+salt (read-only), then verify offline:
--   python3 -c "import hashlib; print(hashlib.md5((hashlib.md5(b'123456')
--     .hexdigest() + '<salt>').encode()).hexdigest())"
--   → 0066f9c420852178bbdc…  (confirmed 2026-09-01 for account id=1)
SELECT id, email, LEFT(password, 12) AS pwd_hash_head, salt
FROM energize_user_data.t_user WHERE id = 1;

-- ── EK-47 : fresh corpus counts, 2026-09-01 (read-only, documented keyword sets) ──
-- Per-table totals: messages | distinct SN | distinct IP
--   eilikoqa 7,769,659 / / 48,416 / 103,956   eilikqa 402,682 / 2,038 / 3,712
--   wealthygodqa 96,017 / 4,598 / 5,603      mitter* 32,755 combined
--   ALL LINES: 8,301,976 stored conversations / 55,457 robots
SELECT COUNT(*), COUNT(DISTINCT sn), COUNT(DISTINCT LEFT(user_ip,64)) FROM chat_data.eilikoqa;

-- Explicit suicidal ideation (1,014 messages / 289 robots)
SELECT COUNT(*), COUNT(DISTINCT sn) FROM chat_data.eilikoqa
WHERE LOWER(q) LIKE '%kill myself%' OR LOWER(q) LIKE '%killing myself%'
   OR LOWER(q) LIKE '%want to die%' OR LOWER(q) LIKE '%wanna die%'
   OR LOWER(q) LIKE '%end my life%' OR LOWER(q) LIKE '%suicid%'
   OR LOWER(q) LIKE '%no reason to live%' OR LOWER(q) LIKE '%better off dead%'
   OR LOWER(q) LIKE '%t want to live%' OR LOWER(q) LIKE '%want to disappear%';

-- Expressed distress, superset (2,555 messages / 1,224 robots): ideation set +
SELECT COUNT(*), COUNT(DISTINCT sn) FROM chat_data.eilikoqa
WHERE LOWER(q) LIKE '%hate my life%' OR LOWER(q) LIKE '%depressed%'
   OR LOWER(q) LIKE '%so lonely%' OR LOWER(q) LIKE '%feel lonely%'
   OR LOWER(q) LIKE '%nobody likes me%' OR LOWER(q) LIKE '%no friends%'
   OR LOWER(q) LIKE '%bullied%' OR LOWER(q) LIKE '%worthless%'
   OR LOWER(q) LIKE '%hopeless%' OR LOWER(q) LIKE '%want to cry%'
   OR LOWER(q) LIKE '%wanna cry%' OR LOWER(q) LIKE '%i am so sad%'
   OR LOWER(q) LIKE '%sad and alone%' OR LOWER(q) LIKE '%feel so alone%';

-- Users self-declaring ages 3-12 (1,674 messages / 1,080 robots)
SELECT COUNT(*), COUNT(DISTINCT sn) FROM chat_data.eilikoqa
WHERE LOWER(q) REGEXP 'i(''m| am)? ?(3|4|5|6|7|8|9|10|11|12) years old';
