import cv2
import time
import os
from datetime import datetime
from ultralytics import YOLO
import uuid
from config import *

# ── Placeholder helpers ───────────────────────────────────────
# These stubs exist to satisfy references in the main logic.
# They can be replaced with real implementations later.

def read_plate_from_frame(frame, box):
    """Return license plate string if OCR succeeds (stub)."""
    # TODO: implement actual plate recognition
    return None


def post_incident(event):
    """Notify backend or log incident (stub)."""
    # In production this would send the event to a server or database
    print("[POST INCIDENT]", event)



# ── Models ────────────────────────────────────────────────────
person_model = YOLO(r"ml_pipeline\weights\yolov8s.pt")
trash_model  = YOLO(r"ml_pipeline\weights\taco_8s_v3.pt")

# ── Folder setup ──────────────────────────────────────────────
os.makedirs(f"{SNAPSHOT_DIR}/persons",  exist_ok=True)
os.makedirs(f"{SNAPSHOT_DIR}/vehicles", exist_ok=True)
os.makedirs(f"{SNAPSHOT_DIR}/full",     exist_ok=True)

# ── State variables ───────────────────────────────────────────
tracked_trash    = {}
object_states    = {}
smoothed_boxes   = {}
smoothed_persons = {}

last_drawn_persons  = []
last_drawn_vehicles = []
last_drawn_trash    = []

# Persons/vehicles from last detection frame
# Used on skipped frames so state machine still runs
last_known_persons  = []
last_known_vehicles = []

frame_count = 0
prev_time   = 0


# ── Helper functions ──────────────────────────────────────────

def get_grid_key(box):
    cx = (box[0] + box[2]) // 2
    cy = (box[1] + box[3]) // 2
    return (int(cx) // 50, int(cy) // 50)

def get_distance(box_a, box_b):
    ax = (box_a[0] + box_a[2]) / 2
    ay = (box_a[1] + box_a[3]) / 2
    bx = (box_b[0] + box_b[2]) / 2
    by = (box_b[1] + box_b[3]) / 2
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5

def boxes_overlap(box_a, box_b):
    return not (
        box_a[2] < box_b[0] or
        box_a[0] > box_b[2] or
        box_a[3] < box_b[1] or
        box_a[1] > box_b[3]
    )

def nearest_suspect(trash_box, persons, vehicles):
    suspects = []
    for b in persons:
        suspects.append(("person", b))
    for b in vehicles:
        suspects.append(("vehicle", b))
    if not suspects:
        return None, None
    nearest = min(suspects, key=lambda s: get_distance(trash_box, s[1]))
    return nearest[0], nearest[1]

def get_box_center(box):
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)

def box_movement(box_a, box_b):
    ax, ay = get_box_center(box_a)
    bx, by = get_box_center(box_b)
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5

def smooth_coords(store, key, new_box, alpha=0.5):
    if key not in store:
        store[key] = new_box
        return new_box
    old    = store[key]
    result = [alpha * new_box[i] + (1 - alpha) * old[i] for i in range(4)]
    store[key] = result
    return result

def is_same_person(current_box, owner_last_pos):
    if owner_last_pos is None:
        return False
    cx, cy = get_box_center(current_box)
    ox, oy = owner_last_pos
    return ((cx - ox) ** 2 + (cy - oy) ** 2) ** 0.5 < OWNER_MATCH_THRESHOLD

def save_snapshot(frame, suspect_box, suspect_type, trash_label):
    uid       = uuid.uuid4().hex[:8]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    h, w      = frame.shape[:2]
    x1 = max(0, int(suspect_box[0]))
    y1 = max(0, int(suspect_box[1]))
    x2 = min(w, int(suspect_box[2]))
    y2 = min(h, int(suspect_box[3]))
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        print("[SNAPSHOT] Failed - invalid coordinates")
        return None, None
    folder   = "persons" if suspect_type == "person" else "vehicles"
    img_path = f"{SNAPSHOT_DIR}/{folder}/{trash_label}_{timestamp}_{uid}.jpg"
    cv2.imwrite(img_path, crop)
    full_path = f"{SNAPSHOT_DIR}/full/{trash_label}_{timestamp}_{uid}_full.jpg"
    cv2.imwrite(full_path, frame)
    print(f"[SNAPSHOT] Saved: {img_path}")
    return img_path, full_path   # returns both paths now

