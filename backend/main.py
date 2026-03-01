from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from model import LitterSchema, VehicleSchema
from database import session, engine
import DBMS
from sqlalchemy.orm import Session
from sqlalchemy import func
import os

app = FastAPI(title="LitterWatch API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # open for now, restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve snapshot images statically
# Frontend can access: http://localhost:8000/snapshots/persons/img.jpg
os.makedirs("data/snapshots", exist_ok=True)
app.mount("/snapshots", StaticFiles(directory="data/snapshots"), name="snapshots")

# Create tables on startup
DBMS.Base.metadata.create_all(bind=engine)

def get_db():
    db = session()
    try:
        yield db
    finally:
        db.close()

# ── Health check ──────────────────────────────────────────────
@app.get("/")
def home():
    return {"status": "LitterWatch API running"}

# ── Get all incidents ─────────────────────────────────────────
@app.get("/incidents")
def get_incidents(db: Session = Depends(get_db)):
    return db.query(DBMS.LitterIncident).order_by(
        DBMS.LitterIncident.timestamp.desc()
    ).all()

# ── Get recent incidents (for live dashboard feed) ────────────
@app.get("/incidents/recent")
def get_recent(limit: int = 10, db: Session = Depends(get_db)):
    return db.query(DBMS.LitterIncident).order_by(
        DBMS.LitterIncident.timestamp.desc()
    ).limit(limit).all()

# ── Post new incident (called by detect.py via api_client) ────
@app.post("/incidents")
def post_incident(litter: LitterSchema, db: Session = Depends(get_db)):
    # Always create incident record
    new_incident = DBMS.LitterIncident(**litter.model_dump())
    db.add(new_incident)

    # If vehicle offender, update vehicle table
    if litter.offender_type.lower() == "vehicle" and litter.license_plate:
        existing = db.query(DBMS.Vehicle).filter(
            DBMS.Vehicle.license_plate == litter.license_plate
        ).first()

        if existing:
            # Vehicle seen before → increment count
            existing.last_seen      = litter.timestamp
            existing.incident_count += 1
        else:
            # New vehicle
            new_vehicle = DBMS.Vehicle(
                license_plate  = litter.license_plate,
                first_seen     = litter.timestamp,
                last_seen      = litter.timestamp,
                incident_count = 1
            )
            db.add(new_vehicle)

    db.commit()
    db.refresh(new_incident)
    return new_incident

# ── Get all vehicles ──────────────────────────────────────────
@app.get("/vehicles")
def get_vehicles(db: Session = Depends(get_db)):
    return db.query(DBMS.Vehicle).order_by(
        DBMS.Vehicle.incident_count.desc()
    ).all()

# ── Stats for dashboard cards ─────────────────────────────────
@app.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    total      = db.query(DBMS.LitterIncident).count()
    vehicles   = db.query(DBMS.LitterIncident).filter(
        DBMS.LitterIncident.offender_type == "vehicle"
    ).count()
    persons    = db.query(DBMS.LitterIncident).filter(
        DBMS.LitterIncident.offender_type == "person"
    ).count()

    # Trash type breakdown
    by_type = db.query(
        DBMS.LitterIncident.trash_type,
        func.count(DBMS.LitterIncident.id)
    ).group_by(DBMS.LitterIncident.trash_type).all()

    # Camera breakdown
    by_camera = db.query(
        DBMS.LitterIncident.camera_id,
        func.count(DBMS.LitterIncident.id)
    ).group_by(DBMS.LitterIncident.camera_id).all()

    return {
        "total_incidents": total,
        "vehicle_offenders": vehicles,
        "person_offenders": persons,
        "by_trash_type": {t: c for t, c in by_type},
        "by_camera": {cam: c for cam, c in by_camera}
    }