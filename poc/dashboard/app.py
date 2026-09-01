#!/usr/bin/env python3
"""
Eilik PoC Dashboard: Flask API + HTML
2026-06-14
"""

import os, json, psycopg2, psycopg2.extras, requests as req_lib
import threading, queue
from flask import Flask, jsonify, render_template, request, Response

app = Flask(__name__)
DB = os.getenv('DATABASE_URL', 'postgresql://eilik:eilik_audit_2026@localhost:5432/eilik_poc')

_ip_geo_cache: dict = {}  # ip -> {'country','code','city'}
_geo_queue: queue.Queue = queue.Queue(maxsize=10000)

def _ensure_ip_geo():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ip_geo (
                ip TEXT PRIMARY KEY,
                country TEXT,
                country_code TEXT,
                city TEXT,
                synced_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute("ALTER TABLE ip_geo ADD COLUMN IF NOT EXISTS city TEXT")
        conn.close()
    except Exception:
        pass

def _resolve_batch(ips_batch: list):
    """Appel ip-api.com pour une liste ≤100 IPs. Stocke en cache + DB."""
    try:
        resp = req_lib.post(
            'http://ip-api.com/batch?fields=query,country,countryCode,city&lang=en',
            json=ips_batch, timeout=8
        )
        inserts = []
        for item in resp.json():
            ip = item.get('query')
            if ip:
                val = {
                    'country': item.get('country', '') or '',
                    'code': item.get('countryCode', '') or '',
                    'city': item.get('city', '') or '',
                }
                _ip_geo_cache[ip] = val
                inserts.append((ip, val['country'], val['code'], val['city']))
        if inserts:
            conn = get_db()
            psycopg2.extras.execute_values(
                conn.cursor(),
                "INSERT INTO ip_geo (ip, country, country_code, city) VALUES %s "
                "ON CONFLICT (ip) DO UPDATE SET country=EXCLUDED.country, "
                "country_code=EXCLUDED.country_code, city=EXCLUDED.city",
                inserts
            )
            conn.close()
    except Exception as e:
        print(f"[geoip-resolve] {e}")

def _geo_bg_worker():
    """Worker de fond : vide _geo_queue en lots de 100."""
    while True:
        batch = []
        try:
            batch.append(_geo_queue.get(timeout=5))
            while len(batch) < 100:
                batch.append(_geo_queue.get_nowait())
        except queue.Empty:
            pass
        if batch:
            _resolve_batch(batch)

# Background worker startup
_geo_thread = threading.Thread(target=_geo_bg_worker, daemon=True)
_geo_thread.start()

def get_geo(ips: list, background: bool = False) -> dict:
    """Return dict ip -> {country, code, city}: all in English.
    background=True: ne bloque pas: retourne le cache et enfile les IPs manquantes.
    """
    ips = list({ip for ip in ips if ip})
    if not ips:
        return {}
    result = {}
    missing = []
    for ip in ips:
        if ip in _ip_geo_cache:
            result[ip] = _ip_geo_cache[ip]
        else:
            missing.append(ip)
    if missing:
        # Charger depuis DB
        try:
            conn = psycopg2.connect(DB)
            conn.autocommit = True
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT ip, country, country_code, city FROM ip_geo WHERE ip = ANY(%s)", [missing])
            for r in cur.fetchall():
                val = {'country': r['country'] or '', 'code': r['country_code'] or '', 'city': r['city'] or ''}
                result[r['ip']] = val
                _ip_geo_cache[r['ip']] = val
            conn.close()
        except Exception:
            pass
        missing = [ip for ip in missing if ip not in result]
    if missing:
        if background:
            # Enfile sans bloquer
            for ip in missing:
                try:
                    _geo_queue.put_nowait(ip)
                except queue.Full:
                    pass
        else:
            # Synchronous resolution (small batches, e.g. 1-2 IPs for users/robots)
            _resolve_batch(missing[:100])
            for ip in missing[:100]:
                if ip in _ip_geo_cache:
                    result[ip] = _ip_geo_cache[ip]
    return result

# Compat alias
def get_countries(ips: list) -> dict:
    return get_geo(ips)

def get_db():
    conn = psycopg2.connect(DB)
    conn.autocommit = True
    return conn

def query(sql, params=None, one=False):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(sql, params if params else None)
    except Exception as e:
        conn.close()
        raise e
    result = cur.fetchone() if one else cur.fetchall()
    conn.close()
    if one:
        return dict(result) if result else {}
    return [dict(r) for r in result] if result else []

# ── Stats ────────────────────────────────────────────────────────────────────

@app.route('/api/stats')
def stats():
    data = {}
    try:
        r = query("""
            SELECT
                (SELECT COUNT(*) FROM users)         AS users_n,
                (SELECT COUNT(*) FROM devices)       AS devices_n,
                (SELECT COUNT(*) FROM conversations) AS conv_n,
                (SELECT COUNT(*) FROM chat_memories) AS mem_n,
                (SELECT COUNT(*) FROM weather_logs)  AS wlog_n,
                (SELECT COUNT(*) FROM login_logs)    AS llog_n,
                (SELECT COUNT(*) FROM mv_geo_stats)  AS geo_n
        """, one=True)
        data['users']         = {'n': r['users_n'], 'emails': r['users_n']}
        data['devices']       = {'n': r['devices_n'], 'types': 5}
        data['conversations'] = {'n': r['conv_n'], 'unique_robots': r['geo_n'], 'unique_ips': r['geo_n']}
        data['memories']      = {'n': r['mem_n']}
        data['weather_logs']  = {'n': r['wlog_n']}
        data['login_logs']    = {'n': r['llog_n']}
    except Exception as e:
        data.setdefault('users',         {'n': 0})
        data.setdefault('devices',       {'n': 0})
        data.setdefault('conversations', {'n': 0})
        data.setdefault('memories',      {'n': 0})
        data.setdefault('weather_logs',  {'n': 0})
        data.setdefault('login_logs',    {'n': 0})

    try:
        sync = query("SELECT key, value, updated_at::text FROM sync_state")
        data['sync'] = {r['key']: {'value': r['value'], 'at': r['updated_at']} for r in sync}
    except:
        data['sync'] = {}
    return jsonify(data)

# ── Users ────────────────────────────────────────────────────────────────────

@app.route('/api/users')
def users():
    page        = int(request.args.get('page', 1))
    per_page    = int(request.args.get('per_page', 50))
    search      = request.args.get('q', '').strip()
    has_phone   = request.args.get('has_phone') == '1'
    has_robot   = request.args.get('has_robot') == '1'
    has_profile = request.args.get('has_profile') == '1'
    has_convs   = request.args.get('has_convs') == '1'
    sort_by     = request.args.get('sort', 'logins')
    offset      = (page - 1) * per_page

    conditions = []
    params = []
    if search:
        conditions.append("(u.email ILIKE %s OR u.nickname ILIKE %s OR u.phone ILIKE %s)")
        params += [f'%{search}%', f'%{search}%', f'%{search}%']
    if has_phone:
        conditions.append("u.phone IS NOT NULL AND u.phone != ''")
    if has_robot:
        conditions.append("EXISTS (SELECT 1 FROM user_devices ud2 WHERE ud2.user_id=u.id OR ud2.user_email=u.email)")
    if has_profile:
        conditions.append("""EXISTS (
            SELECT 1 FROM user_devices ud2
            JOIN devices d2 ON d2.device_mac_id=ud2.device_mac_id AND d2.cpu_id != ''
            JOIN chat_memories m2 ON m2.sn=d2.cpu_id
            WHERE ud2.user_id=u.id OR ud2.user_email=u.email
        )""")
    if has_convs:
        conditions.append("""(u.id IN (SELECT user_id FROM mv_users_with_convs WHERE user_id IS NOT NULL)
            OR u.email IN (SELECT user_email FROM mv_users_with_convs WHERE user_email IS NOT NULL AND user_email != ''))""")

    where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''

    if sort_by == 'convs':
        # Pre-aggregate conv_count so we can ORDER BY it
        sql = f"""
            SELECT
                u.id, u.email, u.nickname, u.realname, u.phone, u.avatar_url,
                u.login_num, u.user_source, u.create_time::text,
                COUNT(DISTINCT ud.device_mac_id) AS robot_count,
                STRING_AGG(DISTINCT d.device_origin_name, ', ') AS robot_names,
                MAX(m.name) AS profile_name,
                MAX(m.age) AS profile_age,
                MAX(m.sex) AS profile_sex,
                MAX(m.address) AS profile_address,
                MAX(m.character) AS profile_character,
                MAX(wl2.city) AS last_city,
                MAX(ll.ip) AS last_login_ip,
                COALESCE(MAX(uc.conv_total), 0) AS conv_count
            FROM users u
            LEFT JOIN user_devices ud ON ud.user_id = u.id OR ud.user_email = u.email
            LEFT JOIN devices d ON d.device_mac_id = ud.device_mac_id
            LEFT JOIN chat_memories m ON m.sn = d.cpu_id
            LEFT JOIN LATERAL (
                SELECT city FROM weather_logs WHERE chip_id = d.cpu_id
                ORDER BY create_time DESC LIMIT 1
            ) wl2 ON TRUE
            LEFT JOIN LATERAL (
                SELECT ip FROM login_logs WHERE email = u.email
                ORDER BY create_time DESC LIMIT 1
            ) ll ON TRUE
            LEFT JOIN (
                SELECT ud2.user_id, ud2.user_email, SUM(cc.conv_count) AS conv_total
                FROM user_devices ud2
                JOIN devices d2 ON d2.device_mac_id = ud2.device_mac_id AND d2.cpu_id != ''
                JOIN mv_conv_counts cc ON cc.cpu_id = d2.cpu_id
                GROUP BY ud2.user_id, ud2.user_email
            ) uc ON uc.user_id = u.id OR uc.user_email = u.email
            {where}
            GROUP BY u.id, u.email, u.nickname, u.realname, u.phone, u.avatar_url,
                     u.login_num, u.user_source, u.create_time
            ORDER BY conv_count DESC NULLS LAST, u.id
            LIMIT %s OFFSET %s
        """
    else:
        order = {
            'logins':  'u.login_num DESC NULLS LAST, u.id',
            'recent':  'u.create_time DESC',
            'robots':  'robot_count DESC NULLS LAST, u.id',
        }.get(sort_by, 'u.login_num DESC NULLS LAST, u.id')
        # Fast path: lateral conv_count only on the 50 returned rows
        sql = f"""
            SELECT base.*, lc.conv_count
            FROM (
                SELECT
                    u.id, u.email, u.nickname, u.realname, u.phone, u.avatar_url,
                    u.login_num, u.user_source, u.create_time::text,
                    COUNT(DISTINCT ud.device_mac_id) AS robot_count,
                    STRING_AGG(DISTINCT d.device_origin_name, ', ') AS robot_names,
                    MAX(m.name) AS profile_name,
                    MAX(m.age) AS profile_age,
                    MAX(m.sex) AS profile_sex,
                    MAX(m.address) AS profile_address,
                    MAX(m.character) AS profile_character,
                    MAX(wl.city) AS last_city,
                    MAX(ll.ip) AS last_login_ip
                FROM users u
                LEFT JOIN user_devices ud ON ud.user_id = u.id OR ud.user_email = u.email
                LEFT JOIN devices d ON d.device_mac_id = ud.device_mac_id
                LEFT JOIN chat_memories m ON m.sn = d.cpu_id
                LEFT JOIN LATERAL (
                    SELECT city FROM weather_logs WHERE chip_id = d.cpu_id
                    ORDER BY create_time DESC LIMIT 1
                ) wl ON TRUE
                LEFT JOIN LATERAL (
                    SELECT ip FROM login_logs WHERE email = u.email
                    ORDER BY create_time DESC LIMIT 1
                ) ll ON TRUE
                {where}
                GROUP BY u.id, u.email, u.nickname, u.realname, u.phone, u.avatar_url,
                         u.login_num, u.user_source, u.create_time
                ORDER BY {order}
                LIMIT %s OFFSET %s
            ) base
            LEFT JOIN LATERAL (
                SELECT COALESCE(SUM(cc.conv_count), 0) AS conv_count
                FROM user_devices ud2
                JOIN devices d2 ON d2.device_mac_id = ud2.device_mac_id AND d2.cpu_id != ''
                JOIN mv_conv_counts cc ON cc.cpu_id = d2.cpu_id
                WHERE ud2.user_id = base.id OR ud2.user_email = base.email
            ) lc ON true
        """
    rows = query(sql, params + [per_page, offset])
    total_row = query(f"SELECT COUNT(*) n FROM users u {where}", params, one=True)
    total = total_row.get('n', 0) if isinstance(total_row, dict) else 0

    # Enrich with country from login IP
    ips = [r.get('last_login_ip') for r in rows]
    countries = get_countries(ips)
    for r in rows:
        geo = countries.get(r.get('last_login_ip') or '')
        r['last_country'] = geo['country'] if geo else ''
        r['last_country_code'] = geo['code'] if geo else ''

    return jsonify({'users': rows, 'total': total, 'page': page, 'per_page': per_page})

@app.route('/api/users/<int:uid>')
def user_detail(uid):
    # Basic info
    user = query("SELECT * FROM users WHERE id=%s", [uid], one=True)
    if not user:
        return jsonify({'error': 'not found'}), 404
    user['create_time'] = str(user.get('create_time',''))
    user['update_time'] = str(user.get('update_time',''))

    # Robots
    robots = query("""
        SELECT DISTINCT ON (d.device_mac_id)
               d.*, ud.upload_way, ud.create_time::text AS paired_at,
               m.summary AS profile, m.name AS profile_name, m.address, m.character,
               m.age, m.sex, m.profession, m.birthday, m.constellation,
               m.family_relations, m.friends, m.food_preference, m.game_preferences,
               m.music_preference, m.movie_preferences, m.pet, m.parental_information,
               COUNT(c.id) OVER (PARTITION BY d.device_mac_id) AS conv_count,
               MAX(c.chat_time) OVER (PARTITION BY d.device_mac_id)::text AS last_used,
               wl.city AS last_city, wl.ip AS last_ip
        FROM user_devices ud
        LEFT JOIN devices d ON d.device_mac_id = ud.device_mac_id
        LEFT JOIN chat_memories m ON m.sn = d.cpu_id
        LEFT JOIN conversations c ON SPLIT_PART(c.sn,'_',1) = d.cpu_id AND d.cpu_id IS NOT NULL AND d.cpu_id != ''
        LEFT JOIN LATERAL (
            SELECT city, ip FROM weather_logs WHERE chip_id = d.cpu_id
            ORDER BY create_time DESC LIMIT 1
        ) wl ON TRUE
        WHERE (ud.user_id=%s OR ud.user_email=%s)
    """, [uid, user.get('email','')])
    for r in robots:
        r['create_time'] = str(r.get('create_time',''))
        r['update_time'] = str(r.get('update_time',''))
        if isinstance(r.get('profile'), dict):
            pass  # already dict from jsonb

    # Recent conversations (100 latest)
    cpu_ids = [r.get('cpu_id','') for r in robots if r.get('cpu_id')]
    conversations = []
    if cpu_ids:
        placeholders = ','.join(['%s']*len(cpu_ids))
        placeholders = ','.join(['%s']*len(cpu_ids))
        conv_sql = f"""
            SELECT id, sn, public_ip, chat_time::text, question, answer, total_token, mode_number
            FROM conversations
            WHERE SPLIT_PART(sn,'_',1) IN ({placeholders})
            ORDER BY chat_time DESC LIMIT 100
        """
        conversations = query(conv_sql, cpu_ids)

    # Login history
    logins = query("""
        SELECT ip, login_type, user_source, create_time::text
        FROM login_logs WHERE email=%s
        ORDER BY create_time DESC LIMIT 50
    """, [user.get('email','')])

    # Geographic
    geo = []
    if cpu_ids:
        geo = query(f"""
            SELECT DISTINCT city, ip, create_time::text
            FROM weather_logs WHERE chip_id IN ({','.join(['%s']*len(cpu_ids))})
            ORDER BY create_time DESC LIMIT 20
        """, cpu_ids)

    return jsonify({
        'user': user,
        'robots': robots,
        'conversations': conversations,
        'logins': logins,
        'geographic': geo,
    })

# ── Conversations ─────────────────────────────────────────────────────────────

@app.route('/api/conversations')
def conversations():
    page     = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    search   = request.args.get('q', '').strip()
    sn       = request.args.get('sn', '').strip()
    ip       = request.args.get('ip', '').strip()
    offset   = (page-1)*per_page

    conditions = []
    params = []
    if search:
        conditions.append("(question ILIKE %s OR answer ILIKE %s)")
        params += [f'%{search}%', f'%{search}%']
    if sn:
        conditions.append("sn LIKE %s")
        params.append(f'{sn[:20]}%')
    if ip:
        conditions.append("public_ip=%s")
        params.append(ip)

    where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''
    sql = f"""
        SELECT c.id, c.sn, c.public_ip, c.chat_time::text, c.question, c.answer,
               c.total_token, c.mode_number,
               (SELECT d.device_origin_name FROM devices d
                WHERE d.cpu_id = SPLIT_PART(c.sn,'_',1) AND d.cpu_id != '' LIMIT 1) AS robot_name,
               (SELECT ud.user_email FROM devices d2
                JOIN user_devices ud ON ud.device_mac_id = d2.device_mac_id
                WHERE d2.cpu_id = SPLIT_PART(c.sn,'_',1) AND d2.cpu_id != '' LIMIT 1) AS owner,
               (SELECT u.id FROM devices d3
                JOIN user_devices ud2 ON ud2.device_mac_id = d3.device_mac_id
                JOIN users u ON u.email = ud2.user_email OR u.id = ud2.user_id
                WHERE d3.cpu_id = SPLIT_PART(c.sn,'_',1) AND d3.cpu_id != '' LIMIT 1) AS owner_id
        FROM conversations c
        {where}
        ORDER BY c.chat_time DESC
        LIMIT %s OFFSET %s
    """
    rows = query(sql, params + [per_page, offset])
    count = query(f"SELECT COUNT(*) n FROM conversations {where}", params, one=True)['n']
    return jsonify({'conversations': rows, 'total': count, 'page': page})

# ── Geographic ───────────────────────────────────────────────────────────────

@app.route('/api/geographic')
def geographic():
    # Precomputed view: refreshable via /api/refresh-cache
    rows = query("""
        SELECT ip, devices, queries, last_seen::text
        FROM mv_geo_stats ORDER BY devices DESC LIMIT 500
    """)
    ips = [r['ip'] for r in rows]
    geo_map = get_geo(ips, background=True)  # immediate response, background resolution
    agg = {}
    for r in rows:
        g = geo_map.get(r['ip'], {})
        city    = g.get('city', '') or ''
        country = g.get('country', '') or ''
        code    = g.get('code', '') or ''
        key = (city, country, code)
        if key not in agg:
            agg[key] = {'city': city, 'country': country, 'country_code': code,
                        'devices': 0, 'queries': 0, 'last_seen': ''}
        agg[key]['devices'] += r['devices']
        agg[key]['queries'] += r['queries']
        if r['last_seen'] and r['last_seen'] > agg[key]['last_seen']:
            agg[key]['last_seen'] = r['last_seen']
    cities = sorted(agg.values(), key=lambda x: -x['devices'])[:100]

    # KPI par pays depuis mv_robot_country (1 robot = 1 pays, pas de double-comptage)
    try:
        country_rows = query("""
            SELECT country, country_code, robots AS devices
            FROM mv_robot_country ORDER BY robots DESC
        """)
        total_robots = sum(r['devices'] for r in country_rows) or 1
        countries = [dict(r, pct=round(r['devices'] / total_robots * 100, 1)) for r in country_rows]
    except Exception:
        countries = []

    timeline = query("""
        SELECT DATE(chat_time) dt, COUNT(DISTINCT SPLIT_PART(sn,'_',1)) devices
        FROM conversations WHERE chat_time > NOW() - INTERVAL '30 days'
        GROUP BY dt ORDER BY dt
    """)
    return jsonify({'cities': cities, 'countries': countries, 'timeline': timeline})

# ── Robots ───────────────────────────────────────────────────────────────────

@app.route('/api/robots')
def robots():
    page     = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    search   = request.args.get('q', '').strip()
    offset   = (page-1)*per_page

    where = ''
    params = []
    if search:
        where = "WHERE d.device_mac_id ILIKE %s OR d.device_origin_name ILIKE %s OR ud.user_email ILIKE %s"
        params = [f'%{search}%']*3

    sql = f"""
        SELECT d.id, d.device_mac_id, d.device_type, d.device_origin_name, d.cpu_id,
               ud.user_email AS owner, u.id AS owner_id, u.nickname AS owner_nickname,
               u.avatar_url AS owner_avatar,
               m.address AS location, m.character AS profile_char,
               COUNT(c.id) AS conv_count,
               MAX(c.chat_time)::text AS last_used,
               wl.city AS last_city
        FROM devices d
        LEFT JOIN user_devices ud ON ud.device_mac_id = d.device_mac_id
        LEFT JOIN users u ON u.email = ud.user_email OR u.id = ud.user_id
        LEFT JOIN chat_memories m ON m.sn = d.cpu_id
        LEFT JOIN conversations c ON d.cpu_id IS NOT NULL AND d.cpu_id != '' AND SPLIT_PART(c.sn,'_',1) = d.cpu_id
        LEFT JOIN LATERAL (
            SELECT city FROM weather_logs WHERE chip_id=d.cpu_id ORDER BY create_time DESC LIMIT 1
        ) wl ON TRUE
        {where}
        GROUP BY d.id, d.device_mac_id, d.device_type, d.device_origin_name, d.cpu_id,
                 ud.user_email, u.id, u.nickname, u.avatar_url, m.address, m.character, wl.city
        ORDER BY conv_count DESC NULLS LAST
        LIMIT %s OFFSET %s
    """
    rows = query(sql, params + [per_page, offset])
    total = query(f"SELECT COUNT(DISTINCT d.id) n FROM devices d LEFT JOIN user_devices ud ON ud.device_mac_id=d.device_mac_id {where}", params, one=True)['n']
    return jsonify({'robots': rows, 'total': total, 'page': page})

# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/refresh-cache', methods=['POST'])
def refresh_cache():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_active_cpu_ids")
        cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_conv_counts")
        cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_users_with_convs")
        cur.execute("REFRESH MATERIALIZED VIEW mv_geo_stats")
        conn.close()
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)}), 500

