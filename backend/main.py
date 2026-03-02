from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import cv2
import threading
import collections
import time
import numpy as np
from fastapi.middleware.cors import CORSMiddleware
from model import LitterSchema, TrashLogSchema
from database import session, engine
import DBMS
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Date
from datetime import datetime, timedelta
import os

# Graceful shutdown flag
shutdown_event = threading.Event()

@asynccontextmanager
async def lifespan(app):
    yield
    # Signal all streaming generators to stop
    shutdown_event.set()

app = FastAPI(title="LitterWatch API", lifespan=lifespan)

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
    total_trash = db.query(DBMS.TrashLog).count()
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
        "total_trash":       total_trash,
        "vehicle_offenders": vehicles,
        "person_offenders":  persons,
        "by_trash_type":     {t: c for t, c in by_type},
        "by_camera":         {cam: c for cam, c in by_camera}
    }

@app.post("/trash_log")
def post_trash_logs(logs: list[TrashLogSchema], db: Session = Depends(get_db)):
    """Receives batched raw trash detections from detect.py."""
    db_logs = [DBMS.TrashLog(**log.model_dump()) for log in logs]
    db.add_all(db_logs)
    db.commit()
    return {"status": "ok", "inserted": len(db_logs)}

@app.get("/stats/history")
def get_stats_history(db: Session = Depends(get_db)):
    """Returns total incidents and total trash per day for the last 7 days."""
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    
    # Daily Incidents
    incidents_daily = db.query(
        cast(DBMS.LitterIncident.timestamp, Date).label('date'),
        func.count(DBMS.LitterIncident.id).label('count')
    ).filter(DBMS.LitterIncident.timestamp >= seven_days_ago)\
     .group_by(cast(DBMS.LitterIncident.timestamp, Date)).all()

    # Daily Trash
    trash_daily = db.query(
        cast(DBMS.TrashLog.timestamp, Date).label('date'),
        func.count(DBMS.TrashLog.id).label('count')
    ).filter(DBMS.TrashLog.timestamp >= seven_days_ago)\
     .group_by(cast(DBMS.TrashLog.timestamp, Date)).all()

    # Format perfectly for Chart.js
    dates = []
    # Build a list of the last 7 days as strings YYYY-MM-DD
    for i in range(6, -1, -1):
        d = (datetime.utcnow() - timedelta(days=i)).strftime('%Y-%m-%d')
        dates.append(d)

    incidents_dict = {str(row.date): row.count for row in incidents_daily}
    trash_dict = {str(row.date): row.count for row in trash_daily}

    return {
        "labels": dates,
        "incidents": [incidents_dict.get(d, 0) for d in dates],
        "trash": [trash_dict.get(d, 0) for d in dates]
    }


# ── MJPEG Stream Endpoints ─────────────────────────────────────
latest_frames = {}
frame_locks = collections.defaultdict(threading.Lock)
camera_last_active = {}  # Tracks the last ping time of each camera

def get_frame_generator(camera_id: str):
    try:
        while not shutdown_event.is_set():
            lock = frame_locks[camera_id]
            with lock:
                frame = latest_frames.get(camera_id)
                
            if frame is None:
                time.sleep(0.1)
                continue
                
            _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
            frame_bytes = jpeg.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
    except GeneratorExit:
        pass  # Client disconnected or server shut down — clean exit

@app.get("/stream/{camera_id}")
def video_stream(camera_id: str):
    return StreamingResponse(
        get_frame_generator(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@app.post("/frame/{camera_id}")
async def receive_frame(camera_id: str, request: Request):
    """detect.py posts current frame here"""
    body = await request.body()
    nparr = np.frombuffer(body, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    lock = frame_locks[camera_id]
    with lock:
        latest_frames[camera_id] = frame
    
    # Update last active time for this camera
    camera_last_active[camera_id] = datetime.utcnow()
        
    return {"status": "ok"}

@app.get("/cameras/active")
def get_active_cameras():
    """Returns cameras that sent a frame in the last 30 seconds."""
    now = datetime.now()
    active_cams = []
    
    for cam_id, last_time in camera_last_active.items():
        if (now - last_time).total_seconds() <= 30:
            active_cams.append({
                "id": cam_id,
                "status": "Active",
                "last_ping": last_time.isoformat()
            })
            
    return {"cameras": active_cams}

# ── Serve Frontend ─────────────────────────────────────────────
# IMPORTANT: This must be LAST so all API routes take priority.
# html=True means it auto-serves index.html for the root URL.
BASE_DIR_FRONTEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")
app.mount("/", StaticFiles(directory=BASE_DIR_FRONTEND, html=True), name="frontend")