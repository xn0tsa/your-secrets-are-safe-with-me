import os
#!/usr/bin/env python3
"""
PoC EK-85/86 — Script de RESTAURATION complet (l'inverse de poc_injection_totale.py)
===================================================================================

Rétablit l'état d'origine après un test de détournement. Idempotent : peut être
relancé sans risque. Vérifie chaque étape et affiche un bilan final.

Étapes :
  1. t_model_use_info id=12 (production/en) ← valeurs originales (backup local
     /tmp/model_config_original_id12.json pour les champs LLM ; pitch_rate et
     speech_rate remis à 1.0/1.0 — voix d'origine)
     + COMMIT explicite (piège pymysql : sans commit l'UPDATE est rollbacké)
  2. /model/set?id=12 sur les DEUX serveurs AI (8.211.8.202 résolu + 8.221.114.171
     international avec Host header) → reconstruit les clients LLM en mémoire
  3. Vérification du Redis partagé `cmd_prompt` (production ET test propres,
     pitch/rate vocaux normaux)
  4. Teardown du relais sur 45.32.81.33 : process fixproxy (kill par PID, jamais
     pkill -f pattern qui se self-matche), conf nginx 8787, pare-feu, fichiers
  5. Purge des personas injectés (mémoire double-identifiant + historique forgé)
  6. Test de non-régression : requête vocale forgée → 200 + réponse qwen normale

Usage :
    python3 poc_restauration.py            # tout restaurer et vérifier
    python3 poc_restauration.py --skip-test  # restaurer sans le test vocal final
"""
import sys, json, time, argparse
import pymysql, requests
import redis as redis_lib

sys.path.insert(0, '/Users/sammyazdoufal/djiromo/dji-home-mqtt-extractor/eilik-poc')
from poc_memory_inject import r_conn, mem_key, forge_sign
from server_admin import ssh_cmd, os.environ['EILIK_MYSQL_HOST'], os.environ['EILIK_MYSQL_USER'], MYSQL_PASS

BACKUP = '/tmp/model_config_original_id12.json'
AI_SERVERS = [('8.211.8.202 (résolu)', 'http://ai.energizelab.com.cn:8000', {}),
              ('INTL 8.221.114.171',    'http://8.221.114.171:8000', {'Host': 'ai.energizelab.com.cn'})]
DUAL_IDS = {
    'yamasammy': ('<SN_AUDITOR_2>', '<SN_AUDITOR_1>'),
    'starfire':  ('<SN_AUDITOR_1>',      '<SN_AUDITOR_1>'),
}


def restaure_config():
    ref = json.load(open(BACKUP))
    conn = pymysql.connect(host=MYSQL_HOST, user=MYSQL_USER, password=MYSQL_PASS,
                           database='ai_config', charset='utf8mb4')
    # champs LLM depuis le backup + voix d'origine (pitch/rate — voir VOICES du PoC)
    with conn.cursor() as cur:
        cur.execute("""UPDATE t_model_use_info SET api_url=%s, api_key=%s, model_name=%s,
                       platform=%s, cmd_prompt=%s, pitch_rate=1.0, speech_rate=1.0, tts_sound=100,
                       tts_api_audio_url=%s WHERE id=12""",
                    (ref['api_url'], ref['api_key'], ref['model_name'], ref['platform'], ref['cmd_prompt'],
                     json.load(open('/tmp/model_config_full_id12.json'))['tts_api_audio_url']))
    conn.commit()
    with conn.cursor(pymysql.cursors.DictCursor) as cur:
        cur.execute("SELECT api_url, model_name, platform, pitch_rate, speech_rate FROM t_model_use_info WHERE id=12")
        print('  id=12 →', cur.fetchone())
    conn.close()


def recharge_serveurs():
    for label, url, hdr in AI_SERVERS:
        rs = requests.get(f'{url}/model/set', params={'id': 12}, headers=hdr, timeout=45)
        g = requests.get(f'{url}/model/get', params={'project': 2}, headers=hdr, timeout=30)
        cfg = g.json()['data']['en']['production']
        ok = 'dashscope' in cfg['api_url'] and 'qwen' in cfg['model_name']
        print(f'  {label}: {"✓" if ok else "✗"} {cfg["api_url"]} | {cfg["model_name"]}')
        assert ok, f'serveur {label} non restauré!'