@app.route('/health')
def health():
    try:
        conn = get_db(); conn.close()
        return jsonify({'status': 'ok', 'db': 'connected'})
    except Exception as e:
        return jsonify({'status': 'error', 'db': str(e)}), 500


# ══════════════════════════════════════════════════════════════════════════════
# SERVER ADMIN MODULES (SSH, MySQL, OSS)
# ══════════════════════════════════════════════════════════════════════════════

try:
    from server_admin import (
        get_file_tree, get_cron_jobs, get_processes, get_open_ports,
        get_device_faces, get_wake_up_audio, safe_mysql_query, ssh_cmd
    )
    SERVER_ADMIN_AVAILABLE = True
except ImportError:
    SERVER_ADMIN_AVAILABLE = False


# ── SSH File Manager ─────────────────────────────────────────────────────────

@app.route('/api/server/files')
def server_files():
    if not SERVER_ADMIN_AVAILABLE:
        return jsonify({'error': 'server_admin module not available'}), 503
    path = request.args.get('path', '/')
    result = get_file_tree(path)
    return jsonify(result)


@app.route('/api/server/cron')
def server_cron():
    if not SERVER_ADMIN_AVAILABLE:
        return jsonify({'error': 'server_admin module not available'}), 503
    return jsonify({'jobs': get_cron_jobs()})


