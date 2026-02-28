#This is the sql code
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime,func
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

# This is for the Base table
class litterr(Base):

    __tablename__='users'

    id=Column(Integer, primary_key=True, autoincrement=True) 
    timestamp=Column(DateTime,server_default=func.now())
    camera_id=Column(String(50))
    trash_type=Column(String)
    trash_confidence=Column(Float)
    offender_type=Column(String(20))
    license_plate=Column(String(20),nullable=True)
    person_image_path=Column(String)
    vehicle_image_path=Column(String,nullable=True)
    full_frame_path=Column(String)
    alert_sent=Column(Boolean)

# this is the vehicle table
class vehicle(Base):
    __tablename__='vehicle'
    id=Column(Integer, primary_key=True, index=True,autoincrement=True) 
    license_plate=Column(String) 
    first_seen=Column(DateTime)
    last_seen=Column(DateTime)
    incident_count=Column(Integer, default=1)