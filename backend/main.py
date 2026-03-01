from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from model import LitterSchema
from database import session, engine
import DBMS
from sqlalchemy.orm import Session
from sqlalchemy import func
import os

app = FastAPI(title="LitterWatch API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create tables on startup
DBMS.Base.metadata.create_all(bind=engine)

# Serve snapshots - path relative to this file so it always works
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT_PATH = os.path.join(BASE_DIR, "..", "data", "snapshots")
os.makedirs(SNAPSHOT_PATH, exist_ok=True)
app.mount("/snapshots", StaticFiles(directory=SNAPSHOT_PATH), name="snapshots")

def get_db():
    db = session()
    try:
        yield db
    finally:
        db.close()

@app.get("/")
def home():
    return {"status": "LitterWatch API running"}

@app.get("/incidents")
def get_incidents(db: Session = Depends(get_db)):
    return db.query(DBMS.LitterIncident).order_by(
        DBMS.LitterIncident.timestamp.desc()
    ).all()

@app.get("/incidents/recent")
def get_recent(limit: int = 10, db: Session = Depends(get_db)):
    return db.query(DBMS.LitterIncident).order_by(
        DBMS.LitterIncident.timestamp.desc()
    ).limit(limit).all()

@app.post("/incidents")
def post_incident(litter: LitterSchema, db: Session = Depends(get_db)):
    new_incident = DBMS.LitterIncident(**litter.model_dump())
    db.add(new_incident)

    if litter.offender_type.lower() == "vehicle" and litter.license_plate:
        existing = db.query(DBMS.Vehicle).filter(
            DBMS.Vehicle.license_plate == litter.license_plate
        ).first()
        if existing:
            existing.last_seen      = litter.timestamp
            existing.incident_count += 1
        else:
            db.add(DBMS.Vehicle(
                license_plate  = litter.license_plate,
                first_seen     = litter.timestamp,
                last_seen      = litter.timestamp,
                incident_count = 1
            ))

    db.commit()
    db.refresh(new_incident)
    return new_incident

@app.get("/vehicles")
def get_vehicles(db: Session = Depends(get_db)):
    return db.query(DBMS.Vehicle).order_by(
        DBMS.Vehicle.incident_count.desc()
    ).all()

@app.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    total    = db.query(DBMS.LitterIncident).count()
    vehicles = db.query(DBMS.LitterIncident).filter(
        DBMS.LitterIncident.offender_type == "vehicle"
    ).count()
    persons  = db.query(DBMS.LitterIncident).filter(
        DBMS.LitterIncident.offender_type == "person"
    ).count()
    by_type = db.query(
        DBMS.LitterIncident.trash_type,
        func.count(DBMS.LitterIncident.id)
    ).group_by(DBMS.LitterIncident.trash_type).all()
    by_camera = db.query(
        DBMS.LitterIncident.camera_id,
        func.count(DBMS.LitterIncident.id)
    ).group_by(DBMS.LitterIncident.camera_id).all()
    return {
        "total_incidents":   total,
        "vehicle_offenders": vehicles,
        "person_offenders":  persons,
        "by_trash_type":     {t: c for t, c in by_type},
        "by_camera":         {cam: c for cam, c in by_camera}
    }