@app.route('/api/server/processes')
def server_processes():
    if not SERVER_ADMIN_AVAILABLE:
        return jsonify({'error': 'server_admin module not available'}), 503
    return jsonify({'processes': get_processes()})


@app.route('/api/server/ports')
def server_ports():
    if not SERVER_ADMIN_AVAILABLE:
        return jsonify({'error': 'server_admin module not available'}), 503
    return jsonify({'ports': get_open_ports()})


@app.route('/api/server/info')
def server_info():
    if not SERVER_ADMIN_AVAILABLE:
        return jsonify({'error': 'server_admin module not available'}), 503
    info_raw = ssh_cmd('hostname && uname -r && uptime && df -h / && free -m | head -3')
    return jsonify({'info': info_raw})


# ── MySQL Browser ────────────────────────────────────────────────────────────

@app.route('/api/server/mysql', methods=['GET', 'POST'])
def server_mysql():
    if not SERVER_ADMIN_AVAILABLE:
        return jsonify({'error': 'server_admin module not available'}), 503
    sql = request.args.get('q') or (request.json or {}).get('query', '')
    if not sql:
        return jsonify({'error': 'No query provided'}), 400
    result = safe_mysql_query(sql)
    return jsonify(result)


@app.route('/api/server/mysql/databases')
def server_mysql_dbs():
    if not SERVER_ADMIN_AVAILABLE:
        return jsonify({'error': 'server_admin module not available'}), 503
    result = safe_mysql_query('SHOW DATABASES')
    return jsonify(result)


