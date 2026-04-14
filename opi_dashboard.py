#!/usr/bin/env python3
"""
OPI Network Monitor Dashboard
Monitors Xiaomi Redmi Note 9 Pro via ADB from Orange Pi Zero 3
"""

import subprocess
import re
import time
import os
import json
import secrets
import hashlib
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
import uvicorn

STATIC_DIR  = os.path.join(os.path.dirname(__file__), "static")
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "opi-conf.json")

# ─── Config / Auth helpers ────────────────────────────────────────────────────

def _init_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    salt       = secrets.token_hex(16)
    pw_hash    = hashlib.pbkdf2_hmac("sha256", b"admin", salt.encode(), 100_000).hex()
    config     = {
        "login":         "admin",
        "password_hash": f"{salt}:{pw_hash}",
        "secret_key":    secrets.token_hex(32),
    }
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    return config

CONFIG = _init_config()

def check_password(password: str) -> bool:
    cfg = json.load(open(CONFIG_FILE))
    try:
        salt, stored = cfg["password_hash"].split(":")
    except ValueError:
        return False
    computed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()
    return secrets.compare_digest(computed, stored)

# ─── Auth middleware ───────────────────────────────────────────────────────────

_PUBLIC = {"/login", "/api/login"}

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/static") or path in _PUBLIC:
            return await call_next(request)
        if not request.session.get("user"):
            if path.startswith("/api/"):
                return Response("Unauthorized", status_code=401)
            return RedirectResponse("/login")
        return await call_next(request)

app = FastAPI(title="OPI Monitor")
# SessionMiddleware must wrap AuthMiddleware → add Auth first, then Session
app.add_middleware(AuthMiddleware)
app.add_middleware(SessionMiddleware, secret_key=CONFIG["secret_key"], session_cookie="opi_session")

# ─── ADB helpers ──────────────────────────────────────────────────────────────

def adb(cmd: str, root: bool = False) -> str:
    full = f'adb shell su -c "{cmd}"' if root else f'adb shell {cmd}'
    try:
        r = subprocess.run(full, shell=True, capture_output=True, text=True, timeout=5)
        return r.stdout.strip()
    except Exception:
        return ""

# ─── Data collectors ──────────────────────────────────────────────────────────

def get_battery() -> dict:
    def s(f): return adb(f"cat /sys/class/power_supply/battery/{f}", root=True)
    capacity = s("capacity"); temp_raw = s("temp")
    current  = s("current_now"); voltage = s("voltage_now")
    charging = s("charging_enabled"); status = s("status")
    return {
        "capacity":   int(capacity)                if capacity.lstrip('-').isdigit()  else None,
        "temp":       round(int(temp_raw)/10, 1)   if temp_raw.lstrip('-').isdigit()  else None,
        "current_ma": round(int(current)/1000, 1)  if current.lstrip('-').isdigit()   else None,
        "voltage_v":  round(int(voltage)/1000000,3) if voltage.lstrip('-').isdigit()  else None,
        "charging":   charging == "1",
        "status":     status or "Unknown",
    }

def get_signal() -> dict:
    full = adb("dumpsys telephony.registry")
    earfcn = band = None
    m = re.search(r'IN_SERVICE.*?mChannelNumber=(\d+)', full, re.DOTALL)
    if m:
        earfcn = int(m.group(1))
        bands = [(600,1199,"B2 (1900 MHz)"),(1200,1949,"B3 (1800 MHz)"),
                 (1950,2399,"B4 (AWS)"),(2400,2649,"B5 (850 MHz)"),
                 (2750,3449,"B7 (2600 MHz)"),(3450,3799,"B8 (900 MHz)"),
                 (6150,6449,"B20 (800 MHz)"),(0,599,"B1 (2100 MHz)")]
        band = next((b for lo,hi,b in bands if lo<=earfcn<=hi), f"EARFCN {earfcn}")
    rsrp=rsrq=rssi=None
    sig = re.search(r'mRegistered=YES.*?rssi=(-\d+).*?rsrp=(-\d+).*?rsrq=(-\d+)', full, re.DOTALL)
    if sig: rssi,rsrp,rsrq = int(sig.group(1)),int(sig.group(2)),int(sig.group(3))
    op = re.search(r'mOperatorAlphaLong=(\w+)', full)
    return {"earfcn":earfcn,"band":band,"rsrp":rsrp,"rsrq":rsrq,"rssi":rssi,
            "operator": op.group(1) if op else "Unknown"}

def get_traffic() -> dict:
    rx = tx = 0
    wan_iface = None
    try:
        with open("/proc/net/dev") as f:
            for line in f:
                # Ищем WAN интерфейс: enx..., usb..., wwan...
                iface = line.strip().split(":")[0].strip()
                if re.match(r'^(enx|usb|wwan)', iface):
                    parts = line.split()
                    rx = int(parts[1])
                    tx = int(parts[9])
                    wan_iface = iface
                    break
    except Exception:
        pass
    return {
        "rx_mb":    round(rx / 1024 / 1024, 2),
        "tx_mb":    round(tx / 1024 / 1024, 2),
        "wan_iface": wan_iface or "—",
    }