def draw_rect(frame, box, label, color):
    x1, y1, x2, y2 = map(int, box)
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw, y1), color, -1)
    cv2.putText(frame, label, (x1, y1 - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)


# ── State machine colors ──────────────────────────────────────
STATE_COLORS = {
    "UNKNOWN":    (128, 128, 128),
    "CARRYING":   (0,   255, 255),
    "SEPARATION": (0,   165, 255),
    "STATIONARY": (0,   0,   255),
    "ALERTED":    (0,   0,   128),
    "CANCELLED":  (0,   255,   0),
}


# ── State machine ─────────────────────────────────────────────
def update_object_state(key, current_box, prev_box, persons, vehicles, frame):
    global object_states, frame_count

    if key not in object_states:
        object_states[key] = {
            "state":          "UNKNOWN",
            "box":            current_box,
            "owner_box":      None,
            "owner_last_pos": None,
            "sep_frame":      None,
            "prev_box":       prev_box,
            "label":          None,
            "confidence":     0.0
        }

    state_info = object_states[key]
    state      = state_info["state"]

    # ── UNKNOWN ───────────────────────────────────────────────
    if state == "UNKNOWN":
        suspect_type, suspect_box = nearest_suspect(current_box, persons, vehicles)
        if suspect_box is not None:
            dist = get_distance(current_box, suspect_box)
            if dist < CARRY_DISTANCE or boxes_overlap(current_box, suspect_box):
                state_info["state"]     = "CARRYING"
                state_info["owner_box"] = suspect_box

    # ── CARRYING ──────────────────────────────────────────────
    elif state == "CARRYING":
        suspect_type, suspect_box = nearest_suspect(current_box, persons, vehicles)

        if suspect_box is not None:
            state_info["owner_box"]      = suspect_box
            state_info["owner_last_pos"] = get_box_center(suspect_box)

        if suspect_box is None or \
           get_distance(current_box, suspect_box) > CARRY_DISTANCE:
            state_info["state"]          = "SEPARATION"
            state_info["sep_frame"]      = frame_count
            state_info["owner_last_pos"] = get_box_center(
                state_info["owner_box"]
            ) if state_info["owner_box"] else None

    # ── SEPARATION ────────────────────────────────────────────
    elif state == "SEPARATION":
        suspect_type, suspect_box = nearest_suspect(current_box, persons, vehicles)

        if suspect_box is not None and \
           get_distance(current_box, suspect_box) < CANCEL_DISTANCE:
            if is_same_person(suspect_box, state_info.get("owner_last_pos")):
                state_info["state"] = "CANCELLED"
                print(f"[CANCEL] Owner returned during separation")
                return None
            else:
                print(f"[INFO] Passerby near object during separation - ignoring")

        movement         = box_movement(current_box, prev_box)
        sep_frame        = state_info["sep_frame"] or frame_count
        frames_separated = frame_count - sep_frame

        if movement < STATIONARY_PIXELS and frames_separated >= SEPARATION_FRAMES:
            state_info["state"] = "STATIONARY"
            print(f"[STATE] Object STATIONARY after {frames_separated} frames")

    # ── STATIONARY ────────────────────────────────────────────
    elif state == "STATIONARY":
        suspect_type, suspect_box = nearest_suspect(current_box, persons, vehicles)

        if suspect_box is not None and \
           get_distance(current_box, suspect_box) < CANCEL_DISTANCE:
            if is_same_person(suspect_box, state_info.get("owner_last_pos")):
                state_info["state"] = "CANCELLED"
                print(f"[CANCEL] Owner returned to object")
                return None
            else:
                print(f"[INFO] Passerby near stationary object - not cancelling")

        person_gone = (
            suspect_box is None or
            get_distance(current_box, suspect_box) > ABANDON_DISTANCE
        )

        if person_gone:
            print(f"\n{'='*45}")
            print(f"  LITTER EVENT CONFIRMED")
            print(f"  Label:  {state_info.get('label', 'Unknown')}")
            print(f"  Flow:   CARRYING → SEPARATION → STATIONARY → ABANDONED")
            print(f"  Time:   {datetime.now().strftime('%H:%M:%S')}")
            print(f"{'='*45}")

            snap_box   = state_info.get("owner_box") or suspect_box
            snap_type  = suspect_type or "person"
            img_path   = None
            full_path  = None
            plate      = None

            if snap_box is not None:
                img_path, full_path = save_snapshot(
                    frame, snap_box, snap_type,
                    state_info.get("label", "trash")
                )
                # OCR only for vehicles
                if snap_type == "vehicle":
                    plate = read_plate_from_frame(frame, snap_box)
                    if plate:
                        print(f"  Plate:  {plate}")

            state_info["state"] = "ALERTED"
            return {
                "timestamp":        datetime.now().isoformat(),
                "label":            state_info.get("label", "Unknown"),
                "suspect_type":     snap_type,
                "image_path":       img_path,
                "full_frame_path":  full_path,
                "camera_id":        CAMERA_ID,
                "license_plate":    plate,
                "confidence":       state_info.get("confidence", 0.0),
            }

    state_info["prev_box"] = state_info["box"]
    state_info["box"]      = current_box
    return None


# ── Litter detection caller ───────────────────────────────────
def detect_litter(trash_boxes, trash_labels, trash_ids, persons, vehicles, frame):
    global tracked_trash, frame_count
    events = []

    for i, trash_box in enumerate(trash_boxes):
        label    = trash_labels[i]
        track_id = trash_ids[i]
        key      = track_id if track_id is not None else get_grid_key(trash_box)

        prev_box = trash_box
        if key in object_states and object_states[key].get("box"):
            prev_box = object_states[key]["box"]

        if key in object_states:
            object_states[key]["label"] = label

        event = update_object_state(key, trash_box, prev_box, persons, vehicles, frame)

        if key in object_states:
            object_states[key]["label"] = label

        if event is not None:
            events.append(event)

        tracked_trash[key] = frame_count

    keys_to_remove = [
        k for k, v in tracked_trash.items()
        if frame_count - v > MEMORY_FRAME_COUNT * 3
    ]
    for k in keys_to_remove:
        tracked_trash.pop(k, None)
        object_states.pop(k, None)

    return events


# ── Trash detection helper ────────────────────────────────────
# Extracted so it runs on BOTH skipped and detection frames
def run_trash_detection(frame, persons, vehicles):
    """
    Runs ByteTrack trash detection on the given frame.
    Returns events list and updates last_drawn_trash.
    Called every frame to keep ByteTrack IDs stable.
    """
    global last_drawn_trash

    trash_detection = trash_model.track(frame, persist=True,tracker="bytetrack.yaml",verbose=False)[0]

    trash_boxes  = []
    trash_labels = []
    trash_ids    = []
    last_drawn_trash = []

    for box in trash_detection.boxes:
        conf   = float(box.conf[0])
        coords = box.xyxy[0].tolist()
        label  = trash_model.names[int(box.cls[0])]

        if conf < TRASH_CONF:
            continue

        track_id = int(box.id[0]) if box.id is not None else None
        key      = track_id if track_id is not None else get_grid_key(coords)

        trash_boxes.append(coords)
        trash_labels.append(label)
        trash_ids.append(track_id)

        smooth     = smooth_coords(smoothed_boxes, key, coords)
        state      = object_states.get(key, {}).get("state", "UNKNOWN")
        color      = STATE_COLORS.get(state, (225, 225, 225))
        id_str     = f"#{track_id}" if track_id else ""
        disp_label = f"{label}{id_str}|{state}"

        draw_rect(frame, smooth, disp_label, color)
        last_drawn_trash.append((smooth, disp_label, color))

    events = detect_litter(
        trash_boxes, trash_labels, trash_ids,
        persons, vehicles, frame
    )

    return events


# ── Main loop ─────────────────────────────────────────────────
vid = cv2.VideoCapture(SOURCE)
if not vid.isOpened():
    print(f"ERROR: Cannot open source: {SOURCE}")
    exit()

print("LitterWatch running... Press Q to quit")

while True:
    res, frame = vid.read()
    if not res:
        print("Stream ended")
        break

    frame_count += 1
    curr_time = time.time()
    fps       = 1 / (curr_time - prev_time + 1e-9)
    prev_time = curr_time

    # ── SKIPPED FRAME ─────────────────────────────────────────
    # Skip person detection but still run trash tracking
    # This keeps ByteTrack IDs stable across frames
    if frame_count % SKIP_FRAMES != 0:

        # Redraw last known person boxes (no new detection)
        for coords, label in last_drawn_persons:
            draw_rect(frame, coords, label, (0, 255, 0))
        for coords, label in last_drawn_vehicles:
            draw_rect(frame, coords, label, (0, 165, 255))

        # Run trash tracking every frame using last known persons
        events = run_trash_detection(frame, last_known_persons, last_known_vehicles)

        # Alert
        if events:
            cv2.rectangle(frame, (0, 0),
                          (frame.shape[1]-1, frame.shape[0]-1),
                          (0, 0, 255), 10)
            cv2.putText(frame, "LITTER CONFIRMED",
                        (frame.shape[1]//2 - 170, 65),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 255), 3)
            for event in events:
                post_incident(event)

        cv2.putText(frame, f"FPS: {fps:.1f}",
                    (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
        cv2.imshow("LitterWatch", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
        continue

    # ── DETECTION FRAME ───────────────────────────────────────
    last_drawn_persons  = []
    last_drawn_vehicles = []

    # Person + vehicle detection
    person_detection = person_model(frame, verbose=False)[0]
    persons  = []
    vehicles = []

    for box in person_detection.boxes:
        cls    = int(box.cls[0])
        conf   = float(box.conf[0])
        coords = box.xyxy[0].tolist()

        if cls == 0 and conf > PERSON_CONF:
            pkey   = get_grid_key(coords)
            smooth = smooth_coords(smoothed_persons, pkey, coords)
            label  = f"Person {conf:.2f}"
            persons.append(coords)
            draw_rect(frame, smooth, label, (0, 255, 0))
            last_drawn_persons.append((smooth, label))

        elif cls in VEHICLE_CLASSES and conf > PERSON_CONF:
            label = f"Vehicle {conf:.2f}"
            vehicles.append(coords)
            draw_rect(frame, coords, label, (0, 165, 255))
            last_drawn_vehicles.append((coords, label))

    # Save for use on skipped frames
    last_known_persons  = persons
    last_known_vehicles = vehicles

    # Run trash detection + state machine
    events = run_trash_detection(frame, persons, vehicles)

    # Alert + send to backend
    if events:
        cv2.rectangle(frame, (0, 0),
                      (frame.shape[1]-1, frame.shape[0]-1),
                      (0, 0, 255), 10)
        cv2.putText(frame, "LITTER CONFIRMED",
                    (frame.shape[1]//2 - 170, 65),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 255), 3)
        for event in events:
            post_incident(event)

    # HUD
    cv2.putText(frame, f"FPS: {fps:.1f}",
                (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
    cv2.putText(frame, f"Persons: {len(persons)}",
                (10, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1)
    cv2.putText(frame, f"Vehicles: {len(vehicles)}",
                (10, 72), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 1)
    cv2.putText(frame, f"Trash tracked: {len(last_drawn_trash)}",
                (10, 92), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 1)

    y = 116
    state_counts = {}
    for s_data in object_states.values():
        s = s_data.get("state", "UNKNOWN")
        state_counts[s] = state_counts.get(s, 0) + 1
    for st, count in state_counts.items():
        color = STATE_COLORS.get(st, (200, 200, 200))
        cv2.putText(frame, f"{st}: {count}",
                    (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
        y += 18

    cv2.imshow("LitterWatch", frame)
    if cv2.waitKey(10) & 0xFF == ord('q'):
        break

# Cleanup
vid.release()
cv2.destroyAllWindows()
print(f"\nSession ended.")
print(f"Total frames processed: {frame_count}")
print(f"Snapshots saved to: {SNAPSHOT_DIR}/")