@app.route('/api/server/mysql/tables/<database>')
def server_mysql_tables(database):
    if not SERVER_ADMIN_AVAILABLE:
        return jsonify({'error': 'server_admin module not available'}), 503
    # Whitelist databases
    allowed = ['ai_config', 'chat_data', 'energize_user_data', 'factory_data',
               'time_log', 'weather_log', 'web_data', 'xunrui_web_data']
    if database not in allowed:
        return jsonify({'error': f'Database not in whitelist'}), 403
    result = safe_mysql_query(f'SHOW TABLES FROM {database}')
    return jsonify(result)


# ── OSS Device Faces ─────────────────────────────────────────────────────────

@app.route('/api/oss/faces')
def oss_faces():
    if not SERVER_ADMIN_AVAILABLE:
        return jsonify({'error': 'server_admin module not available'}), 503
    page = int(request.args.get('page', 1))
    result = get_device_faces(page=page)
    return jsonify(result)


# ── OSS Audio (wake_up) ─────────────────────────────────────────────────────

@app.route('/api/oss/audio')
def oss_audio():
    if not SERVER_ADMIN_AVAILABLE:
        return jsonify({'error': 'server_admin module not available'}), 503
    page = int(request.args.get('page', 1))
    date = request.args.get('date')
    result = get_wake_up_audio(page=page, date=date)
    return jsonify(result)


@app.route('/api/oss/audio/dates')
def oss_audio_dates():
    if not SERVER_ADMIN_AVAILABLE:
        return jsonify({'error': 'server_admin module not available'}), 503
    from server_admin import oss_list
    items, _ = oss_list('wake_up/', max_keys=200)
    dates = sorted(set(i['key'].split('/')[1] for i in items if '/' in i['key']))
    return jsonify({'dates': dates[-30:]})  # last 30 dates

if __name__ == '__main__':
    _ensure_ip_geo()
    app.run(host='0.0.0.0', port=8080, debug=False, threaded=True)
