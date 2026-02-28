from fastapi import FastAPI,Request,Depends
from fastapi.middleware.cors import CORSMiddleware
from model import litterSchema, VehicleSchema
from database import session,engine
import DBMS
from sqlalchemy.orm import Session

app=FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DBMS.Base.metadata.create_all(bind=engine)

# THIS IS THE HOME PAGE
@app.get("/")
def home():
    return "hello world"

def get_db():
    db=session()
    try:
        yield db
    finally:
        db.close()

#THIS IS A EXAMPLE TABLE I MADE TO INITIATE THE TABLE ---CAN BE REMOVED---
# litterrate=detections = [
#     litterSchema(
#                  timestamp=2026,
#         camera_id="CAM_NORTH_01",
#         trash_type="Plastic Bottle",
#         trash_confidence=0.98,
#         offender_type="Vehicle",
#         license_plate="ABC-1234",
#         person_image_path="/storage/p1.jpg",
#         vehicle_image_path="/storage/v1.jpg",
#         full_frame_path="/storage/f1.jpg",
#         alert_sent=False
#     ),
#     litterSchema(
#                  timestamp=2027,
#         camera_id="CAM_SOUTH_02",
#         trash_type="Cardboard",
#         trash_confidence=0.85,
#         offender_type="Pedestrian",
#         license_plate="",
#         person_image_path="/storage/p2.jpg",
#          vehicle_image_path="",
#         full_frame_path="/storage/f2.jpg",
#         alert_sent=True
#     )
# ]

# #THIS IS TO INITIATE THE DATABASE
# def initi():
#     db= session()
#     count= db.query(DBMS.litterr).count
#     if count == 0:
#         for litter in litterrate:
#             db.add(DBMS.litterr(**litter.model_dump()))
#         db.commit()

# initi()

# THIS IS THE MAIN PAGE WHERE EVERYTHING STARTS
@app.get("/incidents")
def litter(db: Session = Depends(get_db)):
    db_incidents= db.query(DBMS.litterr).all()
    return db_incidents

#this is for vehicle table showing
@app.get("/vehicles")
def litter(db: Session = Depends(get_db)):
    db_vehicle=db.query(DBMS.litterr).filter(DBMS.litterr.offender_type=="vehicle").all() #--set the input in lowercase or it wont work--
    if db_vehicle:
        db_incidents= db.query(DBMS.vehicle).all()
        return db_incidents

#this is the input taking page for both 
@app.post("/incidents")
def litteration(Litter: litterSchema, vehicle:VehicleSchema, db: Session=Depends(get_db)):
    main=DBMS.litterr(**Litter.model_dump())
    #--set the input in lowercase or it wont work--
    if Litter.offender_type.lower() == "vehicle":
        new_entry = DBMS.vehicle(**vehicle.model_dump())
        db.add(main)
        db.add(new_entry)
        db.commit()
        return vehicle
    else:
        db.add(DBMS.litterr(**Litter.model_dump()))
        db.commit()
        return Litter


