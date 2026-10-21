"""Puente serie con el ESP32 (protocolo RailTrack). RAIL_PORT=SIM usa un simulador interno."""
import threading, time, glob
try:
    import serial
except ImportError:
    serial = None


class Sim:
    """Simula el firmware de Persona 3: mismos comandos y respuestas."""
    def __init__(s):
        s.pos = s.tgt = 0.0; s.vel = 50.0; s.t = time.time()

    def tick(s):
        n = time.time(); dt = n - s.t; s.t = n
        d = s.tgt - s.pos; m = s.vel * dt
        s.pos = s.tgt if abs(d) <= m else s.pos + (m if d > 0 else -m)

    def cmd(s, line):
        s.tick(); p = line.split(); c = p[0].upper()
        if c == "HOME": s.pos = s.tgt = 0.0
        elif c == "GOTO": s.tgt = float(p[1]); s.vel = float(p[2]) if len(p) > 2 else s.vel
        elif c == "MOVE": s.tgt += float(p[1])
        elif c == "TRACK": s.tgt = float(p[1])
        elif c == "SPEED": s.vel = float(p[1])
        elif c in ("STOP", "ESTOP"): s.tgt = s.pos
        elif c == "POS?":
            return f"POS {s.pos:.2f} {'MOVING' if abs(s.tgt - s.pos) > .01 else 'IDLE'}"
        return "OK"


class Rail:
    def __init__(s, port="SIM", travel=800.0):
        s.port, s.travel = port, travel
        s.pos, s.state, s.error, s.connected = 0.0, "DISCONNECTED", "", False
        s.sim = Sim() if port == "SIM" else None
        s.ser = None; s.lock = threading.Lock()
        threading.Thread(target=s._loop, daemon=True).start()

    # ---- recepción ----
    def _rx(s, l):
        l = l.strip()
        if l.startswith("POS"):
            _, p, st = (l.split() + ["", ""])[:3]; s.pos = float(p); s.state = st
        elif l.startswith("ERR"): s.error = l
        elif l.startswith("OK"): s.error = ""

    def _loop(s):
        while True:
            try:
                if s.sim:
                    s.connected = True; s._tx("POS?"); time.sleep(.2); continue
                if not s.ser:                      # reconexión automática
                    p = s.port
                    if p == "AUTO":
                        c = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
                        if not c: raise OSError("sin puerto")
                        p = c[0]
                    s.ser = serial.Serial(p, 115200, timeout=.1); time.sleep(2)
                    s.connected = True
                s._tx("POS?")
                end = time.time() + .15
                while time.time() < end:
                    l = s.ser.readline().decode(errors="ignore")
                    if l: s._rx(l)
                time.sleep(.1)
            except Exception:
                s.connected = False; s.state = "DISCONNECTED"
                try: s.ser and s.ser.close()
                except Exception: pass
                s.ser = None; time.sleep(1.5)

    # ---- envío ----
    def _tx(s, line):
        with s.lock:
            if s.sim:
                r = s.sim.cmd(line)
                if r: s._rx(r)
                return
            if not s.ser: raise ConnectionError("Sin conexión con el ESP32")
            try: s.ser.write((line + "\n").encode())
            except Exception: s.ser = None; raise ConnectionError("Se perdió la conexión")

    def check(s, mm):
        if not 0 <= mm <= s.travel: raise ValueError(f"{mm} mm fuera del recorrido (0 a {s.travel} mm)")

    def goto(s, mm, vel=50): s.check(mm); s._tx(f"GOTO {mm:.3f} {vel:.1f}")
    def move(s, d): s.check(s.pos + d); s._tx(f"MOVE {d:.3f}")
    def track(s, mm): s.check(mm); s._tx(f"TRACK {mm:.3f}")
    def home(s): s._tx("HOME")
    def stop(s): s._tx("STOP")
    def estop(s): s._tx("ESTOP")
    def reset(s): s._tx("RESET")

    def wait_idle(s, timeout=60):
        time.sleep(.5); t = time.time()
        while s.state != "IDLE" and time.time() - t < timeout: time.sleep(.1)
