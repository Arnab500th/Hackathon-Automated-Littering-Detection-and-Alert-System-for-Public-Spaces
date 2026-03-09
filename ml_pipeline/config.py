# config.py — TRACE unified configuration

# ── Multi-camera registry ─────────────────────────────────────
# Add one entry per camera.
# source: int (webcam index), file path string, or RTSP URL string
# Run all cameras:   python detect.py
# Run one camera:    python detect.py --cam 0   (index into this list)
CAMERA_CONFIG = [
    {"id": "CAM_01", "source": 1,                             "label": "Front Gate"},
    {"id": "CAM_02", "source": r"data\test_videos\test_vid_12.mp4",  "label": "test"},
    {"id": "CAM_03", "source":r"rtsp://192.168.1.3:8080/h264_ulaw.sdp" ,"label": "Back Entrance"},
]

# ── Detection ─────────────────────────────────────────────────
VEHICLE_CLASSES = [2, 3, 5, 7]  # YOLO COCO IDs: car, motorcycle, bus, truck
PERSON_CONF     = 0.40           # confidence threshold for persons/vehicles
TRASH_CONF      = 0.10           # confidence threshold for trash (low = max recall)

# ── State machine thresholds ──────────────────────────────────
CARRY_DISTANCE        = 150   # px — person this close = carrying the trash
SEPARATION_FRAMES     = 3     # frames separated before checking stationary
STATIONARY_PIXELS     = 15    # px — movement below this = object not moving
ABANDON_DISTANCE      = 200   # px — person this far = abandoned
CANCEL_DISTANCE       = 80    # px — person returns this close = cancelled
OWNER_MATCH_THRESHOLD = 120   # px — max shift to consider same person returning

# ── Memory / skip ─────────────────────────────────────────────
PROXIMITY_THRESHOLD = 300   # px — max distance between trash and suspect
MEMORY_FRAME_COUNT  = 90    # frames before stale track is purged
SKIP_FRAMES         = 1     # run person detection every N frames (1 = every frame)

# ── Storage ───────────────────────────────────────────────────
SNAPSHOT_DIR = r"data\snapshots"

# ── Backend ───────────────────────────────────────────────────
BACKEND_URL = "http://localhost:8000"

# ── Timing ────────────────────────────────────────────────────
BATCH_INTERVAL = 10   # seconds between trash log batch pushes to backend