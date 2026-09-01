#!/usr/bin/env python3
"""Flasheur Eilik COMPLET — réplique le protocole EnergizeLab (jump→boot→ressources(skip)→firmware→over-flag).
Usage: python3 eilik_flash_full.py <port> <update.bin> <firmware_info.json>
Formats validés depuis le code Python extrait de l'app + fonctions exécutées.
"""
import sys, time, struct, serial, glob, json, datetime

def usb_frame(payload):
    b=list(payload); L=len(b)+3
    f=[0xAA,0xAA,0xAA,L&0xFF,(L>>8)&0xFF]+b
    return bytes(f+[(~sum(f[3:]))&0xFF])
def sum_data(d): return (~sum(d))&0xFF

def read_frame(s, timeout=2.0):
    t0=time.time(); buf=bytearray()
    while time.time()-t0<timeout:
        n=s.in_waiting
        if n:
            buf.extend(s.read(n))
            i=buf.find(b'\xaa\xaa\xaa')
            if i>=0 and len(buf)>=i+5:
                ln=struct.unpack('<H',buf[i+3:i+5])[0]
                if len(buf)>=i+3+ln: return bytes(buf[i:i+3+ln])
        else:
            time.sleep(0.0005)
    return bytes(buf) if buf else b''

def file_time_bytes(ft):
    t=datetime.datetime.strptime(ft,'%Y/%m/%d %H:%M:%S')
    return [t.year&0xFF,(t.year>>8)&0xFF,t.month,t.day,t.hour,t.minute,t.second]

BLOCK=5120

def reopen_bootloader():
    for _ in range(50):
        time.sleep(0.2)
        ports=glob.glob('/dev/cu.usbmodem*')
        if ports: break
    time.sleep(1.0)
    return serial.Serial(glob.glob('/dev/cu.usbmodem*')[0],115200,timeout=0.15)

