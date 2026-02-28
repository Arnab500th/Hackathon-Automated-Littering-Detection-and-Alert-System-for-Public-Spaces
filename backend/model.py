#This is the pydantic code
from pydantic import BaseModel
from datetime import datetime


class litterSchema(BaseModel):
    timestamp:datetime
    camera_id:str 
    trash_type:str 
    trash_confidence:float
    offender_type:str 
    license_plate:str 
    person_image_path:str 
    vehicle_image_path:str 
    full_frame_path:str 
    alert_sent:bool
    
class VehicleSchema(BaseModel):
    license_plate:str
    first_seen:datetime
    last_seen:datetime
    incident_count:int