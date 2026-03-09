import cv2
import time
import os
import sys
import queue
import threading
import argparse
import requests
from datetime import datetime
from ultralytics import YOLO
import uuid
from config import *

# ── Real module imports ───────────────────────────────────────
try:
    from ocr_module import read_license_plate_from_frame
    OCR_AVAILABLE = True
except ImportError:
    print("[WARN] ocr_module not found - OCR disabled")
    OCR_AVAILABLE = False
    def read_license_plate_from_frame(frame, box):
        return None

try:
    from api_client import post_incident
    API_AVAILABLE = True
except ImportError:
    print("[WARN] api_client not found - backend posting disabled")
    API_AVAILABLE = False
    def post_incident(event):
        print("[POST INCIDENT]", event)


# ── Camera selection ──────────────────────────────────────────
# Run one camera:   python detect.py --cam 0
# Run all cameras:  python detect.py
parser = argparse.ArgumentParser(description="TRACE detection pipeline")
parser.add_argument(
    "--cam", type=int, default=None,
    help="Index into CAMERA_CONFIG to run (default: run all)",
)
args = parser.parse_args()

if args.cam is not None:
    if args.cam >= len(CAMERA_CONFIG):
        print(f"[ERROR] --cam {args.cam} out of range. "
              f"Config has {len(CAMERA_CONFIG)} cameras (0-{len(CAMERA_CONFIG)-1}).")
        sys.exit(1)
    _ACTIVE_CAMERAS = [CAMERA_CONFIG[args.cam]]
else:
    _ACTIVE_CAMERAS = CAMERA_CONFIG


# ── Stream sender (one per camera, fully independent) ─────────
class StreamSender:
    """
    Dedicated daemon thread per camera.
    push_frame() just swaps a pointer — zero blocking in detection loop.
    Sender thread encodes + POSTs at its own pace, always sends latest frame.
    """
    def __init__(self, camera_id: str):
        self.camera_id = camera_id
        self._frame    = None
        self._lock     = threading.Lock()
        self._running  = True
        self._thread   = threading.Thread(
            target=self._run, daemon=True,
            name=f"StreamSender-{camera_id}"
        )
        self._thread.start()

    def _run(self):
        last_sent = None
        while self._running:
            with self._lock:
                frame = self._frame
            if frame is None or frame is last_sent:
                time.sleep(0.005)
                continue
            last_sent = frame
            try:
                # Resize to 854x480 (or scale to 480p) before encoding —
                # keeps POST payload small without losing useful detail on
                # the dashboard stream.
                h, w = frame.shape[:2]
                if h > 480:
                    scale        = 480 / h
                    stream_frame = cv2.resize(frame, (int(w * scale), 480),
                                              interpolation=cv2.INTER_LINEAR)
                else:
                    stream_frame = frame
                # Encode once here — main.py stores raw JPEG bytes and
                # forwards directly to the browser (no second encode).
                _, jpeg = cv2.imencode(".jpg", stream_frame,
                                       [cv2.IMWRITE_JPEG_QUALITY, 60])
                requests.post(
                    f"{BACKEND_URL}/frame/{self.camera_id}",
                    data=jpeg.tobytes(),
                    headers={"Content-Type": "application/octet-stream"},
                    timeout=0.5,
                )
            except Exception:
                pass

    def push_frame(self, frame):
        with self._lock:
            self._frame = frame

    def stop(self):
        self._running = False


def post_trash_log(trash_counts, camera_id):
    if not trash_counts:
        return
    def _send():
        try:
            requests.post(
                f"{BACKEND_URL}/trash_log",
                json={"timestamp": datetime.now().isoformat(),
                      "camera_id": camera_id,
                      "counts":    trash_counts},
                timeout=2.0,
            )
        except Exception:
            pass
    threading.Thread(target=_send, daemon=True).start()


# ── Folder setup ──────────────────────────────────────────────
os.makedirs(f"{SNAPSHOT_DIR}/persons",  exist_ok=True)
os.makedirs(f"{SNAPSHOT_DIR}/vehicles", exist_ok=True)
os.makedirs(f"{SNAPSHOT_DIR}/full",     exist_ok=True)


