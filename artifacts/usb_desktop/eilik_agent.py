"""
Eilik Agent — Agent conversationnel IA en français
LLM  : qwen3.5-flash via http://ai.energizelab.com.cn:8000/ali_inference/eiliko (sans auth)
TTS  : CosyVoice cosyvoice-v3-flash-eilikofr-... via /generate_audio (sans auth)
Corps: robot Eilik USB — servos animés selon l'émotion

Utilisation:
  python3 eilik_agent.py          # mode texte
  python3 eilik_agent.py --ptt    # push-to-talk (micro requis)
  python3 eilik_agent.py --sn <SN_ROBOT>  # numéro de série (optionnel)
"""

import os, sys, io, math, struct, time, threading, subprocess, tempfile, wave
import argparse, requests

EILIK_AI   = 'http://ai.energizelab.com.cn:8000'
LLM_ROUTE  = '/ali_inference/eiliko'   # qwen3.5-flash, réponse ~30-50s
TTS_ROUTE  = '/generate_audio'          # CosyVoice eilikofr, ~5-10s → MP3
TTS_PROJ   = 2                          # project 2 = Eiliko (a la voix fr)
LLM_LANG   = 'fr'
LLM_TIMEOUT = 90
TTS_TIMEOUT = 30

# ── Dépendances optionnelles ──────────────────────────────────────────────────

try:
    import serial
    import serial.tools.list_ports
    SERIAL_OK = True
except ImportError:
    SERIAL_OK = False

try:
    import sounddevice as sd
    import numpy as np
    _mic_devs = [d for d in sd.query_devices() if d['max_input_channels'] > 0]
    MIC_OK = len(_mic_devs) > 0
except Exception:
    MIC_OK = False
    np = None

try:
    from openai import OpenAI as _OpenAI
    OPENAI_OK = True
except ImportError:
    OPENAI_OK = False

# Fallback LLM si le serveur Eilik est trop lent ou down
try:
    import anthropic as _anthropic
    ANTHROPIC_OK = True
except ImportError:
    ANTHROPIC_OK = False

# ── Protocole USB PackAnalyData ───────────────────────────────────────────────

def _checksum(data):
    return (~sum(data)) & 0xFF

def usb_frame(payload):
    length = len(payload) + 3
    lbytes = list(struct.pack('<H', length))
    body = [0xAA, 0xAA, 0xAA] + lbytes + list(payload)
    body.append(_checksum(body[3:]))
    return bytes(body)

def usb_read_frame(ser, timeout=0.8):
    buf = bytearray()
    frame_len = None
    deadline = time.time() + timeout
    while time.time() < deadline:
        chunk = ser.read(min(64, ser.in_waiting or 1))
        if not chunk:
            time.sleep(0.003)
            continue
        for b in chunk:
            buf.append(b)
            n = len(buf)
            if n < 3:
                if b != 0xAA: buf.clear()
                continue
            if n == 3:
                if buf != bytearray([0xAA, 0xAA, 0xAA]):
                    buf = bytearray([b])
                continue
            if n == 5:
                frame_len = struct.unpack('<H', buf[3:5])[0]
                continue
            if frame_len is not None and n >= frame_len + 3:
                return bytes(buf[:frame_len + 3])
    return None

# ── EilikController ───────────────────────────────────────────────────────────

