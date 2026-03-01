import requests
from datetime import datetime
from config import BACKEND_URL


def post_incident(event: dict) -> bool:
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

    try:
        response = requests.post(
            f"{BACKEND_URL}/incidents",
            json=payload,
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            print(f"[API] ✓ Incident posted (id: {data.get('id', '?')})")
            return True   # ← was missing
        else:
            print(f"[API] ✗ Failed: {response.status_code} - {response.text}")
            return False

    except requests.exceptions.ConnectionError:
        print("[API] ✗ Backend not reachable - is uvicorn running?")
        return False
    except requests.exceptions.Timeout:
        print("[API] ✗ Request timed out")
        return False
    except Exception as e:
        print(f"[API] ✗ Unexpected error: {e}")
        return False


def get_stats() -> dict:
    try:
        response = requests.get(f"{BACKEND_URL}/stats", timeout=3)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return {}   # ← was broken by indentation, now correct


def get_recent_incidents(limit: int = 10) -> list:
    try:
        response = requests.get(
            f"{BACKEND_URL}/incidents/recent",
            params={"limit": limit},
            timeout=3
        )
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return []


if __name__ == "__main__":
    print("Testing api_client.py...")
    print("Make sure backend is running: uvicorn main:app --reload")
    print()

    test_event = {
        "timestamp":       datetime.now().isoformat(),
        "camera_id":       "CAM_TEST",
        "label":           "Bottle",
        "confidence":      0.82,
        "suspect_type":    "person",
        "image_path":      None,
        "full_frame_path": None,
        "license_plate":   None,
    }

    print("Sending test incident...")
    success = post_incident(test_event)

    if success:
        print("\nChecking stats...")
        stats = get_stats()
        print(f"Stats: {stats}")

        print("\nChecking recent incidents...")
        recent = get_recent_incidents(5)
        print(f"Recent count: {len(recent)}")
        if recent:
            print(f"Latest: {recent[0]}")
    else:
        print("Backend not reachable.")
        print("Start backend: cd backend && uvicorn main:app --reload")