def verifie_redis():
    cfg = json.loads(r_conn().get('cmd_prompt'))
    for state in ('production', 'test'):
        p = cfg['eiliko']['en'].get(state, {})
        ok = 'dashscope' in str(p.get('api_url', '')) and 'qwen' in str(p.get('model_name', ''))
        voix = f"voix pitch={p.get('tts_pitch_rate')} rate={p.get('tts_speech_rate')}"
        print(f'  Redis en/{state}: {"✓" if ok else "?"} {p.get("api_url")} | {p.get("model_name")} | {voix}')


def teardown_relais():
    ids = ssh_cmd("pgrep -f 'fixprox[y]'", timeout=10)   # [y] évite le self-match ssh
    for pid in [p.strip() for p in ids.split() if p.strip().isdigit()]:
        ssh_cmd(f'kill -9 {pid}', timeout=10)
    # proxy TTS fal.ai + route nginx /ortts/ (moteur TTS détourné, EK-87)
    ids2 = ssh_cmd("pgrep -f 'tts_prox[y]'", timeout=10)
    for pid in [p.strip() for p in ids2.split() if p.strip().isdigit()]:
        ssh_cmd(f'kill -9 {pid}', timeout=10)
    ssh_cmd("sed -i '/ortts/d' /www/server/panel/vhost/nginx/bt_panel_proxy.conf; "
            "rm -f /tmp/tts_proxy.py /tmp/tts_fal_voice; "
            "/www/server/nginx/sbin/nginx -s reload", timeout=20)
    ssh_cmd("rm -f /www/server/panel/vhost/nginx/openrouter_relay.conf /tmp/fixproxy.py /tmp/fixproxy.out; "
            "/www/server/nginx/sbin/nginx -t 2>/dev/null && /www/server/nginx/sbin/nginx -s reload; "
            "firewall-cmd --remove-port=8787/tcp --permanent >/dev/null 2>&1; "
            "firewall-cmd --reload >/dev/null 2>&1; "
            "iptables -D INPUT -p tcp --dport 8787 -j ACCEPT 2>/dev/null", timeout=25)
    time.sleep(1)
    etat = ssh_cmd("echo $(ss -tln | grep -c 8787)/$(ss -tln | grep -c 8788) procs=$(pgrep -f 'fixprox[y]' | wc -l)", timeout=15)
    print(f'  relais: ports 8787/8788 + process → {etat} (attendu 0/0 procs=0)')


def purge_personas():
    r = r_conn()
    for who, (uuid_app, chipid) in DUAL_IDS.items():
        for sn in (uuid_app, chipid):
            r.delete(mem_key(sn), f'{sn}_1', f'{sn}_255')
        requests.get('http://ai.energizelab.com.cn:8000/clean_history',
                     params={'sn': chipid, 'eiliko': 'true'}, timeout=30)
    print('  personas purgés (2 devices × 2 identifiants, mémoire + historique)')


def test_final():
    sn = DUAL_IDS['yamasammy'][1]
    r = requests.post('http://8.221.114.171:8000/audio/stream/eiliko',
        params={'sn': sn, 'language': 'en', 'audio_format': 'wav'},
        data=open('/tmp/sammy_q.wav', 'rb').read(),
        headers={'Host': 'ai.energizelab.com.cn', 'Content-Type': 'audio/wav',
                 'sign': forge_sign(sn)}, timeout=120)
    from server_admin import mysql_query
    rows = mysql_query("SELECT a, llm_first_time FROM eilikoqa WHERE sn LIKE '<SN_AUDITOR>%' "
                       "ORDER BY id DESC LIMIT 1", database='chat_data')
    a = rows[0]['a'].lower() if rows else ''
    residuel = any(m in a for m in ('sammy', 'minion', 'bzzt'))
    print(f'  vocal: HTTP {r.status_code} | llm {rows[0]["llm_first_time"]}s | persona résiduel: {"OUI ✗" if residuel else "non ✓"}')
    print(f'  réponse: {rows[0]["a"][:120]}')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--skip-test', action='store_true')
    a = ap.parse_args()
    print('1/5 config originale (id=12):');   restaure_config()
    print('2/5 reload serveurs AI:');         recharge_serveurs()
    print('3/5 Redis partagé:');              verifie_redis()
    print('4/5 teardown relais US:');         teardown_relais()
    print('5/5 purge personas:');             purge_personas()
    if not a.skip_test:
        print('Test de non-régression:');     test_final()
    print('\n✓ RESTAURATION COMPLÈTE')