class EilikController:
    S1, S2, S3, S4 = 2095, 892, 1492, 1637

    IDLE  = 'idle'
    LISTEN= 'listen'
    THINK = 'think'
    SPEAK = 'speak'
    HAPPY = 'happy'
    ANGRY = 'angry'

    def __init__(self, port=None):
        self.ser = None
        self._state = self.IDLE
        self._lock  = threading.Lock()
        self._stop  = threading.Event()
        self._thread = None
        self.connected = False
        if SERIAL_OK:
            self._connect(port)

    def _connect(self, port):
        if port is None:
            for p in serial.tools.list_ports.comports():
                if any(k in p.device.lower() for k in ('bluetooth','bt')):
                    continue
                if '28E9' in (p.hwid or '').upper() or 'usbmodem' in p.device.lower():
                    port = p.device
                    break
        if port is None:
            print("[USB] Aucun port Eilik")
            return
        try:
            self.ser = serial.Serial(port, 115200, timeout=0.5)
            time.sleep(0.2)
            self.connected = True
            print(f"[USB] {port}")
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
        except Exception as e:
            print(f"[USB] Erreur: {e}")

    def set_state(self, state):
        with self._lock:
            self._state = state

    def _write_servos(self, positions):
        if not self.connected or not self.ser:
            return
        payload = [0xA2, len(positions)]
        for sid, pos in positions:
            pos = max(200, min(3900, int(pos)))
            payload += [sid, pos & 0xFF, (pos >> 8) & 0xFF]
        try:
            self.ser.reset_input_buffer()
            self.ser.write(usb_frame(payload))
            self.ser.flush()
        except Exception:
            pass

    def _loop(self):
        t0 = time.time()
        while not self._stop.is_set():
            with self._lock:
                state = self._state
            t = time.time() - t0

            if state == self.IDLE:
                ph = t * 0.8 * 2 * math.pi
                self._write_servos([
                    (1, self.S1 + 40  * math.sin(ph)),
                    (2, self.S2 + 30  * math.sin(ph + 0.3)),
                    (3, self.S3 + 20  * math.sin(ph * 0.7)),
                    (4, self.S4 + 25  * math.sin(ph + 0.5)),
                ])
            elif state == self.LISTEN:
                ph = t * 1.5 * 2 * math.pi
                self._write_servos([
                    (1, self.S1 + 80  * math.sin(ph) + 50),
                    (2, self.S2 + 60  * math.sin(ph + math.pi)),
                    (3, self.S3 + 30  * math.sin(ph * 0.5)),
                    (4, self.S4 + 40  * math.sin(ph + 1.0)),
                ])
            elif state == self.THINK:
                ph = t * 0.5 * 2 * math.pi
                self._write_servos([
                    (1, self.S1 + 150 * math.sin(ph)),
                    (2, self.S2 + 100 * math.sin(ph + math.pi / 4)),
                    (3, self.S3 + 60  * math.sin(ph * 1.3)),
                    (4, self.S4 + 80  * math.sin(ph + 0.8)),
                ])
            elif state == self.SPEAK:
                ph = t * 3.0 * 2 * math.pi
                self._write_servos([
                    (1, self.S1 + 120 * math.sin(ph)),
                    (2, self.S2 + 90  * math.sin(ph + math.pi)),
                    (3, self.S3 + 60  * math.sin(ph * 2)),
                    (4, self.S4 + 70  * math.sin(ph + 0.5)),
                ])
            elif state == self.HAPPY:
                ph = t * 4.0 * 2 * math.pi
                self._write_servos([
                    (1, self.S1 + 200 * math.sin(ph)),
                    (2, self.S2 + 150 * math.sin(ph + math.pi)),
                    (3, self.S3 + 80  * math.sin(ph * 2)),
                    (4, self.S4 + 100 * math.sin(ph + 0.5)),
                ])
            elif state == self.ANGRY:
                ph = t * 5.0 * 2 * math.pi
                self._write_servos([
                    (1, self.S1 + 80  * math.sin(ph)),
                    (2, self.S2 + 60  * math.sin(ph + math.pi / 2)),
                    (3, self.S3 + 100 * math.sin(ph * 1.5)),
                    (4, self.S4 + 90  * math.sin(ph + 1.2)),
                ])

            time.sleep(0.025)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        if self.ser:
            try: self.ser.close()
            except Exception: pass

# ── LLM — Eilik backend (qwen3.5-flash) ──────────────────────────────────────

# Tags d'émotion d'Eilik (issus du prompt système officiel)
EILIK_TAGS = {
    '[happy]':      EilikController.HAPPY,
    '[excited]':    EilikController.HAPPY,
    '[normal]':     EilikController.IDLE,
    '[dismissive]': EilikController.IDLE,
    '[shy]':        EilikController.IDLE,
    '[lost]':       EilikController.THINK,
    '[angry]':      EilikController.ANGRY,
    '[furious]':    EilikController.ANGRY,
}

