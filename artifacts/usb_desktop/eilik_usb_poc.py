"""
Eilik Robot USB Serial PoC — Protocole extrait de EnergizeLab.app (PyInstaller)

Protocole extrait de FirmwareBase/PackAnalyData.pyc :

  Frame TX/RX: [0xAA][0xAA][0xAA][len_lo][len_hi][inst...][data...][checksum]
    len = len(inst+data) + 3
    checksum = ~sum([len_lo, len_hi, inst..., data...]) & 0xFF

  Commandes (PackAnalyData docstring + disassembly) :
    0x01 — Ping      → répons: inst + chip_id(12) + model(4) + fw(4) + boot(4) + reserved(10)
    0x20 — Read all  → répons: 2 Ko de paramètres
    0x21 — Read one  → répons: valeur paramètre
    0x31 — Write one
    0x41 — Re-init SD card
    0x42 — Format SD card
    0xA1 — Read servo angles
    0xA2 — Write servo angles  [count, id, pos_lo, pos_hi, ...]
    0xA3 — Read display content
    0xA4 — Write display content (1024 bytes)
    0xA5 — Read run number
    0xA6 — Write run number
    0x04 — Flash depuis SD
    0x05/0x01-0x03 — Flash direct via USB

  RobotInfo.get_json_data keys: boot_firmware, firmware_number, mode_number,
                                 chip_id_1, chip_id_2, chip_id_3, log, data
"""

import struct
import sys
import time
import serial
import serial.tools.list_ports

USB_PORT  = '/dev/cu.usbmodem31101'
BAUD_RATE = 115200   # CDC ACM — baud ignoré par le hardware, mais requis par pyserial
TIMEOUT   = 2.0

# ─── Protocole PackAnalyData ──────────────────────────────────────────────────

def _checksum(data: list[int]) -> int:
    return (~sum(data)) & 0xFF

def frame(payload: list[int]) -> bytes:
    """Construit une frame complète: header + length + payload + checksum."""
    length = len(payload) + 3
    hdr    = [0xAA, 0xAA, 0xAA]
    lbytes = list(struct.pack('<H', length))
    body   = hdr + lbytes + payload
    body.append(_checksum(body[3:]))
    return bytes(body)

def cmd_ping()           -> bytes: return frame([0x01])
def cmd_read_all()       -> bytes: return frame([0x20])
def cmd_read_one(addr)   -> bytes: return frame([0x21, addr])
def cmd_read_servos()    -> bytes: return frame([0xA1])
def cmd_read_display()   -> bytes: return frame([0xA3])
def cmd_read_run_num()   -> bytes: return frame([0xA5])
def cmd_reinit_sd()      -> bytes: return frame([0x41])

def cmd_write_servo(servos: list[tuple[int,int,int]]) -> bytes:
    """servos = [(id, pos_lo, pos_hi), ...]"""
    data = [0xA2, len(servos)]
    for sid, lo, hi in servos:
        data += [sid, lo, hi]
    return frame(data)

def cmd_write_run_num(n: int) -> bytes:
    return frame([0xA6] + list(struct.pack('<I', n)))

# ─── Parseur de réponse ───────────────────────────────────────────────────────

def read_frame(ser: serial.Serial, timeout: float = 3.0) -> bytes | None:
    """Lit une frame complète selon la machine d'état de check_data()."""
    buf        = bytearray()
    frame_len  = None
    deadline   = time.time() + timeout

    while time.time() < deadline:
        chunk = ser.read(min(64, ser.in_waiting or 1))
        if not chunk:
            time.sleep(0.005)
            continue

        for b in chunk:
            buf.append(b)
            n = len(buf)

            # Éliminer les bytes avant le header 0xAA 0xAA 0xAA
            if n < 3:
                if b != 0xAA:
                    buf.clear()
                continue

            if n == 3:
                if buf != bytearray([0xAA, 0xAA, 0xAA]):
                    buf = bytearray([b])  # glissement
                continue

            if n == 5:
                frame_len = struct.unpack('<H', buf[3:5])[0]
                continue

            if frame_len is not None:
                expected = frame_len + 3  # header(3) + length-field-content
                if n == expected:
                    return bytes(buf)
                if n > expected:
                    buf.clear()
                    frame_len = None

    return None