def flash(port_path, fw, manifest, progress=None):
    s=serial.Serial(port_path,115200,timeout=0.15); time.sleep(0.3)
    def send(payload):
        s.reset_input_buffer(); s.write(usb_frame(payload)); s.flush()
    # 1) JUMP (cmd 0x02)
    s.write(usb_frame([0x02,0x00]+list(struct.pack('<i',9)))); s.flush(); time.sleep(0.5); s.close()
    print("[1/5] jump → bootloader…"); s=reopen_bootloader(); time.sleep(0.3)
    # 2) get_boot_version
    send([1]); r=read_frame(s,3.0)
    boot_fw = r[26] if len(r)>26 else 3
    print(f"[2/5] boot version resp={r.hex()[:40]} → boot_fw={boot_fw}")
    # 3) RESSOURCES (skip)
    res=manifest['resource']; total=len(res); nskip=0; nupd=0; updates=[]
    print(f"[3/5] {total} ressources (skip attendu)…")
    for idx,(name,meta) in enumerate(res.items()):
        info=file_time_bytes(meta['file_time'])+list(struct.pack('<I',meta['file_size']))+list(name.lstrip('/').encode('ascii'))
        send([3,1]+info)
        r=read_frame(s,2.0)
        if not r:
            # 1 retry
            send([3,1]+info); r=read_frame(s,2.0)
            if not r:
                s.close(); return f"ressource '{name}' (#{idx}): pas de réponse"
        # skip = frame[7]==1 ; update = autre
        if len(r)>7 and r[7]==1: nskip+=1
        else:
            nupd+=1; updates.append(name)
        if progress and idx%200==0: progress('res', idx, total)
    print(f"[3/5] ressources OK : {nskip} skip, {nupd} à mettre à jour")
    if nupd>0:
        print(f"[!] {nupd} ressources ignorées (SD/manifeste désynchro): {updates} — on tente quand même firmware+finalize")
    # 4) FIRMWARE streamé comme ressource 'update.bin' (type 3) — protocole EXACT de l'app :
    #    resource_update() : file_write_info [3,1] → chunks [3,2]+offset+data(256o) → file_write_config(3)=[3,3]
    #    BLOCK_LENGTH=256 (valeur réelle du module ; pour EL check_and_wait=True donc pas d'ACK par chunk)
    FWBLK=256
    print(f"[4/6] firmware 'update.bin' {len(fw)}o via resource_update, chunks de {FWBLK}o…")
    now=datetime.datetime.now()
    ft=[now.year&0xFF,(now.year>>8)&0xFF,now.month,now.day,now.hour,now.minute,now.second]
    send([3,1]+ft+list(struct.pack('<I',len(fw)))+list(b'update.bin'))
    r=read_frame(s,3.0); print(f"      info resp={r.hex()} (attendu: update, pas skip)")
    if not r: s.close(); return "firmware info: pas d'ACK"
    # streaming 256o : send_length = offset cumulé ; chunk = fw[send_length-blk:send_length]
    # pas de reset_input ni de lecture par chunk (EL n'ACK pas ; write() bloque via flow-control USB CDC)
    send_length=0
    n_full=len(fw)//FWBLK; last=len(fw)%FWBLK
    for i in range(n_full):
        send_length+=FWBLK
        s.write(usb_frame([3,2]+list(struct.pack('<i',send_length))+list(fw[send_length-FWBLK:send_length]))); s.flush()
        if progress and i%40==0: progress('fw',send_length,len(fw))
    if last:
        send_length+=last
        s.write(usb_frame([3,2]+list(struct.pack('<i',send_length))+list(fw[send_length-last:send_length]))); s.flush()
    if progress: progress('fw',len(fw),len(fw))
    print()
    def fin_cmd(name, payload, tries=25, wait=0.4):
        """écrit payload en boucle jusqu'à réponse (comme file_write_config de l'app, retry ~5s)."""
        for i in range(tries):
            try:
                s.reset_input_buffer(); s.write(usb_frame(payload)); s.flush()
                r=read_frame(s,wait)
                if r and len(r)>=8: return r
            except (serial.SerialException,OSError):
                return 'PORTGONE'
        return b''
    # finalize ressource update.bin : file_write_config(3) = [3,3]  → "finish" sur l'écran
    r33=fin_cmd('[3,3]',[3,3])
    print(f"[fin] file_write_config(3) [3,3] = {r33 if isinstance(r33,str) else (r33.hex() if r33 else 'AUCUNE')}")
    # 5) COMMIT firmware : inst_data(4,0) = [4,0] → cd[6]==1 (write firmware success)
    r40=fin_cmd('[4,0]',[4,0])
    print(f"[5/6] commit [4,0] = {r40 if isinstance(r40,str) else (r40.hex() if r40 else 'AUCUNE')}")
    # 6) OVER-FLAG : file_write_config(4) = [3,4] = res-end-flag → update complete + REBOOT
    r34=fin_cmd('[3,4]',[3,4])
    print(f"[6/6] over-flag [3,4] = {r34 if isinstance(r34,str) else (r34.hex() if r34 else 'AUCUNE')}")
    # le robot reboote après [3,4] : le port tombe puis ré-énumère
    try: s.close()
    except: pass
    finish_ok = isinstance(r33,(bytes,)) and len(r33)>=8   # [3,3] a répondu = "finish"
    commit_ok = isinstance(r40,(bytes,)) and len(r40)>=8   # [4,0] write firmware success
    reboot = (r34=='PORTGONE')                              # [3,4] → port tombé = reboot
    if finish_ok and commit_ok and reboot:
        return "OK — firmware flashé, finish + commit OK, robot en reboot ✅"
    return (f"INCOMPLET: finish([3,3])={'ok' if finish_ok else (r33 if isinstance(r33,str) else 'AUCUNE')} "
            f"commit([4,0])={'ok' if commit_ok else 'AUCUNE'} "
            f"reboot([3,4])={'ok' if reboot else (r34 if isinstance(r34,str) else 'PAS DE REBOOT')}")

if __name__=='__main__':
    port,fwfile,manifestfile=sys.argv[1],sys.argv[2],sys.argv[3]
    fw=open(fwfile,'rb').read()
    manifest=json.load(open(manifestfile))
    print(f"Flash COMPLET {fwfile} ({len(fw)}o) + {len(manifest['resource'])} ressources sur {port}")
    def prog(ph,cur,tot): print(f"\r  [{ph}] {cur}/{tot}",end='',flush=True)
    print("RÉSULTAT:", flash(port,fw,manifest,prog))