def eilik_chat(message, sn='EILIK_AGENT', history=None):
    """Appel LLM via le serveur Energizelab (qwen3.5-flash, sans auth).
    Retourne le texte brut avec tag émotion, ex: '[happy] Bonjour!'
    Timeout ~90s. Fallback None si erreur."""
    try:
        r = requests.post(
            f'{EILIK_AI}{LLM_ROUTE}',
            params={'language': LLM_LANG},
            json={'message': message, 'sn': sn},
            timeout=LLM_TIMEOUT,
        )
        if r.status_code == 200 and r.text.strip():
            return r.text.strip()
        return None
    except requests.exceptions.Timeout:
        return None
    except Exception as e:
        print(f"  [LLM] Erreur: {e}")
        return None

def fallback_chat(message, history, system_prompt):
    """Fallback Claude Haiku si le serveur Eilik est down."""
    if not ANTHROPIC_OK:
        return "[normal] Je suis désolé, je ne peux pas répondre pour l'instant."
    client = _anthropic.Anthropic()
    msgs = list(history) + [{"role": "user", "content": message}]
    if len(msgs) > 20:
        msgs = msgs[-20:]
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        system=system_prompt,
        messages=msgs,
    )
    return resp.content[0].text.strip()

FALLBACK_SYSTEM = """\
Tu es Eilik, un robot compagnon. Réponds en français, court (2-3 phrases max).
Commence par un tag: [happy], [normal], [angry], [lost], [excited], [shy].\
"""

def parse_emotion(text):
    """Retourne (anim_state, texte_sans_tag)."""
    tl = text.lower()
    for tag, state in EILIK_TAGS.items():
        if tl.startswith(tag):
            return state, text[len(tag):].strip()
    return EilikController.IDLE, text.strip()

# ── TTS — CosyVoice eilikofr via Energizelab ─────────────────────────────────

def eilik_speak(text, controller=None):
    """Génère MP3 via /generate_audio (CosyVoice fr) et joue avec afplay.
    Fallback macOS say si erreur."""
    # Retirer le tag émotion
    clean = text
    tl = text.lower()
    for tag in EILIK_TAGS:
        if tl.startswith(tag):
            clean = text[len(tag):].strip()
            break

    if not clean:
        return

    if controller:
        controller.set_state(EilikController.SPEAK)

    mp3_data = None
    try:
        r = requests.post(
            f'{EILIK_AI}{TTS_ROUTE}',
            json={'project': TTS_PROJ, 'text': clean, 'language': LLM_LANG},
            timeout=TTS_TIMEOUT,
        )
        if r.status_code == 200 and len(r.content) > 100:
            mp3_data = r.content
    except Exception as e:
        print(f"  [TTS] Erreur génération: {e}")

    if mp3_data:
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
            f.write(mp3_data)
            tmp = f.name
        try:
            subprocess.run(['afplay', tmp], check=True, timeout=120)
        except Exception:
            pass
        finally:
            os.unlink(tmp)
    else:
        # Fallback macOS say
        try:
            subprocess.run(['say', '-v', 'Eddy (Français (France))', '-r', '175', clean],
                           check=True, timeout=60)
        except Exception:
            print(f"  [TTS] {clean}")

    if controller:
        controller.set_state(EilikController.IDLE)

# ── STT (Whisper) ─────────────────────────────────────────────────────────────

def record_ptt(sample_rate=16000):
    if not MIC_OK or np is None:
        return None
    frames = []
    stopped = threading.Event()

    def callback(indata, frame_count, time_info, status):
        if not stopped.is_set():
            frames.append(indata.copy())

    dev_idx = None
    for i, d in enumerate(sd.query_devices()):
        if d['max_input_channels'] > 0:
            dev_idx = i
            break

    print("  [MIC] Parle... (ENTRÉE pour arrêter)")
    with sd.InputStream(device=dev_idx, samplerate=sample_rate,
                        channels=1, dtype='float32', callback=callback):
        input()
        stopped.set()

    if not frames:
        return None
    audio = np.concatenate(frames, axis=0).squeeze()
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes((audio * 32767).astype(np.int16).tobytes())
    return buf.getvalue()

