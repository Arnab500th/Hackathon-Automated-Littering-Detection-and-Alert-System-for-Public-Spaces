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
import asyncio
import os

# Graceful shutdown flag
shutdown_event = threading.Event()

@asynccontextmanager
async def lifespan(app):
    yield
    # Signal all streaming generators to stop
    shutdown_event.set()

app = FastAPI(title="TRACE API", lifespan=lifespan)

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
async def post_trash_logs(request: Request, db: Session = Depends(get_db)):
    """
    Accepts detect.py batch format:
      {"timestamp": "...", "camera_id": "CAM_01", "counts": {"Bottle": 3}}
    OR legacy list: [{timestamp, camera_id, trash_type}, ...]
    """
    body = await request.json()
    db_logs = []
    if isinstance(body, dict) and "counts" in body:
        ts        = datetime.fromisoformat(body["timestamp"])
        camera_id = body["camera_id"]
        for trash_type, count in body["counts"].items():
            for _ in range(count):
                db_logs.append(DBMS.TrashLog(timestamp=ts, camera_id=camera_id, trash_type=trash_type))
    elif isinstance(body, list):
        for item in body:
            db_logs.append(DBMS.TrashLog(
                timestamp  = datetime.fromisoformat(item["timestamp"]),
                camera_id  = item["camera_id"],
                trash_type = item["trash_type"],
            ))
    else:
        return {"status": "error", "detail": "unrecognised payload format"}
    db.add_all(db_logs)
    db.commit()
    return {"status": "ok", "inserted": len(db_logs)}

@app.get("/stats/history")
def get_stats_history(db: Session = Depends(get_db)):
    """Returns total incidents and total trash per day for the last 7 days."""
    from sqlalchemy import text
    seven_days_ago = datetime.now() - timedelta(days=7)

    dates = [
        (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        for i in range(6, -1, -1)
    ]

    # cast(timestamp, Date) is broken in SQLite — use strftime instead
    incidents_raw = db.execute(text("""
        SELECT strftime('%Y-%m-%d', timestamp) AS day, COUNT(id) AS cnt
        FROM incidents
        WHERE timestamp >= :since
        GROUP BY day
    """), {"since": seven_days_ago.isoformat()}).fetchall()

    trash_raw = db.execute(text("""
        SELECT strftime('%Y-%m-%d', timestamp) AS day, COUNT(id) AS cnt
        FROM trash_log
        WHERE timestamp >= :since
        GROUP BY day
    """), {"since": seven_days_ago.isoformat()}).fetchall()

    incidents_dict = {row[0]: row[1] for row in incidents_raw}
    trash_dict     = {row[0]: row[1] for row in trash_raw}

    return {
        "labels":    dates,
        "incidents": [incidents_dict.get(d, 0) for d in dates],
        "trash":     [trash_dict.get(d, 0)     for d in dates],
    }


@app.get("/stats/today")
def get_stats_today(db: Session = Depends(get_db)):
    """Returns today's counts only — used by the dashboard stat cards."""
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    total   = db.query(DBMS.LitterIncident).filter(DBMS.LitterIncident.timestamp >= today_start).count()
    trash   = db.query(DBMS.TrashLog).filter(DBMS.TrashLog.timestamp >= today_start).count()
    vehicles = db.query(DBMS.LitterIncident).filter(
        DBMS.LitterIncident.timestamp >= today_start,
        DBMS.LitterIncident.offender_type == "vehicle"
    ).count()
    persons = db.query(DBMS.LitterIncident).filter(
        DBMS.LitterIncident.timestamp >= today_start,
        DBMS.LitterIncident.offender_type == "person"
    ).count()
    by_type = db.query(
        DBMS.LitterIncident.trash_type,
        func.count(DBMS.LitterIncident.id)
    ).filter(DBMS.LitterIncident.timestamp >= today_start)     .group_by(DBMS.LitterIncident.trash_type).all()
    return {
        "total_incidents":   total,
        "total_trash":       trash,
        "vehicle_offenders": vehicles,
        "person_offenders":  persons,
        "by_trash_type":     {t: c for t, c in by_type},
        "date":              today_start.strftime('%Y-%m-%d'),
    }


@app.get("/cameras/config")
def get_cameras_config():
    """Returns CAMERA_CONFIG from config.py so the frontend can auto-populate streams."""
    from ml_pipeline.config import CAMERA_CONFIG
    return [{"id": cam["id"], "label": cam["label"]} for cam in CAMERA_CONFIG]


# ── MJPEG Stream Endpoints ─────────────────────────────────────
# Store raw JPEG bytes directly — no re-encode on the way out.
# Each camera gets an asyncio.Event so the generator wakes up
# immediately when a new frame arrives instead of polling every 33ms.
latest_frames: dict[str, bytes] = {}          # camera_id -> raw JPEG bytes
frame_events:  dict[str, asyncio.Event] = {}  # camera_id -> new-frame signal
camera_last_active = {}                        # camera_id -> datetime

def _get_event(camera_id: str) -> asyncio.Event:
    if camera_id not in frame_events:
        frame_events[camera_id] = asyncio.Event()
    return frame_events[camera_id]

async def get_frame_generator(camera_id: str):
    try:
        while not shutdown_event.is_set():
            event = _get_event(camera_id)
            try:
                # Wait up to 5s for a new frame — wakes instantly when one arrives
                await asyncio.wait_for(asyncio.shield(event.wait()), timeout=5.0)
            except asyncio.TimeoutError:
                continue  # no frame yet — loop and wait again

            # Grab the current JPEG bytes and immediately clear the event
            # so the next frame will trigger a fresh wake-up
            jpeg_bytes = latest_frames.get(camera_id)
            event.clear()

            if jpeg_bytes is None:
                continue

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg_bytes + b'\r\n')
    except GeneratorExit:
        pass  # Client disconnected — clean exit

