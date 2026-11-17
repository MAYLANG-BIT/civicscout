import sqlite3
import time
import bcrypt
from typing import Optional
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="CivicScout Realtime API v4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "civicscout.db"
RATE_LIMIT_SECONDS = 30
MAX_OPEN_REPORTS_PER_SCOUT = 10
last_submission_ts: dict[str, float] = {}

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

ws_manager = ConnectionManager()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            unit_type TEXT DEFAULT '',
            barangay TEXT DEFAULT 'Brgy. Batia',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    try:
        cur.execute("ALTER TABLE users ADD COLUMN unit_type TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass

    cur.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY,
            scout_email TEXT NOT NULL,
            scout_name TEXT NOT NULL,
            barangay TEXT NOT NULL,
            category TEXT NOT NULL,
            severity TEXT DEFAULT 'Moderate',
            street_address TEXT DEFAULT 'Brgy. Batia, Bocaue',
            description TEXT NOT NULL,
            image TEXT,
            resolved_image TEXT,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            status TEXT DEFAULT 'Reported',
            dispatched_unit TEXT,
            assigned_unit_type TEXT DEFAULT '',
            ai_flagged INTEGER DEFAULT 0,
            confirmations INTEGER DEFAULT 1,
            confirmed_by TEXT DEFAULT '',
            created_epoch INTEGER DEFAULT 0,
            timestamp TEXT NOT NULL
        )
    """)
    migrations = [
        "ALTER TABLE reports ADD COLUMN resolved_image TEXT",
        "ALTER TABLE reports ADD COLUMN severity TEXT DEFAULT 'Moderate'",
        "ALTER TABLE reports ADD COLUMN street_address TEXT DEFAULT 'Brgy. Batia, Bocaue'",
        "ALTER TABLE reports ADD COLUMN created_epoch INTEGER DEFAULT 0",
        "ALTER TABLE reports ADD COLUMN assigned_unit_type TEXT DEFAULT ''"
    ]
    for sql in migrations:
        try:
            cur.execute(sql)
        except sqlite3.OperationalError:
            pass

    # Seed default LGU & Field Responder accounts for instant demo
    default_accounts = [
        ("Brgy. Batia Desk Officer", "lgu@batia.gov.ph", "batia2026", "lgu", "", "Brgy. Batia"),
        ("Engr. Reyes (Barangay Electrician)", "electrician@batia.gov.ph", "batia2026", "responder", "Electrician Team", "Brgy. Batia"),
        ("Garbage Truck #04 Crew", "garbage@batia.gov.ph", "batia2026", "responder", "Garbage Truck #04", "Brgy. Batia"),
        ("Motorized Road Crew", "road@batia.gov.ph", "batia2026", "responder", "Motorized Road Crew", "Brgy. Batia"),
        ("Drainage Maintenance Team", "drainage@batia.gov.ph", "batia2026", "responder", "Drainage Maintenance", "Brgy. Batia"),
    ]
    for name, email, raw_pw, role, unit_type, brgy in default_accounts:
        cur.execute("SELECT id FROM users WHERE email = ?", (email,))
        if not cur.fetchone():
            pw_hash = bcrypt.hashpw(raw_pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            cur.execute(
                "INSERT INTO users (name, email, password_hash, role, unit_type, barangay) VALUES (?, ?, ?, ?, ?, ?)",
                (name, email, pw_hash, role, unit_type, brgy)
            )
    conn.commit()
    conn.close()

init_db()

class RegisterPayload(BaseModel):
    name: str
    email: str
    password: str
    role: str
    unitType: Optional[str] = ""
    barangay: str = "Brgy. Batia"
    lguCode: Optional[str] = None

class LoginPayload(BaseModel):
    email: str
    password: str

class ReportPayload(BaseModel):
    id: int
    scoutEmail: str
    scoutName: str
    barangay: str
    category: str
    severity: str = "Moderate"
    streetAddress: str = "Brgy. Batia, Bocaue"
    description: str
    image: Optional[str] = None
    resolvedImage: Optional[str] = None
    lat: float
    lng: float
    status: str = "Reported"
    dispatchedUnit: Optional[str] = None
    assignedUnitType: Optional[str] = ""
    aiFlagged: bool = False
    confirmations: int = 1
    confirmedBy: list[str] = []
    createdEpoch: Optional[int] = None
    timestamp: str

class StatusUpdatePayload(BaseModel):
    status: str
    dispatchedUnit: Optional[str] = None
    assignedUnitType: Optional[str] = None
    resolvedImage: Optional[str] = None

class ConfirmPayload(BaseModel):
    scoutEmail: str

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)

@app.post("/api/register")
def register(data: RegisterPayload):
    if data.role not in ("scout", "lgu", "responder"):
        raise HTTPException(status_code=400, detail="Invalid role.")
    if data.role in ("lgu", "responder") and data.lguCode != "BATIA-LGU-2026":
        raise HTTPException(status_code=403, detail="Invalid Barangay Authorization Code. (Use: BATIA-LGU-2026)")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE email = ?", (data.email.lower(),))
    if cur.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Email already registered.")
    pw_hash = bcrypt.hashpw(data.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    unit_val = data.unitType if data.role == "responder" else ""
    cur.execute(
        "INSERT INTO users (name, email, password_hash, role, unit_type, barangay) VALUES (?, ?, ?, ?, ?, ?)",
        (data.name.strip(), data.email.lower().strip(), pw_hash, data.role, unit_val, data.barangay)
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.close()
    return {
        "id": user_id,
        "name": data.name.strip(),
        "email": data.email.lower().strip(),
        "role": data.role,
        "unitType": unit_val,
        "barangay": data.barangay
    }

@app.post("/api/login")
def login(data: LoginPayload):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = ?", (data.email.lower().strip(),))
    row = cur.fetchone()
    conn.close()
    if not row or not bcrypt.checkpw(data.password.encode("utf-8"), row["password_hash"].encode("utf-8")):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "role": row["role"],
        "unitType": row["unit_type"] or "",
        "barangay": row["barangay"]
    }

@app.get("/api/reports")
def get_reports():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM reports ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()
    return [{
        "id": r["id"],
        "scoutEmail": r["scout_email"],
        "scoutName": r["scout_name"],
        "barangay": r["barangay"],
        "category": r["category"],
        "severity": r["severity"] or "Moderate",
        "streetAddress": r["street_address"] or "Brgy. Batia, Bocaue",
        "description": r["description"],
        "image": r["image"],
        "resolvedImage": r["resolved_image"],
        "lat": r["lat"],
        "lng": r["lng"],
        "status": r["status"],
        "dispatchedUnit": r["dispatched_unit"],
        "assignedUnitType": r["assigned_unit_type"] or "",
        "aiFlagged": bool(r["ai_flagged"]),
        "confirmations": r["confirmations"],
        "confirmedBy": [x for x in r["confirmed_by"].split(",") if x],
        "createdEpoch": r["created_epoch"] or int(r["id"] / 1000),
        "timestamp": r["timestamp"]
    } for r in rows]

@app.post("/api/reports")
async def create_report(r: ReportPayload):
    now = time.time()
    email_key = r.scoutEmail.lower().strip()
    last_ts = last_submission_ts.get(email_key, 0)
    if now - last_ts < RATE_LIMIT_SECONDS:
        wait = int(RATE_LIMIT_SECONDS - (now - last_ts))
        raise HTTPException(status_code=429, detail=f"Anti-Spam Cooldown: Please wait {wait}s before submitting another report.")

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) as cnt FROM reports WHERE scout_email = ? AND status IN ('Reported', 'Verified', 'In Progress')",
        (email_key,)
    )
    open_count = cur.fetchone()["cnt"]
    if open_count >= MAX_OPEN_REPORTS_PER_SCOUT:
        conn.close()
        raise HTTPException(status_code=429, detail=f"Limit reached: You have {open_count} active unresolved reports.")

    epoch = r.createdEpoch or int(now)
    cur.execute("""
        INSERT OR IGNORE INTO reports (id, scout_email, scout_name, barangay, category, severity, street_address, description, image, resolved_image, lat, lng, status, dispatched_unit, assigned_unit_type, ai_flagged, confirmations, confirmed_by, created_epoch, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        r.id, email_key, r.scoutName, r.barangay, r.category, r.severity, r.streetAddress,
        r.description, r.image, r.resolvedImage, r.lat, r.lng, r.status, r.dispatchedUnit,
        r.assignedUnitType or "", int(r.aiFlagged), r.confirmations, ",".join(r.confirmedBy), epoch, r.timestamp
    ))
    conn.commit()
    conn.close()
    last_submission_ts[email_key] = now
    await ws_manager.broadcast({"event": "NEW_REPORT", "category": r.category, "severity": r.severity, "scoutName": r.scoutName})
    return {"ok": True}