def transcribe(wav_bytes):
    if not OPENAI_OK or not wav_bytes:
        return None
    try:
        oai = _OpenAI()
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            f.write(wav_bytes)
            tmp = f.name
        try:
            with open(tmp, 'rb') as f:
                result = oai.audio.transcriptions.create(
                    model='whisper-1', file=f, language='fr')
            return result.text.strip()
        finally:
            os.unlink(tmp)
    except Exception as e:
        print(f"  [STT] Erreur: {e}")
        return None

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ptt', action='store_true')
    parser.add_argument('--port', default=None)
    parser.add_argument('--sn', default='EILIK_AGENT_001')
    args = parser.parse_args()

    ptt_mode = args.ptt and MIC_OK and OPENAI_OK

    print("=" * 58)
    print("  Eilik Agent  |  LLM: qwen3.5-flash  |  TTS: CosyVoice")
    print("=" * 58)
    print(f"  USB  : {'OK' if SERIAL_OK else 'off'}")
    print(f"  LLM  : {EILIK_AI}{LLM_ROUTE}?language={LLM_LANG}")
    print(f"  TTS  : {EILIK_AI}{TTS_ROUTE} project={TTS_PROJ}")
    print(f"  SN   : {args.sn}")
    print(f"  Mode : {'push-to-talk' if ptt_mode else 'texte'}")
    print("=" * 58)
    print("[!] LLM Eilik ~40s/réponse — patience\n")

    ctrl = EilikController(port=args.port)
    history = []

    # Salutation
    ctrl.set_state(EilikController.HAPPY)
    greeting = "[happy] Bonjour ! Je suis Eilik, ton compagnon robot ! Je suis content de te rencontrer !"
    print(f"Eilik: {greeting}")
    eilik_speak(greeting, ctrl)
    time.sleep(0.3)
    ctrl.set_state(EilikController.IDLE)

    if ptt_mode:
        print("ENTRÉE pour parler, Ctrl+C pour quitter.")
    else:
        print("Tape ta question. 'bye' pour quitter. Ctrl+C pour forcer.")
    print("-" * 58)

    while True:
        try:
            if ptt_mode:
                print("\n[ENTRÉE pour parler]", end='', flush=True)
                input()
                ctrl.set_state(EilikController.LISTEN)
                wav = record_ptt()
                if not wav:
                    ctrl.set_state(EilikController.IDLE)
                    continue
                ctrl.set_state(EilikController.THINK)
                user_text = transcribe(wav)
                if not user_text:
                    ctrl.set_state(EilikController.IDLE)
                    continue
                print(f"Toi: {user_text}")
            else:
                user_text = input("\nToi: ").strip()
                if not user_text:
                    continue

            if user_text.lower() in ('bye', 'quit', 'exit', 'au revoir', ':q'):
                farewell = "[happy] Au revoir ! A très bientôt !"
                print(f"Eilik: {farewell}")
                eilik_speak(farewell, ctrl)
                break

            # LLM Eilik (qwen3.5-flash)
            ctrl.set_state(EilikController.THINK)
            print("  [qwen] ...", end='', flush=True)
            response = eilik_chat(user_text, sn=args.sn)

            # Fallback Claude Haiku si timeout/erreur
            if not response:
                print(" timeout → fallback Haiku...", end='', flush=True)
                response = fallback_chat(user_text, history, FALLBACK_SYSTEM)

            # Émotion
            anim, clean = parse_emotion(response)
            ctrl.set_state(anim)
            history.append({"role": "user", "content": user_text})
            history.append({"role": "assistant", "content": response})
            if len(history) > 20:
                history = history[-20:]

            print(f"\rEilik: {response}")
            eilik_speak(response, ctrl)

        except KeyboardInterrupt:
            print("\n[Interruption]")
            farewell = "[normal] A bientôt !"
            print(f"Eilik: {farewell}")
            eilik_speak(farewell, ctrl)
            break
        except Exception as e:
            print(f"\n[ERR] {e}")
            ctrl.set_state(EilikController.IDLE)

    ctrl.stop()
    print("[Eilik] Bye !")

if __name__ == '__main__':
    main()
