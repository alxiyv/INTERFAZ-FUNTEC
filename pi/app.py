"""Servidor RailTrack (Persona 5). Uso: RAIL_PORT=SIM|AUTO|/dev/ttyUSB0 python app.py"""
import os, json, time, threading
from flask import Flask, jsonify, request, send_from_directory, Response
from bridge import Rail
import sessions as S
try:
    from tracker import Tracker          # Persona 4
except Exception:
    Tracker = None

app = Flask(__name__, static_folder="static")
SET_F = os.path.join(S.DATA, "_settings.json")
DEF = {"travel_mm": 800, "speed": 50, "deadzone": 8, "gain": 0.3}
try: cfg = {**DEF, **json.load(open(SET_F))}
except Exception: cfg = dict(DEF)
rail = Rail(os.environ.get("RAIL_PORT", "SIM"), cfg["travel_mm"])
cur = S.load("demo") if S.exists("demo") else S.new("demo")
busy = {"msg": ""}
tracker = None

def save(): S.save(cur)

def go(mm, push=True):
    mm = round(mm, 3); rail.goto(mm, cfg["speed"])
    if push: cur["history"] = (cur["history"] + [[cur["last_mm"], cur["frame"]]])[-200:]
    cur["last_mm"] = mm

@app.errorhandler(Exception)
def err(e):
    return jsonify(ok=False, error=str(e)), 400

@app.get("/")
def index(): return send_from_directory("static", "index.html")

@app.get("/api/status")
def status():
    return jsonify(connected=rail.connected, pos=rail.pos, state=rail.state, error=rail.error,
                   busy=busy["msg"], cfg=cfg, session=cur, tracking=bool(tracker and getattr(tracker, "running", False)))

@app.post("/api/cmd/<c>")
def cmd(c):
    if c not in ("home", "stop", "estop", "reset"): return jsonify(ok=False, error="comando"), 404
    getattr(rail, c)()
    if c == "home": cur["last_mm"] = 0.0; save()
    return jsonify(ok=True)

@app.post("/api/goto")
def goto():
    go(float(request.json["mm"])); save(); return jsonify(ok=True)

@app.post("/api/move")
def move():
    go(cur["last_mm"] + float(request.json["mm"])); save(); return jsonify(ok=True)

@app.post("/api/settings")
def settings():
    for k, v in request.json.items():
        if k in DEF: cfg[k] = float(v)
    rail.travel = cfg["travel_mm"]; cur["calibration"]["travel_mm"] = cfg["travel_mm"]
    json.dump(cfg, open(SET_F, "w")); save()
    if tracker: tracker.params.update({"deadzone": cfg["deadzone"], "gain": cfg["gain"]})
    return jsonify(ok=True)

# ---- sesiones y posiciones ----
@app.get("/api/sessions")
def sessions_list(): return jsonify(S.list_all())

@app.post("/api/sessions")
def session_open():
    global cur
    n = request.json["name"].strip()
    if not n: raise ValueError("Escribe un nombre")
    cur = S.load(n) if S.exists(n) else S.new(n); save(); return jsonify(ok=True)

@app.get("/api/export")
def export():
    return Response(json.dumps(cur, indent=1, ensure_ascii=False), mimetype="application/json",
                    headers={"Content-Disposition": f"attachment; filename={cur['name']}.json"})

@app.post("/api/positions")
def pos_add():
    d = request.json; mm = cur["last_mm"]
    cur["positions"] = [p for p in cur["positions"] if p["name"] != d["name"]] + \
        [{"name": d["name"], "mm": mm, "speed": cfg["speed"], "notes": d.get("notes", "")}]
    save(); return jsonify(ok=True)

@app.delete("/api/positions/<name>")
def pos_del(name):
    cur["positions"] = [p for p in cur["positions"] if p["name"] != name]; save(); return jsonify(ok=True)

@app.post("/api/positions/<name>/go")
def pos_go(name):
    p = next(p for p in cur["positions"] if p["name"] == name); go(p["mm"]); save(); return jsonify(ok=True)

# ---- stop motion ----
@app.post("/api/sm/step")
def sm_step():
    d = request.json; k = 1 if d["dir"] > 0 else -1
    cur["step_mm"] = float(d.get("step", cur["step_mm"]))
    go(cur["last_mm"] + k * cur["step_mm"]); cur["frame"] = max(0, cur["frame"] + k); save()
    return jsonify(ok=True)

@app.post("/api/sm/undo")
def sm_undo():
    if not cur["history"]: raise ValueError("No hay nada que deshacer")
    mm, fr = cur["history"].pop(); rail.goto(mm, cfg["speed"]); cur["last_mm"], cur["frame"] = mm, fr
    save(); return jsonify(ok=True)

@app.post("/api/sm/marker")
def sm_marker():
    cur["markers"][request.json["which"]] = cur["last_mm"]; save(); return jsonify(ok=True)

@app.post("/api/sm/lerp")
def sm_lerp():
    m = cur["markers"]; d = request.json; i, n = int(d["i"]), int(d["n"])
    if m["start"] is None or m["end"] is None or n < 2: raise ValueError("Guarda inicio y fin, y usa 2 o más puntos")
    go(m["start"] + (m["end"] - m["start"]) * i / (n - 1)); cur["frame"] = i; save(); return jsonify(ok=True)

@app.post("/api/sm/resume")
def sm_resume():
    target = cur["last_mm"]
    def run():
        try:
            busy["msg"] = "Buscando el origen (HOME)…"; rail.home(); rail.wait_idle()
            busy["msg"] = f"Yendo a {target} mm…"; rail.goto(target, cfg["speed"]); rail.wait_idle()
        finally: busy["msg"] = ""
    threading.Thread(target=run, daemon=True).start(); return jsonify(ok=True, target=target)

# ---- seguimiento (Persona 4) ----
@app.post("/api/track/<a>")
def track(a):
    global tracker
    if Tracker is None: raise ValueError("tracker.py aún no está disponible (Persona 4)")
    if a == "start":
        tracker = tracker or Tracker(rail); tracker.params.update({"deadzone": cfg["deadzone"], "gain": cfg["gain"]}); tracker.start()
    elif tracker: tracker.stop(); rail.stop()
    return jsonify(ok=True)

@app.get("/video")
def video():
    def gen():
        while True:
            j = getattr(tracker, "last_jpeg", None)
            if j: yield b"--f\r\nContent-Type: image/jpeg\r\n\r\n" + j + b"\r\n"
            time.sleep(.07)
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=f")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
