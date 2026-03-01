from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class LitterSchema(BaseModel):
    timestamp:          datetime
    camera_id:          str
    trash_type:         str
    trash_confidence:   float
    offender_type:      str
    license_plate:      Optional[str] = None      # optional
    person_image_path:  Optional[str] = None      # optional
    vehicle_image_path: Optional[str] = None      # optional
    full_frame_path:    Optional[str] = None      # optional
    alert_sent:         bool = False

class VehicleSchema(BaseModel):
    license_plate:  str
    first_seen:     datetime
    last_seen:      datetime
    incident_count: int = 1

class TrashLogSchema(BaseModel):
    timestamp:  datetime
    camera_id:  str
    trash_type: str