def parse_ping(resp: bytes) -> dict:
    """Parse la réponse au Ping (0x01). Offset 5 = début payload."""
    if not resp or len(resp) < 10:
        return {}
    payload = resp[5:-1]  # strip header+length+checksum
    if not payload or payload[0] != 0x01:
        return {}
    d = payload[1:]  # sauter l'octet instruction
    out = {}
    if len(d) >= 12:
        out['chip_id'] = d[0:12].hex()
    if len(d) >= 16:
        out['model_number'] = struct.unpack('<I', d[12:16])[0]
    if len(d) >= 20:
        out['firmware_version'] = struct.unpack('<I', d[16:20])[0]
    if len(d) >= 24:
        out['boot_version'] = struct.unpack('<I', d[20:24])[0]
    return out

def parse_servos(resp: bytes) -> list[dict]:
    """Parse la réponse 0xA1 (lecture angles servos).
    Format payload: [0xA1][count][id1][pos_lo1][pos_hi1]..."""
    if not resp or len(resp) < 6:
        return []
    payload = resp[5:-1]
    if not payload or payload[0] != 0xA1:
        return []
    data  = payload[1:]
    if not data:
        return []
    count = data[0]
    servos = []
    i = 1
    for _ in range(count):
        if i + 2 >= len(data):
            break
        sid = data[i]
        pos = struct.unpack('<H', data[i+1:i+3])[0]
        servos.append({'id': sid, 'position': pos, 'degrees': round(pos * 360 / 4096, 1)})
        i += 3
    return servos

# ─── Scan des ports série ─────────────────────────────────────────────────────

def find_eilik_port() -> str | None:
    SKIP = ('bluetooth', 'bt', 'debug', 'incoming-port', 'serial over bluetooth', 'virtual')
    for p in serial.tools.list_ports.comports():
        nl = p.name.lower()
        if any(k in nl for k in SKIP):
            continue
        if any(k in (p.description or '').lower() for k in SKIP):
            continue
        if '28E9' in (p.hwid or '').upper():  # GD32 VID
            return p.device
        if 'usbmodem' in p.device.lower():
            return p.device
    return None

# ─── Envoi + réception ───────────────────────────────────────────────────────

