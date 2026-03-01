# config.py

SOURCE =r"data\test_videos\test_vid_2.mp4"  # video file or 0 for webcam

VEHICLE_CLASSES = [2, 3, 5, 7]  # YOLO: car, motorcycle, bus, truck

# Detection confidence thresholds
PERSON_CONF        = 0.40   # 40% - person/vehicle confidence
TRASH_CONF         = 0.10   # 20% - trash confidence

# Event logic thresholds
PROXIMITY_THRESHOLD  = 300   # pixels - max distance between trash and suspect
MEMORY_FRAME_COUNT   = 30    # frames before same trash location can re-trigger
SKIP_FRAMES          = 1     # process every Nth frame

# State machine thresholds
CARRY_DISTANCE     = 150   # pixels - person this close = carrying object
SEPARATION_FRAMES  = 8      # frames separated before marking stationary
STATIONARY_PIXELS  = 15     # pixels moved - less than this = not moving
ABANDON_DISTANCE   = 200    # pixels - person this far = abandoned object
CANCEL_DISTANCE    = 80     # pixels - person returns this close = cancelled
OWNER_MATCH_THRESHOLD = 120  # pixels - max distance to consider same person for cancellation

# Storage
SNAPSHOT_DIR = r"data\snapshots"

# Camera
CAMERA_ID = "CAM_01"


BACKEND_URL = "http://localhost:8000"


