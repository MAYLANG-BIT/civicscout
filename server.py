import sqlite3
import time
import bcrypt
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="CivicScout API v1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "civicscout.db"

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
            role TEXT NOT NULL CHECK(role IN ('scout', 'lgu')),
            barangay TEXT DEFAULT 'Brgy. Batia',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY,
            scout_email TEXT NOT NULL,
            scout_name TEXT NOT NULL,
            barangay TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            image TEXT,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            status TEXT DEFAULT 'Reported',
            dispatched_unit TEXT,
            ai_flagged INTEGER DEFAULT 0,
            confirmations INTEGER DEFAULT 1,
            confirmed_by TEXT DEFAULT '',
            timestamp TEXT NOT NULL
        )
    """)
    # Seed default demo LGU account if not exists
    cur.execute("SELECT id FROM users WHERE email = ?", ("lgu@batia.gov.ph",))
    if not cur.fetchone():
        pw_hash = bcrypt.hashpw("batia2026".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        cur.execute(
            "INSERT INTO users (name, email, password_hash, role, barangay) VALUES (?, ?, ?, ?, ?)",
            ("Brgy. Batia Desk Officer", "lgu@batia.gov.ph", pw_hash, "lgu", "Brgy. Batia")
        )
    conn.commit()
    conn.close()

init_db()

class RegisterPayload(BaseModel):
    name: str
    email: str
    password: str
    role: str
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
    description: str
    image: Optional[str] = None
    lat: float
    lng: float
    status: str = "Reported"
    dispatchedUnit: Optional[str] = None
    aiFlagged: bool = False
    confirmations: int = 1
    confirmedBy: list[str] = []
    timestamp: str

class StatusUpdatePayload(BaseModel):
    status: str
    dispatchedUnit: Optional[str] = None

class ConfirmPayload(BaseModel):
    scoutEmail: str

@app.post("/api/register")
def register(data: RegisterPayload):
    if data.role == "lgu" and data.lguCode != "BATIA-LGU-2026":
        raise HTTPException(status_code=403, detail="Invalid LGU Authorization Code.")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE email = ?", (data.email.lower(),))
    if cur.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Email already registered.")
    pw_hash = bcrypt.hashpw(data.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    cur.execute(
        "INSERT INTO users (name, email, password_hash, role, barangay) VALUES (?, ?, ?, ?, ?)",
        (data.name.strip(), data.email.lower().strip(), pw_hash, data.role, data.barangay)
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.close()
    return {"id": user_id, "name": data.name.strip(), "email": data.email.lower().strip(), "role": data.role, "barangay": data.barangay}

@app.post("/api/login")
def login(data: LoginPayload):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = ?", (data.email.lower().strip(),))
    row = cur.fetchone()
    conn.close()
    if not row or not bcrypt.checkpw(data.password.encode("utf-8"), row["password_hash"].encode("utf-8")):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return {"id": row["id"], "name": row["name"], "email": row["email"], "role": row["role"], "barangay": row["barangay"]}

@app.get("/api/reports")
def get_reports():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM reports ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()
    result = []
    for r in rows:
        result.append({
            "id": r["id"],
            "scoutEmail": r["scout_email"],
            "scoutName": r["scout_name"],
            "barangay": r["barangay"],
            "category": r["category"],
            "description": r["description"],
            "image": r["image"],
            "lat": r["lat"],
            "lng": r["lng"],
            "status": r["status"],
            "dispatchedUnit": r["dispatched_unit"],
            "aiFlagged": bool(r["ai_flagged"]),
            "confirmations": r["confirmations"],
            "confirmedBy": [x for x in r["confirmed_by"].split(",") if x],
            "timestamp": r["timestamp"]
        })
    return result

@app.post("/api/reports")
def create_report(r: ReportPayload):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO reports (id, scout_email, scout_name, barangay, category, description, image, lat, lng, status, dispatched_unit, ai_flagged, confirmations, confirmed_by, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        r.id, r.scoutEmail, r.scoutName, r.barangay, r.category, r.description,
        r.image, r.lat, r.lng, r.status, r.dispatchedUnit, int(r.aiFlagged),
        r.confirmations, ",".join(r.confirmedBy), r.timestamp
    ))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.patch("/api/reports/{report_id}")
def update_report(report_id: int, payload: StatusUpdatePayload):
    conn = get_db()
    cur = conn.cursor()
    if payload.dispatchedUnit is not None:
        cur.execute("UPDATE reports SET status = ?, dispatched_unit = ? WHERE id = ?", (payload.status, payload.dispatchedUnit, report_id))
    else:
        cur.execute("UPDATE reports SET status = ? WHERE id = ?", (payload.status, report_id))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.post("/api/reports/{report_id}/confirm")
def confirm_report(report_id: int, payload: ConfirmPayload):
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
    return {"ok": True}

# Serve frontend files directly at http://localhost:8000
app.mount("/", StaticFiles(directory=".", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)