@app.get("/stream/{camera_id}")
async def video_stream(camera_id: str):
    return StreamingResponse(
        get_frame_generator(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@app.post("/frame/{camera_id}")
async def receive_frame(camera_id: str, request: Request):
    """
    detect.py POSTs a JPEG-encoded frame here.
    We store the raw bytes directly — no decode/re-encode needed.
    The asyncio.Event wakes all browser clients for this camera instantly.
    """
    jpeg_bytes = await request.body()
    latest_frames[camera_id] = jpeg_bytes
    camera_last_active[camera_id] = datetime.now()

    # Signal all waiting stream generators that a new frame is ready
    event = _get_event(camera_id)
    event.set()

    return {"status": "ok"}

@app.get("/cameras/active")
def get_active_cameras(db: Session = Depends(get_db)):
    """
    Returns cameras active in last 30s with DB aggregates, priority, and zone.
    priority  — live value stored by POST /camera/priority/{camera_id}
    zone_name — derived from camera GPS vs HIGH_SENSITIVITY_ZONES in config
    """
    now = datetime.now()
    active_cams = []

    try:
        try:
            from ml_pipeline.config import CAMERA_CONFIG
        except ImportError:
            from ml_pipeline.config import CAMERA_CONFIG
        cam_coords = {c["id"]: (c.get("lat", 0.0), c.get("lng", 0.0)) for c in CAMERA_CONFIG}
    except Exception:
        cam_coords = {}

    def get_zone(cam_id):
        try:
            try:
                from ml_pipeline.geo import in_high_sensitivity_zone
            except ImportError:
                from ml_pipeline.geo import in_high_sensitivity_zone
            lat, lng = cam_coords.get(cam_id, (0.0, 0.0))
            return in_high_sensitivity_zone(lat, lng)
        except Exception:
            return None

    for cam_id, last_time in camera_last_active.items():
        if (now - last_time).total_seconds() <= 30:
            total_trash = db.query(DBMS.TrashLog).filter(DBMS.TrashLog.camera_id == cam_id).count()
            total_persons = db.query(DBMS.LitterIncident).filter(
                DBMS.LitterIncident.camera_id == cam_id,
                DBMS.LitterIncident.offender_type == "person",
            ).count()
            total_vehicles = db.query(DBMS.LitterIncident).filter(
                DBMS.LitterIncident.camera_id == cam_id,
                DBMS.LitterIncident.offender_type == "vehicle",
            ).count()

            active_cams.append({
                "id":             cam_id,
                "status":         "Active",
                "last_ping":      last_time.isoformat(),
                "total_trash":    total_trash,
                "total_persons":  total_persons,
                "total_vehicles": total_vehicles,
                "priority":       camera_priority.get(cam_id, "LOW"),
                "zone_name":      get_zone(cam_id),
            })

    return {"cameras": active_cams}


# detect.py POSTs current priority here so the dashboard reflects it live
camera_priority: dict[str, str] = {}

@app.post("/camera/priority/{camera_id}")
async def update_priority(camera_id: str, request: Request):
    body = await request.json()
    camera_priority[camera_id] = body.get("priority", "LOW")
    return {"status": "ok"}

@app.get("/stats/camera/{cam_id}")
def get_camera_stats(cam_id: str, db: Session = Depends(get_db)):
    """
    Returns all-time AND today-only stats for a single camera.
    Used by the Live Stats tab to populate per-camera detail cards.
    """
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    # ── All-time ──────────────────────────────────────────────
    all_trash     = db.query(DBMS.TrashLog).filter(DBMS.TrashLog.camera_id == cam_id).count()
    all_persons   = db.query(DBMS.LitterIncident).filter(
        DBMS.LitterIncident.camera_id == cam_id,
        DBMS.LitterIncident.offender_type == "person"
    ).count()
    all_vehicles  = db.query(DBMS.LitterIncident).filter(
        DBMS.LitterIncident.camera_id == cam_id,
        DBMS.LitterIncident.offender_type == "vehicle"
    ).count()
    all_incidents = db.query(DBMS.LitterIncident).filter(
        DBMS.LitterIncident.camera_id == cam_id
    ).count()
    by_type_all   = db.query(
        DBMS.LitterIncident.trash_type,
        func.count(DBMS.LitterIncident.id)
    ).filter(DBMS.LitterIncident.camera_id == cam_id)\
     .group_by(DBMS.LitterIncident.trash_type).all()

    # ── Today only ────────────────────────────────────────────
    today_trash     = db.query(DBMS.TrashLog).filter(
        DBMS.TrashLog.camera_id == cam_id,
        DBMS.TrashLog.timestamp >= today_start
    ).count()
    today_persons   = db.query(DBMS.LitterIncident).filter(
        DBMS.LitterIncident.camera_id == cam_id,
        DBMS.LitterIncident.offender_type == "person",
        DBMS.LitterIncident.timestamp >= today_start
    ).count()
    today_vehicles  = db.query(DBMS.LitterIncident).filter(
        DBMS.LitterIncident.camera_id == cam_id,
        DBMS.LitterIncident.offender_type == "vehicle",
        DBMS.LitterIncident.timestamp >= today_start
    ).count()
    today_incidents = db.query(DBMS.LitterIncident).filter(
        DBMS.LitterIncident.camera_id == cam_id,
        DBMS.LitterIncident.timestamp >= today_start
    ).count()
    by_type_today   = db.query(
        DBMS.LitterIncident.trash_type,
        func.count(DBMS.LitterIncident.id)
    ).filter(
        DBMS.LitterIncident.camera_id == cam_id,
        DBMS.LitterIncident.timestamp >= today_start
    ).group_by(DBMS.LitterIncident.trash_type).all()

    return {
        "camera_id": cam_id,
        "date":      today_start.strftime('%Y-%m-%d'),
        "all_time": {
            "total_trash":     all_trash,
            "total_persons":   all_persons,
            "total_vehicles":  all_vehicles,
            "total_incidents": all_incidents,
            "by_trash_type":   {t: c for t, c in by_type_all},
        },
        "today": {
            "total_trash":     today_trash,
            "total_persons":   today_persons,
            "total_vehicles":  today_vehicles,
            "total_incidents": today_incidents,
            "by_trash_type":   {t: c for t, c in by_type_today},
        },
    }


# ── Serve Frontend ─────────────────────────────────────────────
# IMPORTANT: This must be LAST so all API routes take priority.
# html=True means it auto-serves index.html for the root URL.
BASE_DIR_FRONTEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")
app.mount("/", StaticFiles(directory=BASE_DIR_FRONTEND, html=True), name="frontend")