def send_recv(ser: serial.Serial, cmd: bytes, label: str = '', timeout: float = 2.0) -> bytes | None:
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    ser.write(cmd)
    ser.flush()
    print(f"  TX [{label}]: {cmd.hex(' ')}")
    resp = read_frame(ser, timeout)
    if resp:
        print(f"  RX [{label}]: {resp.hex(' ')} ({len(resp)} bytes)")
    else:
        print(f"  RX [{label}]: <timeout>")
    return resp

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    port = USB_PORT
    if not port:
        port = find_eilik_port()
    if not port:
        print("Port USB Eilik introuvable. Ports disponibles:")
        for p in serial.tools.list_ports.comports():
            print(f"  {p.device}  {p.description}  [{p.hwid}]")
        sys.exit(1)

    print(f"Connexion à {port} (baud={BAUD_RATE})...")
    try:
        ser = serial.Serial(port, BAUD_RATE, timeout=TIMEOUT)
    except serial.SerialException as e:
        print(f"Erreur ouverture port: {e}")
        sys.exit(1)

    time.sleep(0.2)
    print(f"Port ouvert: {ser.is_open}\n")

    # ── 1. Ping ───────────────────────────────────────────────────────────────
    print("=== 1. PING (0x01) ===")
    resp = send_recv(ser, cmd_ping(), 'ping', timeout=3.0)
    if resp:
        info = parse_ping(resp)
        if info:
            print(f"  chip_id          : {info.get('chip_id','?')}")
            print(f"  model_number     : {info.get('model_number','?')}")
            print(f"  firmware_version : {info.get('firmware_version','?')}")
            print(f"  boot_version     : {info.get('boot_version','?')}")
    print()

    # ── 2. Lecture angles servos ───────────────────────────────────────────────
    print("=== 2. READ SERVO ANGLES (0xA1) ===")
    resp = send_recv(ser, cmd_read_servos(), 'servo_read', timeout=2.0)
    if resp:
        servos = parse_servos(resp)
        for s in servos:
            print(f"  Servo #{s['id']}: pos={s['position']} ({s['degrees']}°)")
    print()

    # ── 3. Lecture run number ──────────────────────────────────────────────────
    print("=== 3. READ RUN NUMBER (0xA5) ===")
    resp = send_recv(ser, cmd_read_run_num(), 'run_num', timeout=2.0)
    print()

    # ── 4. Read display content ────────────────────────────────────────────────
    print("=== 4. READ DISPLAY (0xA3) ===")
    resp = send_recv(ser, cmd_read_display(), 'display', timeout=2.0)
    if resp and len(resp) > 6:
        payload = resp[6:-1]
        print(f"  Display data ({len(payload)} bytes): {payload.hex(' ')[:120]}")
    print()

    # ── 5. Read all parameters ────────────────────────────────────────────────
    print("=== 5. READ ALL PARAMS (0x20) ===")
    resp = send_recv(ser, cmd_read_all(), 'read_all', timeout=3.0)
    if resp and len(resp) > 6:
        payload = resp[6:-1]
        print(f"  Params dump ({len(payload)} bytes):")
        # Afficher en hex 16 bytes par ligne
        for i in range(0, min(len(payload), 256), 16):
            chunk = payload[i:i+16]
            hex_  = ' '.join(f'{b:02x}' for b in chunk)
            ascii_ = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
            print(f"  {i:04x}: {hex_:<48}  {ascii_}")
    print()

    # ── 6. Heartbeat (0x03, 0x05) — from FirmwareUpdate.send_heartbeat ────────
    print("=== 6. HEARTBEAT (0x03 0x05) ===")
    hb = frame([0x03, 0x05])
    resp = send_recv(ser, hb, 'heartbeat', timeout=2.0)
    print()

    # ── 7. Raw bytes dump ─────────────────────────────────────────────────────
    print("=== 7. PASSIVE LISTEN 3s ===")
    time.sleep(0.1)
    deadline = time.time() + 3.0
    passive  = bytearray()
    while time.time() < deadline:
        if ser.in_waiting:
            passive.extend(ser.read(ser.in_waiting))
        time.sleep(0.01)
    if passive:
        print(f"  Received {len(passive)} bytes (passive):")
        for i in range(0, len(passive), 16):
            chunk = passive[i:i+16]
            hex_  = ' '.join(f'{b:02x}' for b in chunk)
            ascii_ = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
            print(f"  {i:04x}: {hex_:<48}  {ascii_}")
    else:
        print("  Aucun byte reçu en passif.")
    print()

    # ── 8. Contrôle servos ──────────────────────────────────────────────────────
    print("=== 8. WRITE SERVO ANGLES (0xA2) — wakeup test ===")
    # Envoyer les 4 servos à position neutre (512 = ~180° sur 10-bit servo)
    # Format: [0xA2, count, id, pos_lo, pos_hi, ...]
    neutral_pos = 512   # centre
    servos_cmd = [
        (1, neutral_pos & 0xFF, (neutral_pos >> 8) & 0xFF),
        (2, neutral_pos & 0xFF, (neutral_pos >> 8) & 0xFF),
        (3, neutral_pos & 0xFF, (neutral_pos >> 8) & 0xFF),
        (4, neutral_pos & 0xFF, (neutral_pos >> 8) & 0xFF),
    ]
    resp = send_recv(ser, cmd_write_servo(servos_cmd), 'servo_write', timeout=2.0)
    if resp:
        print(f"  Réponse: {resp.hex(' ')}")
    time.sleep(1.0)
    print()

    # ── 9. Lecture servos après move ──────────────────────────────────────────
    print("=== 9. READ SERVOS AFTER MOVE ===")
    resp = send_recv(ser, cmd_read_servos(), 'servo_read2', timeout=2.0)
    if resp:
        servos = parse_servos(resp)
        for s in servos:
            print(f"  Servo #{s['id']}: pos={s['position']} ({s['degrees']}°)")
    print()

    # ── 10. Write run number — déclencher animation ───────────────────────────
    print("=== 10. WRITE RUN NUMBER (0xA6) — animation 1 ===")
    resp = send_recv(ser, cmd_write_run_num(1), 'run_write_1', timeout=2.0)
    if resp:
        print(f"  Réponse: {resp.hex(' ')}")
    time.sleep(2.0)
    print()

    ser.close()
    print("Done.")

if __name__ == '__main__':
    main()
