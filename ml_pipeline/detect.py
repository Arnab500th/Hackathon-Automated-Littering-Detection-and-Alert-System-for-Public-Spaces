import cv2
import time
import os
from datetime import datetime
from ultralytics import YOLO
import uuid
from config import *

# MODELS
# Two models run on every frame:
# person_model → detects people and vehicles (pretrained YOOLOv8s)
# trash_model  → detects litter (your trained TACO model)
person_model = YOLO(r"ml_pipeline\weights\yolov8s.pt")
trash_model  = YOLO(r"ml_pipeline\weights\taco_8s_v3.pt")

# FOLDER SETUP
# Create all required snapshot directories at startup
os.makedirs(f"{SNAPSHOT_DIR}/persons",     exist_ok=True)
os.makedirs(f"{SNAPSHOT_DIR}/vehicles",    exist_ok=True)
os.makedirs(f"{SNAPSHOT_DIR}/full", exist_ok=True)

# STATE VARIABLES
# These live outside functions so they persist across frames

# Stores known trash positions: {grid_key: frame_number_last_seen}
tracked_trash = {}

# Stores state machine data for each tracked object
# Each entry: {grid_key: {'state': str, 'box': list, 'owner_box': list,
#                          'sep_frame': int, 'prev_box': list}}
object_states = {}

frame_count = 0
prev_time   = 0


# HELPER FUNCTIONS

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
        box_a[2] < box_b[0] or   # a is left of b
        box_a[0] > box_b[2] or   # a is right of b
        box_a[3] < box_b[1] or   # a is above b
        box_a[1] > box_b[3]      # a is below b
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
    return nearest[0], nearest[1]   # (type, box)


def get_box_center(box):#returns box center
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def box_movement(box_a, box_b):
    """
    How many pixels did the center move between two boxes.
    Used to detect if a trash object has stopped moving (stationary).
    """
    ax, ay = get_box_center(box_a)
    bx, by = get_box_center(box_b)
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def save_snapshot(frame, suspect_box, suspect_type, trash_label):
    uid       = uuid.uuid4().hex[:8]   # short unique ID
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    h, w      = frame.shape[:2]

    # Clamp coordinates to frame boundaries
    x1 = max(0, int(suspect_box[0]))
    y1 = max(0, int(suspect_box[1]))
    x2 = min(w, int(suspect_box[2]))
    y2 = min(h, int(suspect_box[3]))

    crop = frame[y1:y2, x1:x2]

    if crop.size == 0:
        print("[SNAPSHOT] Failed - invalid box coordinates")
        return None

    # Save cropped suspect image
    folder   = "persons" if suspect_type == "person" else "vehicles"
    img_path = f"{SNAPSHOT_DIR}/{folder}/{trash_label}_{timestamp}_{uid}.jpg"
    cv2.imwrite(img_path, crop)

    # Save full frame for context
    full_path = f"{SNAPSHOT_DIR}/full/{trash_label}_{timestamp}_{uid}_full.jpg"
    cv2.imwrite(full_path, frame)

    print(f"[SNAPSHOT] Saved: {img_path}")
    return img_path