@app.patch("/api/reports/{report_id}")
async def update_report(report_id: int, payload: StatusUpdatePayload):
    conn = get_db()
    cur = conn.cursor()
    fields = ["status = ?"]
    values = [payload.status]

    if payload.dispatchedUnit is not None:
        fields.append("dispatched_unit = ?")
        values.append(payload.dispatchedUnit)
    if payload.assignedUnitType is not None:
        fields.append("assigned_unit_type = ?")
        values.append(payload.assignedUnitType)
    if payload.resolvedImage is not None:
        fields.append("resolved_image = ?")
        values.append(payload.resolvedImage)

    values.append(report_id)
    cur.execute(f"UPDATE reports SET {', '.join(fields)} WHERE id = ?", tuple(values))
    conn.commit()
    conn.close()
    await ws_manager.broadcast({
        "event": "STATUS_UPDATED",
        "reportId": report_id,
        "status": payload.status,
        "assignedUnitType": payload.assignedUnitType
    })
    return {"ok": True}

@app.post("/api/reports/{report_id}/confirm")
async def confirm_report(report_id: int, payload: ConfirmPayload):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM reports WHERE id = ?", (report_id,))
    r = cur.fetchone()
    if not r:
        conn.close()
        raise HTTPException(status_code=404, detail="Report not found.")
    if r["scout_email"] == payload.scoutEmail:
        conn.close()
        raise HTTPException(status_code=400, detail="Cannot confirm your own report.")
    confirmed_list = [x for x in r["confirmed_by"].split(",") if x]
    if payload.scoutEmail not in confirmed_list:
        confirmed_list.append(payload.scoutEmail)
        cur.execute(
            "UPDATE reports SET confirmations = ?, confirmed_by = ? WHERE id = ?",
            (len(confirmed_list) + 1, ",".join(confirmed_list), report_id)
        )
        conn.commit()
    conn.close()
    await ws_manager.broadcast({"event": "REPORT_CONFIRMED", "reportId": report_id})
    return {"ok": True}

app.mount("/", StaticFiles(directory=".", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)