# config.py — TRACE unified configuration

# ── Multi-camera registry ─────────────────────────────────────
# Add one entry per camera.
# source: int (webcam index), file path string, or RTSP URL string

CAMERA_CONFIG = [
    {"id": "CAM_01", "source": 0, "label": "Front Gate", "lat": 22.5626, "lng": 88.3511},
    {"id": "CAM_02", "source": r"data\test_videos\test_vid_12.mp4", "label": "test", "lat": 22.5553, "lng": 88.3514},
    {"id": "CAM_03", "source": 1 , "label": "Back Entrance", "lat": 22.5448, "lng": 88.3426},
]
#r"rtsp://10.149.9.188:8080/h264_ulaw.sdp"
# ── Municipality offices ──────────────────────────────────────
# When a litter event fires, the system finds the nearest office
# using Haversine distance and sends the WhatsApp alert there.
# Ph_no is no longer on individual cameras — it lives here.
# Add as many offices as needed — one per ward/zone.
MUNICIPALITY_OFFICES = [
    {"name": "Ward 1",  "Ph_no": "+919475561298", "lat": 22.5679, "lng": 88.3468},
    {"name": "Ward 2",  "Ph_no": "+918597797117", "lat": 22.5520, "lng": 88.3520},
    {"name": "Ward 3",  "Ph_no": "+919064569402", "lat": 22.5410, "lng": 88.3400},
]

# ── High sensitivity zones ────────────────────────────────────
# Cameras inside these zones never drop below MEDIUM priority.
# radius_m is the geofence radius in metres around the centre point.
HIGH_SENSITIVITY_ZONES = [
    {"name": "School Zone",    "lat": 22.5548, "lng": 88.3522, "radius_m": 200},
    {"name": "Heritage Site",  "lat": 22.5630, "lng": 88.3515, "radius_m": 150},
    {"name": "Railway Station","lat": 22.5448, "lng": 88.3426, "radius_m": 300},
]

# ── Detection ─────────────────────────────────────────────────
VEHICLE_CLASSES = [2, 3, 5, 7]  # YOLO COCO IDs: car, motorcycle, bus, truck
PERSON_CONF     = 0.40           # confidence threshold for persons/vehicles
TRASH_CONF      = 0.15           # confidence threshold for trash (low = max recall)

# ── State machine thresholds ──────────────────────────────────
CARRY_DISTANCE        = 150   # px — person this close = carrying the trash
SEPARATION_FRAMES     = 30     # frames separated before checking stationary
STATIONARY_PIXELS     = 15    # px — movement below this = object not moving
ABANDON_DISTANCE      = 250   # px — person this far = abandoned
CANCEL_DISTANCE       = 100    # px — person returns this close = cancelled
OWNER_MATCH_THRESHOLD = 120   # px — max shift to consider same person returning

# ── Memory / skip ─────────────────────────────────────────────
PROXIMITY_THRESHOLD = 300   # px — max distance between trash and suspect
MEMORY_FRAME_COUNT  = 150    # frames before stale track is purged
SKIP_FRAMES         = 1     # run person detection every N frames (1 = every frame)

# ── Storage ───────────────────────────────────────────────────
SNAPSHOT_DIR = r"data\snapshots"

# ── Backend ───────────────────────────────────────────────────
BACKEND_URL = "http://localhost:8000"

# ── Timing ────────────────────────────────────────────────────
BATCH_INTERVAL = 10   # seconds between trash log batch pushes to backend

#batch levelling
PRIORITY_HIGH_SKIP   = 1    # every frame
PRIORITY_MEDIUM_SKIP = 5    # every 3rd frame
PRIORITY_LOW_SKIP    = 8    # every 6th frame

PRIORITY_HIGH_WINDOW   = 5    # seconds — trash this recent = HIGH
PRIORITY_MEDIUM_WINDOW = 30   # seconds — trash this recent = MEDIUM
                               # older than 30s = LOW