from twilio.rest import Client
from datetime import datetime
from dotenv import load_dotenv
import os

from imgbb_upload import upload_image
from pathlib import Path
load_dotenv(dotenv_path=Path(__file__).parent / ".env")

TWILIO_ACCOUNT_SID   = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN    = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM")  


def send_whatsapp_alert(
    to_number:    str ,         # "+918597797117"  — from CAMERA_CONFIG["Ph_no"]
    camera_id:    str,         # "CAM_01"
    camera_label: str,         # "Front Gate"
    trash_type:   str,         # "Bottle"
    suspect_type: str,         # "person" or "vehicle"
    confidence:   float,       # 0.0 – 1.0
    dwell_secs:   float,       # seconds trash was on ground
    plate:        str | None,  # license plate or None
    image_url:    str | None,  # public imgbb URL or None
) -> bool:
    """
    Send a WhatsApp alert to the camera's designated number.

    Why one number per camera?
      Each camera covers a different physical location. A guard at the
      front gate only needs alerts from CAM_01, not from every camera
      in the system. CAMERA_CONFIG["Ph_no"] routes each alert to the
      right person automatically.

    Message includes:
      - Which camera / location fired
      - Trash type and confidence
      - Whether offender is a person or vehicle (with plate if read)
      - How long the trash was on the ground before confirmation
      - Snapshot image attached (if imgbb upload succeeded)

    """

    client   = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    time_str = datetime.now().strftime("%H:%M:%S")

    offender_line = (
        f"VEHICLE — {plate}"   if suspect_type == "vehicle" and plate
        else "VEHICLE (plate unread)" if suspect_type == "vehicle"
        else "PERSON"
    )

    body = (
        f"🚨 LITTER ALERT — {camera_id} | {camera_label}\n"
        f"{'─' * 28}\n"
        f"Trash:      {trash_type}\n"
        f"Offender:   {offender_line}\n"
        f"Confidence: {confidence * 100:.0f}%\n"
        f"On ground:  {dwell_secs}s\n"
        f"Time:       {time_str}"
    )

    to_wa = f"whatsapp:{to_number}"

    try:
        if image_url:
            msg = client.messages.create(
                body      = body,
                media_url = [image_url],          # Twilio fetches image from imgbb
                from_     = TWILIO_WHATSAPP_FROM,
                to        = to_wa,
            )
        else:
            body += "\n⚠️ (snapshot unavailable)"
            msg = client.messages.create(
                body  = body,
                from_ = TWILIO_WHATSAPP_FROM,
                to    = to_wa,
            )

        print(f"[WA] ✓ Alert sent to {to_number} (sid: {msg.sid})")
        return True

    except Exception as e:
        print(f"[WA] ✗ Failed to send to {to_number}: {e}")
        return False
    
if __name__ == "__main__":
    link = upload_image("data\snapshots\persons\Bottle_20260309_092309_9a292b63.jpg")
    send_whatsapp_alert(
    "+919475561298",         # "+918597797117"  — from CAMERA_CONFIG["Ph_no"]
    "CAM_01",         # "CAM_01"
    "Front Gate",         # "Front Gate"
    "Bottle",         # "Bottle"
    "person",         # "person" or "vehicle"
    0.8,       # 0.0 – 1.0
    15.6,       # seconds trash was on ground
    None,  # license plate or None
   link,  # public imgbb URL or None
)