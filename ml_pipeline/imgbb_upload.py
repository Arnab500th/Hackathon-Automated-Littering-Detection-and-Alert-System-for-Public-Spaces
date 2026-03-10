import requests
from dotenv import load_dotenv
import os
from pathlib import Path
load_dotenv(dotenv_path=Path(__file__).parent / ".env")
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY")

def upload_image(image_path: str) -> str | None :
    """
    Upload a local image file to imgbb and return the public HTTPS URL.
    Returns None on any failure so callers can degrade gracefully.
    Flow:
        local file  →  POST to imgbb API  →  public URL
                                              ↓
                                    passed to Twilio as media_url
    """
    error = "https://tinyurl.com/3bfkxh3e"
    try:
        with open(image_path, "rb") as f:
            response = requests.post(
                "https://api.imgbb.com/1/upload",
                params={"key": IMGBB_API_KEY},
                files={"image": f},
                timeout=10
            )

        data = response.json()
        if response.status_code == 200 and data.get("success"):
            url = data["data"]["url"]
            print(f"[IMGBB] ✓ Uploaded → {url}")
            return url
        else:
            err = data.get("error", {}).get("message", "unknown error")
            print(f"[IMGBB] ✗ Upload failed: {err}")
            return error

    except FileNotFoundError:
        print(f"[IMGBB] ✗ File not found: {image_path}")
        return error
    except requests.exceptions.Timeout:
        print("[IMGBB] ✗ Upload timed out (10s)")
        return error
    except Exception as e:
        print(f"[IMGBB] ✗ Unexpected error: {e}")
        return error

#testing
if __name__ == "__main__":
    upload_image("data\snapshots\persons\Bottle_20260309_092309_9a292b63.jpg")