# ── Per-camera state container ────────────────────────────────
class CameraContext:
    def __init__(self, camera_id: str):
        self.camera_id            = camera_id
        self.tracked_trash        = {}
        self.object_states        = {}
        self.smoothed_boxes       = {}
        self.smoothed_persons     = {}
        self.last_drawn_persons   = []
        self.last_drawn_vehicles  = []
        self.last_drawn_trash     = []
        self.last_known_persons   = []
        self.last_known_vehicles  = []
        self.current_trash_counts = {}
        # Per‑batch aggregated counts for new, unique trash objects
        self.max_trash_in_batch   = {}
        # Track IDs we have already logged to the backend (avoid double-counting)
        self.seen_trash_ids       = set()
        # Per-frame map of "new this frame" trash counts, used to build batches
        self.latest_new_trash_counts = {}
        self.last_batch_time      = time.time()
        self.frame_count          = 0
        self.prev_time            = 0.0



# ── Helper functions ──────────────────────────────────────────
def get_grid_key(box):
    cx = (box[0] + box[2]) // 2
    cy = (box[1] + box[3]) // 2
    return (int(cx) // 50, int(cy) // 50)


def get_distance(box_a, box_b):
    ax = (box_a[0] + box_a[2]) / 2;  ay = (box_a[1] + box_a[3]) / 2
    bx = (box_b[0] + box_b[2]) / 2;  by = (box_b[1] + box_b[3]) / 2
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def boxes_overlap(box_a, box_b):
    return not (
        box_a[2] < box_b[0] or box_a[0] > box_b[2] or
        box_a[3] < box_b[1] or box_a[1] > box_b[3]
    )


def nearest_suspect(trash_box, persons, vehicles):
    # persons  = [(track_id, box), ...]
    # vehicles = [(track_id, box), ...]
    suspects = [("person",  pid,  b) for pid, b  in persons] +                [("vehicle", vid,  b) for vid, b  in vehicles]
    if not suspects:
        return None, None, None
    nearest = min(suspects, key=lambda s: get_distance(trash_box, s[2]))
    return nearest[0], nearest[1], nearest[2]   # type, track_id, box


def get_box_center(box):
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def box_movement(box_a, box_b):
    ax, ay = get_box_center(box_a);  bx, by = get_box_center(box_b)
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def smooth_coords(store, key, new_box, alpha=0.5):
    if key not in store:
        store[key] = new_box
        return new_box
    old    = store[key]
    result = [alpha * new_box[i] + (1 - alpha) * old[i] for i in range(4)]
    store[key] = result
    return result


def is_same_person(current_track_id, current_box, owner_track_id, owner_last_pos):
    """
    Primary check:  compare ByteTrack IDs — fast and exact.
    Fallback check: positional distance — used when either ID is None
                    (ByteTrack hasn't confirmed the track yet, or the person
                    briefly left the frame and got a new ID on re-entry).
    """
    # Both IDs known and valid → use identity directly
    if current_track_id is not None and owner_track_id is not None:
        return current_track_id == owner_track_id
    # At least one ID missing → fall back to position heuristic
    if owner_last_pos is None:
        return False
    cx, cy = get_box_center(current_box)
    ox, oy = owner_last_pos
    return ((cx - ox) ** 2 + (cy - oy) ** 2) ** 0.5 < OWNER_MATCH_THRESHOLD


def save_snapshot(frame, suspect_box, suspect_type, trash_label):
    uid       = uuid.uuid4().hex[:8]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    h, w      = frame.shape[:2]
    x1 = max(0, int(suspect_box[0]));  y1 = max(0, int(suspect_box[1]))
    x2 = min(w, int(suspect_box[2]));  y2 = min(h, int(suspect_box[3]))
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return None, None
    folder    = "persons" if suspect_type == "person" else "vehicles"
    img_path  = f"{SNAPSHOT_DIR}/{folder}/{trash_label}_{timestamp}_{uid}.jpg"
    full_path = f"{SNAPSHOT_DIR}/full/{trash_label}_{timestamp}_{uid}_full.jpg"
    cv2.imwrite(img_path, crop)
    cv2.imwrite(full_path, frame)
    print(f"[SNAPSHOT] Saved: {img_path}")
    return img_path, full_path


def draw_rect(frame, box, label, color):
    x1, y1, x2, y2 = map(int, box)
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw, y1), color, -1)
    cv2.putText(frame, label, (x1, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)


STATE_COLORS = {
    "UNKNOWN":    (128, 128, 128),
    "CARRYING":   (0,   255, 255),
    "SEPARATION": (0,   165, 255),
    "STATIONARY": (0,   0,   255),
    "ALERTED":    (0,   0,   128),
    "CANCELLED":  (0,   255,   0),
}


# ── State machine ─────────────────────────────────────────────
def update_object_state(ctx, key, current_box, prev_box, persons, vehicles, frame):
    if key not in ctx.object_states:
        ctx.object_states[key] = {
            "state": "UNKNOWN", "box": current_box,
            "owner_box": None, "owner_last_pos": None, "owner_track_id": None,
            "sep_frame": None, "prev_box": prev_box,
            "label": None, "confidence": 0.0,
            "first_seen": ctx.frame_count,
        }

    state_info = ctx.object_states[key]
    state      = state_info["state"]

    if state == "UNKNOWN":
        suspect_type, suspect_id, suspect_box = nearest_suspect(current_box, persons, vehicles)
        if suspect_box is not None:
            dist = get_distance(current_box, suspect_box)
            if dist < CARRY_DISTANCE or boxes_overlap(current_box, suspect_box):
                state_info["state"]          = "CARRYING"
                state_info["owner_box"]      = suspect_box
                state_info["owner_track_id"] = suspect_id   # save ByteTrack ID

    elif state == "CARRYING":
        suspect_type, suspect_id, suspect_box = nearest_suspect(current_box, persons, vehicles)
        if suspect_box is not None:
            state_info["owner_box"]      = suspect_box
            state_info["owner_track_id"] = suspect_id   # keep ID updated each frame
            state_info["owner_last_pos"] = get_box_center(suspect_box)
        if suspect_box is None or get_distance(current_box, suspect_box) > CARRY_DISTANCE:
            state_info["state"]          = "SEPARATION"
            state_info["sep_frame"]      = ctx.frame_count
            state_info["owner_last_pos"] = (
                get_box_center(state_info["owner_box"])
                if state_info["owner_box"] else None
            )

    elif state == "SEPARATION":
        suspect_type, suspect_id, suspect_box = nearest_suspect(current_box, persons, vehicles)
        if suspect_box is not None and get_distance(current_box, suspect_box) < CANCEL_DISTANCE:
            if is_same_person(suspect_id, suspect_box,
                              state_info.get("owner_track_id"),
                              state_info.get("owner_last_pos")):
                state_info["state"] = "CANCELLED"
                print("[CANCEL] Owner returned during separation")
                return None
            else:
                print("[INFO] Passerby near object during separation - ignoring")

        movement         = box_movement(current_box, prev_box)
        sep_frame        = state_info["sep_frame"] or ctx.frame_count
        frames_separated = ctx.frame_count - sep_frame
        if movement < STATIONARY_PIXELS and frames_separated >= SEPARATION_FRAMES:
            state_info["state"] = "STATIONARY"
            print(f"[STATE] Object STATIONARY after {frames_separated} frames")

    elif state == "STATIONARY":
        suspect_type, suspect_id, suspect_box = nearest_suspect(current_box, persons, vehicles)
        if suspect_box is not None and get_distance(current_box, suspect_box) < CANCEL_DISTANCE:
            if is_same_person(suspect_id, suspect_box,
                              state_info.get("owner_track_id"),
                              state_info.get("owner_last_pos")):
                state_info["state"] = "CANCELLED"
                print("[CANCEL] Owner returned to object")
                return None
            else:
                print("[INFO] Passerby near stationary object - not cancelling")

        person_gone = (
            suspect_box is None or
            get_distance(current_box, suspect_box) > ABANDON_DISTANCE
        )
        if person_gone:
            frames_on_ground  = ctx.frame_count - state_info.get("sep_frame", ctx.frame_count)
            seconds_on_ground = round(frames_on_ground / 30, 1)

            print(f"\n{'='*45}")
            print(f"  LITTER EVENT CONFIRMED  [{ctx.camera_id}]")
            print(f"  Label:     {state_info.get('label', 'Unknown')}")
            print(f"  On ground: {seconds_on_ground}s")
            print(f"  Time:      {datetime.now().strftime('%H:%M:%S')}")
            print(f"{'='*45}")

            snap_box  = state_info.get("owner_box") or suspect_box
            snap_type = suspect_type or "person"
            img_path = full_path = plate = None

            if snap_box is not None:
                img_path, full_path = save_snapshot(
                    frame, snap_box, snap_type, state_info.get("label", "trash")
                )
                if snap_type == "vehicle" and OCR_AVAILABLE:
                    plate = read_license_plate_from_frame(frame, snap_box)
                    if plate:
                        print(f"  Plate:     {plate}")

            state_info["state"] = "ALERTED"
            return {
                "timestamp":       datetime.now().isoformat(),
                "label":           state_info.get("label", "Unknown"),
                "suspect_type":    snap_type,
                "image_path":      img_path,
                "full_frame_path": full_path,
                "camera_id":       ctx.camera_id,
                "license_plate":   plate,
                "confidence":      state_info.get("confidence", 0.0),
                "dwell_seconds":   seconds_on_ground,
            }

    state_info["prev_box"] = state_info["box"]
    state_info["box"]      = current_box
    return None


def detect_litter(ctx, trash_boxes, trash_labels, trash_ids, persons, vehicles, frame):
    events = []
    for i, trash_box in enumerate(trash_boxes):
        label    = trash_labels[i]
        track_id = trash_ids[i]
        key      = track_id if track_id is not None else get_grid_key(trash_box)

        prev_box = ctx.object_states[key]["box"] if key in ctx.object_states else trash_box
        if key in ctx.object_states:
            ctx.object_states[key]["label"] = label

        event = update_object_state(ctx, key, trash_box, prev_box, persons, vehicles, frame)

        if key in ctx.object_states:
            ctx.object_states[key]["label"] = label
        if event is not None:
            events.append(event)
        ctx.tracked_trash[key] = ctx.frame_count

    for k in [k for k, v in ctx.tracked_trash.items()
              if ctx.frame_count - v > MEMORY_FRAME_COUNT * 3]:
        ctx.tracked_trash.pop(k, None)
        ctx.object_states.pop(k, None)
    return events


def run_trash_detection(ctx, frame, persons, vehicles, trash_model):
    trash_detection = trash_model.track(
        frame, persist=True, tracker="bytetrack.yaml", verbose=False
    )[0]

    trash_boxes = [];  trash_labels = [];  trash_ids = []
    ctx.last_drawn_trash  = []
    trash_type_counts = {}
    new_trash_counts = {}

    for box in trash_detection.boxes:
        conf   = float(box.conf[0])
        coords = box.xyxy[0].tolist()
        label  = trash_model.names[int(box.cls[0])]
        if conf < TRASH_CONF:
            continue

        trash_type_counts[label] = trash_type_counts.get(label, 0) + 1

        track_id = int(box.id[0]) if box.id is not None else None
        key      = track_id if track_id is not None else get_grid_key(coords)
        trash_boxes.append(coords);  trash_labels.append(label);  trash_ids.append(track_id)

        # Count only first appearance of each track_id once per camera lifetime
        if track_id is not None and track_id not in ctx.seen_trash_ids:
            new_trash_counts[label] = new_trash_counts.get(label, 0) + 1
            ctx.seen_trash_ids.add(track_id)

        if key in ctx.object_states:
            ctx.object_states[key]["confidence"] = conf

        smooth    = smooth_coords(ctx.smoothed_boxes, key, coords)
        state     = ctx.object_states.get(key, {}).get("state", "UNKNOWN")
        color     = STATE_COLORS.get(state, (225, 225, 225))
        id_str    = f"#{track_id}" if track_id else ""
        dwell_str = ""
        if state == "STATIONARY":
            sep_f     = ctx.object_states.get(key, {}).get("sep_frame", ctx.frame_count)
            dwell_str = f"|{int((ctx.frame_count - sep_f) / 30)}s"

        disp_label = f"{label}{id_str}|{state}{dwell_str}"
        draw_rect(frame, smooth, disp_label, color)
        ctx.last_drawn_trash.append((smooth, disp_label, color))

    ctx.current_trash_counts     = trash_type_counts
    ctx.latest_new_trash_counts  = new_trash_counts
    events = detect_litter(ctx, trash_boxes, trash_labels, trash_ids, persons, vehicles, frame)
    return events, trash_type_counts


def draw_hud(ctx, frame, fps, persons, vehicles, events, trash_type_counts):
    if events:
        cv2.rectangle(frame, (0, 0), (frame.shape[1]-1, frame.shape[0]-1), (0, 0, 255), 10)
        cv2.putText(frame, "LITTER CONFIRMED",
                    (frame.shape[1]//2 - 170, 65),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 255), 3)

    cv2.putText(frame, f"FPS: {fps:.1f}",            (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
    cv2.putText(frame, f"Persons: {len(persons)}",   (10, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1)
    cv2.putText(frame, f"Vehicles: {len(vehicles)}", (10, 72), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 1)
    cv2.putText(frame, f"Trash: {sum(trash_type_counts.values())}", (10, 92), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 1)

    y = 116
    state_counts = {}
    for s_data in ctx.object_states.values():
        s = s_data.get("state", "UNKNOWN")
        state_counts[s] = state_counts.get(s, 0) + 1
    for st, count in state_counts.items():
        color = STATE_COLORS.get(st, (200, 200, 200))
        cv2.putText(frame, f"  {st}: {count}", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
        y += 16

    y += 8
    cv2.putText(frame, "ON SCREEN:", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
    y += 18
    for trash_type, count in sorted(trash_type_counts.items()):
        cv2.putText(frame, f"  {trash_type}: {count}", (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
        y += 15


# ── Per-camera worker thread ──────────────────────────────────
# Does ALL detection work but ZERO cv2 GUI calls.
# Puts annotated frames into a queue for the main thread to display.

def camera_worker(cam_config, frame_queues, stop_event):
    camera_id = cam_config["id"]
    source    = cam_config["source"]
    cam_label = cam_config["label"]

    # Each thread loads its OWN model instances.
    # Required because ByteTrack persist=True keeps internal state per model object.
    # Sharing one model between threads would corrupt tracking across cameras.
    print(f"[{camera_id}] Loading models...")
    person_model = YOLO(r"ml_pipeline\weights\yolov8s.pt")
    trash_model  = YOLO(r"ml_pipeline\weights\taco_8s_v3.pt")
    print(f"[{camera_id}] Models loaded. Starting capture...")

    ctx           = CameraContext(camera_id)
    stream_sender = StreamSender(camera_id)

    vid = cv2.VideoCapture(source)
    if not vid.isOpened():
        print(f"[{camera_id}] ERROR: Cannot open source: {source}")
        # Return, not exit() — exit() would kill the whole process
        stream_sender.stop()
        return

    print(f"[TRACE] {camera_id} [{cam_label}] running")

    while not stop_event.is_set():
        res, frame = vid.read()
        if not res:
            print(f"[{camera_id}] Stream ended.")
            break

        ctx.frame_count += 1
        curr_time = time.time()
        fps = 1 / (curr_time - ctx.prev_time + 1e-9)
        ctx.prev_time = curr_time

        # ── Person / vehicle detection ─────────────────────────
        if ctx.frame_count % SKIP_FRAMES == 0:
            ctx.last_drawn_persons  = []
            ctx.last_drawn_vehicles = []
            persons  = []
            vehicles = []

            person_detection = person_model.track(
                frame, persist=True, tracker="bytetrack.yaml", verbose=False
            )[0]
            for box in person_detection.boxes:
                cls    = int(box.cls[0])
                conf   = float(box.conf[0])
                coords = box.xyxy[0].tolist()
                # ByteTrack assigns IDs after the first frame a track is confirmed.
                # box.id is None on the very first frame of a new detection.
                pid = int(box.id[0]) if box.id is not None else None
                if cls == 0 and conf > PERSON_CONF:
                    pkey   = get_grid_key(coords)
                    smooth = smooth_coords(ctx.smoothed_persons, pkey, coords)
                    id_str = f"#{pid}" if pid is not None else ""
                    label  = f"Person{id_str} {conf:.2f}"
                    persons.append((pid, coords))          # (track_id, box)
                    draw_rect(frame, smooth, label, (0, 255, 0))
                    ctx.last_drawn_persons.append((smooth, label))
                elif cls in VEHICLE_CLASSES and conf > PERSON_CONF:
                    vid_id = int(box.id[0]) if box.id is not None else None
                    id_str = f"#{vid_id}" if vid_id is not None else ""
                    label  = f"Vehicle{id_str} {conf:.2f}"
                    vehicles.append((vid_id, coords))      # (track_id, box)
                    draw_rect(frame, coords, label, (0, 165, 255))
                    ctx.last_drawn_vehicles.append((coords, label))
            ctx.last_known_persons  = persons
            ctx.last_known_vehicles = vehicles
        else:
            # Skipped frame: redraw last detections, use cached lists
            for coords, label in ctx.last_drawn_persons:
                draw_rect(frame, coords, label, (0, 255, 0))
            for coords, label in ctx.last_drawn_vehicles:
                draw_rect(frame, coords, label, (0, 165, 255))
            persons  = ctx.last_known_persons
            vehicles = ctx.last_known_vehicles

        # ── Trash detection + state machine ───────────────────
        events, trash_counts = run_trash_detection(
            ctx, frame, persons, vehicles, trash_model
        )

        if events:
            for event in events:
                threading.Thread(
                    target=post_incident,
                    args=(event,),
                    daemon=True,
                    name=f"IncidentPost-{camera_id}",
                ).start()

        # ── Batch trash log ───────────────────────────────────
        # Use only *new* unique objects (first time a track_id is seen)
        for t_type, count in ctx.latest_new_trash_counts.items():
            ctx.max_trash_in_batch[t_type] = ctx.max_trash_in_batch.get(t_type, 0) + count
        if curr_time - ctx.last_batch_time >= BATCH_INTERVAL:
            post_trash_log(ctx.max_trash_in_batch, camera_id)
            ctx.max_trash_in_batch = {}
            ctx.last_batch_time    = curr_time

        # ── Overlay ───────────────────────────────────────────
        draw_hud(ctx, frame, fps, persons, vehicles, events, trash_counts)

        # ── Push annotated frame to MJPEG backend stream ──────
        stream_sender.push_frame(frame)

        # ── Put frame in GUI queue (non-blocking, drop if full) ─
        q = frame_queues.get(camera_id)
        if q is not None:
            try:
                q.put_nowait(frame)
            except queue.Full:
                pass  # main thread is slow — drop, never block inference

    # Cleanup
    stream_sender.stop()
    vid.release()
    print(f"[{camera_id}] Stopped. Total frames: {ctx.frame_count}")


# ── Main thread: the ONLY place cv2 GUI calls are made ────────
# OpenCV requires imshow / waitKey / destroyAllWindows to run
# in the main thread on all platforms, especially Windows.

def main():
    if not _ACTIVE_CAMERAS:
        print("[ERROR] No cameras in CAMERA_CONFIG. Edit config.py.")
        sys.exit(1)

    print(f"[TRACE] Starting {len(_ACTIVE_CAMERAS)} camera(s):")
    for cam in _ACTIVE_CAMERAS:
        print(f"  [{cam['id']}]  {cam['label']}  source={cam['source']}")

    # One small queue per camera — bounded size so memory doesn't grow
    frame_queues = {cam["id"]: queue.Queue(maxsize=2) for cam in _ACTIVE_CAMERAS}
    stop_event   = threading.Event()

    # Start one worker thread per camera (daemon=False for clean join)
    threads = []
    for cam in _ACTIVE_CAMERAS:
        t = threading.Thread(
            target=camera_worker,
            args=(cam, frame_queues, stop_event),
            daemon=False,
            name=f"CamWorker-{cam['id']}",
        )
        t.start()
        threads.append(t)

    print("[TRACE] All cameras started. Press Q in any window to quit.\n")

    # GUI loop — runs entirely in the main thread
    while True:
        for cam in _ACTIVE_CAMERAS:
            cam_id = cam["id"]
            try:
                frame = frame_queues[cam_id].get_nowait()
                cv2.imshow(f"TRACE - {cam_id} [{cam['label']}]", frame)
            except queue.Empty:
                pass  # no new frame for this camera yet

        # Single waitKey per loop tick — handles all windows at once
        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("[TRACE] Q pressed — stopping...")
            stop_event.set()
            break

        # If all worker threads have finished (e.g. all files ended), exit
        if not any(t.is_alive() for t in threads):
            print("[TRACE] All streams ended.")
            break

          # avoid burning CPU in the loop

    # Signal stop and wait for clean shutdown
    stop_event.set()
    for t in threads:
        t.join(timeout=8)

    cv2.destroyAllWindows()
    print("[TRACE] Session ended.")


if __name__ == "__main__":
    main()