"""Sesiones en JSON (pi/data/<nombre>.json). Escritura atómica para no corromper al apagar."""
import os, json, re, time
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA, exist_ok=True)

def _p(n): return os.path.join(DATA, re.sub(r"[^\w\-]", "_", n) + ".json")

def new(name):
    return {"name": name, "project": name, "scene": 1, "frame": 0, "step_mm": 0.5,
            "last_mm": 0.0, "calibration": {"travel_mm": 800}, "positions": [],
            "history": [], "markers": {"start": None, "end": None}, "updated": 0}

def save(s):
    s["updated"] = time.time(); tmp = _p(s["name"]) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(s, f, indent=1, ensure_ascii=False)
    os.replace(tmp, _p(s["name"]))

def load(name):
    with open(_p(name), encoding="utf-8") as f: return {**new(name), **json.load(f)}

def exists(name): return os.path.exists(_p(name))

def list_all():
    out = []
    for f in os.listdir(DATA):
        if f.endswith(".json") and not f.startswith("_"):
            try:
                d = json.load(open(os.path.join(DATA, f), encoding="utf-8"))
                out.append({"name": d["name"], "updated": d.get("updated", 0)})
            except Exception: pass
    return sorted(out, key=lambda x: -x["updated"])
