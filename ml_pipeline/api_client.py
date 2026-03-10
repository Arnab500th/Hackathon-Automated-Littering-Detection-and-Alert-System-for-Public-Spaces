import requests
from datetime import datetime
from config import BACKEND_URL

# ── Alert modules ─────────────────────────────────────────────
try:
    from imgbb_upload import upload_image
    IMGBB_AVAILABLE = True
except ImportError:
    print("[WARN] imgbb_upload not found - image upload disabled")
    IMGBB_AVAILABLE = False
    def upload_image(path): return None

try:
    from whatsapp_alert import send_whatsapp_alert   # file must be named whatsapp_alert.py
    WA_AVAILABLE = True
except ImportError:
    print("[WARN] whatsapp_alert not found - WhatsApp alerts disabled")
    WA_AVAILABLE = False
    def send_whatsapp_alert(**kwargs): return False


def post_incident(event: dict) -> bool:
    # ── 1. POST to backend ────────────────────────────────────
    payload = {
        "timestamp":          event.get("timestamp",    datetime.now().isoformat()),
        "camera_id":          event.get("camera_id",    "CAM_01"),
        "trash_type":         event.get("label",        "Unknown"),
        "trash_confidence":   event.get("confidence",   0.0),
        "offender_type":      event.get("suspect_type", "person"),
        "license_plate":      event.get("license_plate", None),
        "person_image_path":  event.get("image_path",   None) \
                              if event.get("suspect_type") != "vehicle" else None,
        "vehicle_image_path": event.get("image_path",   None) \
                              if event.get("suspect_type") == "vehicle" else None,
        "full_frame_path":    event.get("full_frame_path", None),
        "alert_sent":         False
    }

    backend_ok = False
    try:
        response = requests.post(f"{BACKEND_URL}/incidents", json=payload, timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"[API] ✓ Incident posted (id: {data.get('id', '?')})")
            backend_ok = True
        else:
            print(f"[API] ✗ Failed: {response.status_code} - {response.text}")
    except requests.exceptions.ConnectionError:
        print("[API] ✗ Backend not reachable - is uvicorn running?")
    except requests.exceptions.Timeout:
        print("[API] ✗ Request timed out")
    except Exception as e:
        print(f"[API] ✗ Unexpected error: {e}")

    # ── 2 & 3. WhatsApp alert ─────────────────────────────────
    phone_no = event.get("phone_no")
    if phone_no:
        _send_whatsapp_alert(event, phone_no)
    else:
        print("[WA] No Ph_no configured for this camera — skipping alert")

    return backend_ok


def _send_whatsapp_alert(event: dict, phone_no: str):
    image_path = event.get("full_frame_path")
    image_url  = None

    if image_path and IMGBB_AVAILABLE:
        image_url = upload_image(image_path)

    if WA_AVAILABLE:
        send_whatsapp_alert(
            to_number    = phone_no,
            camera_id    = event.get("camera_id",    "CAM_??"),
            camera_label = event.get("camera_label", ""),
            trash_type   = event.get("label",        "Unknown"),
            suspect_type = event.get("suspect_type", "person"),
            confidence   = event.get("confidence",   0.0),
            dwell_secs   = event.get("dwell_seconds", 0.0),
            plate        = event.get("license_plate"),
            image_url    = image_url,
        )