def draw_rect(frame, box, label, color):
    x1, y1, x2, y2 = map(int, box)
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

    # Text background for readability
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw, y1), color, -1)
    cv2.putText(frame, label, (x1, y1 - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

def is_same_person(current_box, owner_last_pos, threshold=120):
    """
    Checks if the person near the trash is likely the same one
    who dropped it, based on position continuity.
    """
    if owner_last_pos is None:
        # Don't know who the owner was 
        return False

    cx, cy = get_box_center(current_box)
    ox, oy = owner_last_pos
    dist   = ((cx - ox) ** 2 + (cy - oy) ** 2) ** 0.5
    return dist < threshold

# STATE MACHINE LOGIC
# Tracks each trash object through 5 states:
#
# UNKNOWN    → object just appeared, checking if person is nearby
# CARRYING   → person is close (assumed holding it)
# SEPARATION → object moved away from person
# STATIONARY → object stopped moving (on the ground)
# ALERTED    → litter event already fired, stop tracking
# CANCELLED  → person came back (picked it up / false positive)

# Color for each state shown on screen
STATE_COLORS = {
    "UNKNOWN":    (128, 128, 128),  # grey
    "CARRYING":   (0,   255, 255),  # yellow
    "SEPARATION": (0,   165, 255),  # orange
    "STATIONARY": (0,   0,   255),  # red
    "ALERTED":    (0,   0,   128),  # dark red
    "CANCELLED":  (0,   255,   0),  # green
}


def update_object_state(key,current_box, prev_box, persons, vehicles, frame):
    """
    Update the state of a tracked object based on its movement and proximity to suspects.
    key =  grid key for this object
    current_box = current bounding box of the object
    prev_box = previous bounding box of the object
    persons = list of detected person boxes in this frame
    vehicles = list of detected vehicle boxes in this frame
    frame = current video frame (for drawing and snapshots)
    """

    global object_states, frame_count

    #create state entry if new
    if key not in object_states:
        object_states[key]={
            "state": "UNKNOWN",
            "box": current_box,
            "owner_box": None,
            "sep_frame": None,
            "prev_box": prev_box,
            "label": None
        }

    state_info = object_states[key]
    state = state_info["state"]

    #unknown → carrying

    if state == "UNKNOWN":
        suspect_type,suspect_box = nearest_suspect(current_box, persons, vehicles)
        
        if suspect_box is not None:
            dist = get_distance(current_box, suspect_box)
            if dist < CARRY_DISTANCE or boxes_overlap(current_box, suspect_box):
                #person is close enough to be carrying the object
                state_info["state"] = "CARRYING"
                state_info["owner_box"] = suspect_box
            
    #carrying : person near check seperation
    elif state == "CARRYING":
        suspect_type, suspect_box = nearest_suspect(current_box, persons, vehicles)

        # Keep updating owner position while still carrying
        if suspect_box is not None:
            state_info["owner_box"]      = suspect_box
            state_info["owner_last_pos"] = get_box_center(suspect_box)

        if suspect_box is None or get_distance(current_box, suspect_box) > CARRY_DISTANCE:
            state_info["state"]          = "SEPARATION"
            state_info["sep_frame"]      = frame_count
            state_info["owner_last_pos"] = get_box_center(state_info["owner_box"]) if state_info["owner_box"] else None  
    
    #separation : person left check if come back

    elif state == "SEPARATION":
        suspect_type, suspect_box = nearest_suspect(current_box, persons, vehicles)

        if suspect_box is not None and get_distance(current_box, suspect_box) < CANCEL_DISTANCE:
            #person came back → cancelled event
            if is_same_person(suspect_box, state_info.get("owner_last_pos")):
                state_info["state"] = "CANCELLED"
                return None
            else:
                print(f"[INFO] Passerby near object during separation - ignoring")
        
        movement = box_movement(current_box, prev_box)
        sep_frame        = state_info["sep_frame"] or frame_count
        frames_separated = frame_count - sep_frame

        if movement < STATIONARY_PIXELS and frames_separated >= SEPARATION_FRAMES:
            #object stopped moving after separation → likely abandoned
            state_info["state"] = "STATIONARY"
    
    elif state == "STATIONARY":
        suspect_type, suspect_box = nearest_suspect(current_box, persons, vehicles)

        if suspect_box is not None and get_distance(current_box, suspect_box) < CANCEL_DISTANCE:

            if is_same_person(suspect_box, state_info.get("owner_last_pos")):
                state_info["state"] = "CANCELLED"
                return None
            else:
                print(f"[INFO] Passerby near stationary object - not cancelling")
            
        person_gone = suspect_box is None or get_distance(current_box, suspect_box) > ABANDON_DISTANCE

        if person_gone:
            #person is gone and object is stationary → trigger alert
            print(f"\n{'='*45}")
            print(f"  LITTER EVENT CONFIRMED")
            print(f"  Label:  {state_info.get('label', 'Unknown')}")
            print(f"  Flow:   CARRYING → SEPARATION → STATIONARY → ABANDONED")
            print(f"  Time:   {datetime.now().strftime('%H:%M:%S')}")
            print(f"{'='*45}")

            snap_box = state_info.get("owner_box") or suspect_box
            snap_type = suspect_type or "Person" 

            img_path = None

            if snap_box is not None :
                img_path = save_snapshot(frame, snap_box, snap_type, state_info.get("label", "trash"))

            state_info["state"] = "ALERTED"

            return {
                "timestamp": datetime.now().isoformat(),
                "label": state_info.get("label", "Unknown"),
                "suspect_type": snap_type,
                "image_path": img_path,
                "camera_id": CAMERA_ID
            }
        
    #if no event takes place
    state_info["prev_box"] = state_info["box"]
    state_info["box"] = current_box
    return None

def detect_litter(trash_boxes, trash_labels, persons, vehicles, frame):
    """
    Main litter detection function called every frame.
    Matches trash detections to tracked objects and updates state machine.
    Returns list of confirmed litter event dicts.
    """

    global tracked_trash, frame_count

    events = []

    for i , trash_box in enumerate(trash_boxes):
        label = trash_labels[i]
        key = get_grid_key(trash_box)

        #prev box for movement comparison
        prev_box = trash_box

        if key in object_states and object_states[key].get("box"):
            prev_box = object_states[key]["box"]

        #set label on state entry
        if key in object_states:
            object_states[key]["label"] = label
        else:
            pass

        event = update_object_state(key, trash_box, prev_box, persons, vehicles, frame)

        if key in object_states:
            object_states[key]["label"] = label
        
        if event is not None:
            events.append(event)

        tracked_trash[key] = frame_count

    #cleanup old tracked objects to prevent memory bloat
    keys_to_remove = [k for k , v in tracked_trash.items() if frame_count - v > MEMORY_FRAME_COUNT * 3]

    for k in keys_to_remove:
        tracked_trash.pop(k, None)
        object_states.pop(k, None)

    return events


# MAIN LOOP

vid= cv2.VideoCapture(SOURCE)

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

    #fps
    curr_time = time.time()
    fps = 1 / (curr_time - prev_time + 1e-9)
    prev_time = curr_time

    #skipping frames to reduce load , detection will run every nth frame 

    if frame_count % SKIP_FRAMES != 0:
        cv2.imshow("LitterWatch", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
        continue

    # Run detections
    person_detection = person_model(frame, verbose=False)[0]
    persons = []
    vehicles = []

    for box in person_detection.boxes:
        cls = int(box.cls[0])
        conf = float(box.conf[0])
        coords = box.xyxy[0].tolist()
       
        if cls == 0 and conf > PERSON_CONF:
           persons.append(coords)
           draw_rect(frame, coords, f"Person {conf:.2f}", (0, 255, 0))
        elif cls in VEHICLE_CLASSES and conf > PERSON_CONF:
           vehicles.append(coords)
           draw_rect(frame, coords, f"Vehicle {conf:.2f}", (0, 165, 255))

    #rash Detection
    trash_detection = trash_model(frame, verbose=False)[0]
    trash_boxes = []
    trash_labels = []

    for box in trash_detection.boxes:
        conf = float(box.conf[0])
        coords= box.xyxy[0].tolist()
        label = trash_model.names[int(box.cls[0])]

        if conf < TRASH_CONF:
            continue

        trash_boxes.append(coords)
        trash_labels.append(label)

        key = get_grid_key(coords)
        state = object_states.get(key, {}).get("state", "UNKNOWN")
        color = STATE_COLORS.get(state, (225, 225, 225))
        draw_rect(frame, coords, f"{label}|{state}", color)

    #Run the litter detection logi
    events = detect_litter(trash_boxes, trash_labels, persons, vehicles, frame)

    #Display Alerts on screen
    if events:
        cv2.rectangle(frame, (0,0),(frame.shape[1]-1, frame.shape[0]-1),(0,0,255), 10)
        cv2.putText(frame, "LITTER CONFIRMED",(frame.shape[1]//2 - 170, 65),cv2.FONT_HERSHEY_SIMPLEX,1.4, (0, 0, 255), 3)

    #HUD

    cv2.putText(frame, f"FPS: {fps:.1f}",
                (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
    cv2.putText(frame, f"Persons: {len(persons)}",
                (10, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1)
    cv2.putText(frame, f"Vehicles: {len(vehicles)}",
                (10, 72), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 1)
    cv2.putText(frame, f"Trash tracked: {len(trash_boxes)}",
                (10, 92), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 1)

    y = 116
    state_counts = {}
    for s_data in object_states.values():
        s = s_data.get('state', 'UNKNOWN')
        state_counts[s] = state_counts.get(s, 0) + 1
    for state, count in state_counts.items():
        color = STATE_COLORS.get(state, (200, 200, 200))
        cv2.putText(frame, f"{state}: {count}",
                    (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
        y += 18

    #image show
    cv2.imshow("LitterWatch", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break


#Cleanup
vid.release()
cv2.destroyAllWindows()
print(f"\nSession ended.")
print(f"Total frames processed: {frame_count}")
print(f"Snapshots saved to: {SNAPSHOT_DIR}/")