def get_sms(limit: int = 20) -> list:
    raw = adb("content query --uri content://sms/inbox "
              "--projection address:body:date:read", root=True)
    msgs = []
    for row in raw.split("Row:"):
        row = row.strip()
        if not row: continue
        addr = re.search(r'address=([^,]+)', row)
        body = re.search(r'body=(.+?)(?:, date=|$)', row, re.DOTALL)
        date = re.search(r'date=(\d+)', row)
        read = re.search(r'read=(\d)', row)
        ts   = int(date.group(1)) if date else 0
        msgs.append({
            "from": addr.group(1).strip() if addr else "?",
            "body": body.group(1).strip() if body else "",
            "date": datetime.fromtimestamp(ts/1000).strftime("%d.%m %H:%M") if ts else "",
            "read": read.group(1)=="1" if read else True,
            "ts":   ts,
        })
    msgs.sort(key=lambda x: x["ts"], reverse=True)
    for m in msgs: del m["ts"]
    return msgs[:limit]

def get_opi_stats() -> dict:
    with open("/proc/uptime") as f:
        sec = int(float(f.read().split()[0]))
    h,rem=divmod(sec,3600); m,s=divmod(rem,60)
    cpu_temp=None
    for path in ["/sys/class/thermal/thermal_zone0/temp",
                 "/sys/devices/virtual/thermal/thermal_zone0/temp"]:
        if os.path.exists(path):
            with open(path) as f:
                t=int(f.read().strip())
                cpu_temp=round(t/1000,1) if t>1000 else t
            break
    with open("/proc/loadavg") as f:
        load=f.read().split()[:3]
    return {"uptime":f"{h}h {m}m {s}s","cpu_temp":cpu_temp,"load":" / ".join(load)}

# ─── API ──────────────────────────────────────────────────────────────────────

@app.get("/api/stats")
def api_stats():
    return {"battery":get_battery(),"signal":get_signal(),"traffic":get_traffic(),
            "opi":get_opi_stats(),"time":datetime.now().strftime("%H:%M:%S")}

@app.get("/api/sms")
def api_sms(): return get_sms()

@app.post("/api/sms/clear")
def api_sms_clear():
    db_dir = "/data/user/0/com.android.providers.telephony/databases"
    adb(f"rm {db_dir}/mmssms.db*", root=True)
    time.sleep(1)
    adb("am force-stop com.android.phone", root=True)
    return {"status": "ok"}

class SmsPayload(BaseModel):
    to: str; body: str

@app.post("/api/sms/send")
def api_sms_send(payload: SmsPayload):
    body = payload.body.replace('"', '\\"')
    args = ["adb","shell","service","call","isms","5","i32","0",
            "s16","com.android.mms.service","s16","null",
            "s16",payload.to,"s16","null",
            "s16",f'"{body}"',"s16","null","s16","null"]
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=10)
        out = r.stdout.strip()
        return {"result":out,"success":"00000000" in out}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class UssdPayload(BaseModel):
    code: str

@app.post("/api/ussd")
def api_ussd(payload: UssdPayload):
    code_enc = payload.code.replace("#","%23")
    subprocess.run(["adb","shell","am","start","-a","android.intent.action.CALL",
                    "-d",f"tel:{code_enc}"], capture_output=True, timeout=5)
    time.sleep(4)
    r = subprocess.run("adb exec-out uiautomator dump /dev/tty 2>/dev/null",
                       shell=True, capture_output=True, text=True, timeout=10)
    texts = re.findall(r'text="([^"]{3,})"', r.stdout)
    skip  = {'OK','Отмена','Cancel','Назад','','MegaFon'}
    result = [t for t in texts if t not in skip and len(t)>3]
    subprocess.run(["adb","shell","input","keyevent","4"], capture_output=True, timeout=3)
    return {"response":result}

@app.post("/api/phone/reboot")
def phone_reboot():
    def do_reboot():
        # Send reboot command
        subprocess.run(["adb", "reboot"], capture_output=True, timeout=5)
        # Wait for device to disappear
        for _ in range(30):
            time.sleep(2)
            r = subprocess.run(["adb", "devices"], capture_output=True, text=True)
            if "device" not in r.stdout.replace("List of devices attached", ""):
                break
        # Wait for device to come back (up to 90 sec)
        for _ in range(45):
            time.sleep(2)
            r = subprocess.run(["adb", "devices"], capture_output=True, text=True)
            if "device" in r.stdout.replace("List of devices attached", ""):
                break
        # Give Android time to fully boot
        time.sleep(10)
        # Re-run usb-autowarp to reconnect modem and reconfigure routing
        subprocess.run(["/usr/local/bin/usb-autowarp.sh"], capture_output=True, timeout=60)

    import threading
    threading.Thread(target=do_reboot, daemon=True).start()
    return {"status": "rebooting, will reconnect automatically"}

@app.post("/api/opi/reboot")
def opi_reboot():
    subprocess.Popen(["reboot"]); return {"status":"ok"}

@app.post("/api/opi/poweroff")
def opi_poweroff():
    subprocess.Popen(["poweroff"]); return {"status":"ok"}

# ─── Auth routes ──────────────────────────────────────────────────────────────

@app.get("/login")
def login_page():
    return FileResponse(os.path.join(STATIC_DIR, "login.html"))

class LoginPayload(BaseModel):
    login: str
    password: str

@app.post("/api/login")
async def api_login(payload: LoginPayload, request: Request):
    cfg = json.load(open(CONFIG_FILE))
    if payload.login == cfg["login"] and check_password(payload.password):
        request.session["user"] = payload.login
        return {"ok": True}
    raise HTTPException(status_code=401, detail="Invalid credentials")

@app.post("/api/logout")
async def api_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)

# ─── Static ───────────────────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def dashboard(): return FileResponse(os.path.join(STATIC_DIR,"index.html"))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=80)
