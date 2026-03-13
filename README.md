# TRACE — Trash Recognition and Automated Civic Enforcement
### Hackathon Prototype | AI-Powered Real-Time Urban Litter Detection & Alert System

---

## Project Overview

**TRACE** is an end-to-end AI surveillance pipeline that monitors live camera feeds, detects littering behaviour, identifies offenders (person or vehicle), and dispatches instant WhatsApp alerts with visual evidence to the nearest municipal authority — automatically.

The system integrates deep learning, multi-object tracking, state-machine event logic, geofencing, OCR, real-time streaming, and a live analytics dashboard into a single deployable pipeline.

**Target Environments:**
Municipal surveillance · Smart cities · Railway stations · Markets & public roads · Campuses · Urban monitoring

---

## System Architecture

```
Cameras (USB / RTSP / Video Files)
            ↓
  Multi-Threaded Frame Capture
  (one thread per camera, daemon=False)
            ↓
  Dynamic Priority System
  HIGH / MEDIUM / LOW skip control
  + Geofence sensitivity floor
            ↓
     YOLOv8 Detection
  Trash model  ←  every frame
  Person model ←  every Nth frame (priority-controlled)
            ↓
     ByteTrack Tracking
  (per-model, per-thread — no shared state)
            ↓
      State Machine
  UNKNOWN → CARRYING → SEPARATION → STATIONARY → ALERTED
                                  ↘ CANCELLED (owner returns)
            ↓
  Evidence Capture + EasyOCR (vehicles)
            ↓
  Nearest Municipality Office Routing
  (Haversine distance to MUNICIPALITY_OFFICES)
            ↓
  imgbb Upload → Twilio WhatsApp Alert
  (with zone sensitivity label)
            ↓
     FastAPI Backend
  SQLite · MJPEG Streaming · REST API
            ↓
     Admin Dashboard
  Live feed · Incidents · Stats · Priority badges · Zone badges
```

---

## Key Features

- Multi-camera real-time processing (threaded, one worker per camera)
- Dynamic priority system — HIGH / MEDIUM / LOW frame skip per camera based on recent activity
- Geofencing — cameras near schools, stations, or heritage sites never drop below MEDIUM priority
- Nearest-office alert routing — WhatsApp sent to the closest municipality ward office using Haversine GPS distance, not a hardcoded number
- Zone sensitivity labelling — alerts flag whether the incident occurred in a protected zone
- State-machine based littering detection — confirms events only after carry → separation → stationary → abandon sequence
- ByteTrack multi-object tracking with persistent IDs across frames
- Owner identity verification — ByteTrack ID matching prevents passerby false cancellations
- EasyOCR license plate recognition for vehicle offenders (Indian format validation)
- Evidence snapshots — cropped offender image + full annotated frame saved automatically
- imgbb image hosting — snapshots uploaded to public URL for Twilio media attachment
- FastAPI backend with SQLite — incidents, vehicles, trash log tables
- MJPEG live streaming — zero re-encode, event-driven frame push
- Dashboard with live priority badges and zone sensitivity indicators per camera
- 7-day history charts, per-camera stats, trash type breakdown

---

## Tech Stack

### ML & Computer Vision

| Component        | Technology                        |
|------------------|-----------------------------------|
| Person/Vehicle   | YOLOv8s (COCO pretrained)         |
| Trash Detection  | YOLOv8s fine-tuned on TACO        |
| Tracking         | ByteTrack (persist=True per thread)|
| OCR              | EasyOCR (lazy init, GPU=False)    |
| Image Processing | OpenCV                            |
| Training         | PyTorch + CUDA                    |

### Backend

| Component      | Technology           |
|----------------|----------------------|
| API Server     | FastAPI + Uvicorn    |
| Database       | SQLite (SQLAlchemy)  |
| Streaming      | MJPEG (event-driven) |
| Alerts         | Twilio WhatsApp API  |
| Image Hosting  | imgbb API            |
| Language       | Python 3.11+         |

### Frontend Dashboard

| Component  | Technology       |
|------------|------------------|
| UI         | HTML + CSS       |
| Logic      | JavaScript       |
| Charts     | Chart.js         |
| Streaming  | MJPEG (img src)  |
| Fonts      | JetBrains Mono   |

---

## Performance Benchmarks

**Test Machine:** Intel i5-12450HX · NVIDIA RTX 2050 4GB · 12GB RAM

| Cameras | Avg FPS | Priority State | Notes                          |
|---------|---------|----------------|--------------------------------|
| 1       | ~28 FPS | HIGH           | Real-time                      |
| 3       | ~20 FPS | HIGH           | Stable                         |
| 4       | ~16 FPS | HIGH           | GPU bound                      |
| 6–8     | ~14 FPS | MEDIUM/LOW mix | Most cameras idle, skip=5 or 8 |

**Priority system impact on inference load:**

| Priority | Person skip | Inferences/cam/sec | Max cameras (ceiling 112/s) |
|----------|-------------|--------------------|-----------------------------|
| HIGH     | every frame | ~60                | 4 (matches hardware limit)  |
| MEDIUM   | every 5th   | ~40                | 6–7                         |
| LOW      | every 8th   | ~35                | 8–9                         |

Trash model runs every frame regardless of priority — only person detection is skipped.
Cameras in HIGH_SENSITIVITY_ZONES are floored at MEDIUM and never drop to LOW.

---

## Folder Structure

```
TRACE/
│
├── backend/
│   ├── main.py          FastAPI app, all REST endpoints, MJPEG streaming
│   ├── DBMS.py          SQLAlchemy models (incidents, vehicles, trash_log)
│   ├── database.py      SQLite engine + session factory
│   ├── model.py         Pydantic schemas
│   └── main.db          SQLite database
│
├── frontend/
│   ├── index.html       Dashboard shell, page structure
│   ├── app.js           All fetch logic, charts, priority/zone badges
│   └── style.css        Dark theme, priority badge colours, zone badge
│
├── ml_pipeline/
│   ├── detect.py        Main detection loop, state machine, camera workers
│   ├── api_client.py    Backend POST, nearest-office routing, WhatsApp dispatch
│   ├── config.py        Camera registry, municipality offices, sensitivity zones,
│   │                    detection thresholds, priority windows
│   ├── geo.py           Haversine distance, nearest_office(), 
│   │                    in_high_sensitivity_zone(), get_geo_skip()
│   ├── imgbb_upload.py  Upload snapshot to imgbb, return public HTTPS URL
│   ├── whatsapp_alert.py Twilio WhatsApp message builder + sender
│   ├── ocr_module.py    EasyOCR plate reader, Indian format validation
│   ├── .env             API keys (Twilio, imgbb) — never commit
│   └── weights/
│       ├── yolov8s.pt
│       └── taco_8s_v3.pt
│
├── data/
│   ├── snapshots/
│   │   ├── persons/     Cropped offender images
│   │   ├── vehicles/    Cropped vehicle images
│   │   └── full/        Full annotated frames
│   └── test_videos/
│
├── docs/
│   └── screenshots/
│
└── README.md
```

---

## Configuration — config.py

All deployment-specific values live in `ml_pipeline/config.py`. Nothing else needs editing for a new deployment.

```python
# Cameras — add lat/lng for geofencing and office routing
CAMERA_CONFIG = [
    {"id": "CAM_01", "source": 0,        "label": "Front Gate",    "lat": 22.5626, "lng": 88.3511},
    {"id": "CAM_02", "source": "rtsp://…","label": "Park Entrance", "lat": 22.5553, "lng": 88.3514},
]

# Municipality offices — alerts routed to nearest by Haversine distance
MUNICIPALITY_OFFICES = [
    {"name": "Ward 1 Office", "Ph_no": "+91XXXXXXXXXX", "lat": 22.5679, "lng": 88.3468},
]

# Protected zones — cameras within radius_m never drop below MEDIUM priority
HIGH_SENSITIVITY_ZONES = [
    {"name": "School Zone",     "lat": 22.5548, "lng": 88.3522, "radius_m": 200},
    {"name": "Railway Station", "lat": 22.5448, "lng": 88.3426, "radius_m": 300},
]

# Priority windows
PRIORITY_HIGH_WINDOW   = 5    # seconds after trash detection = HIGH
PRIORITY_MEDIUM_WINDOW = 30   # seconds after = MEDIUM, beyond = LOW
```

**To add a new camera:** add one dict to `CAMERA_CONFIG` with correct `lat`/`lng`. Alert routing and zone sensitivity are automatic.

**To add a new municipality office:** add one dict to `MUNICIPALITY_OFFICES`. No camera config changes needed — nearest-office routing recalculates automatically.

---

## WhatsApp Alert Format

```
LITTER ALERT - CAM_01 | Esplanade Metro Gate → Ward 62 Office
────────────────────────────────
Trash:      Bottle
Offender:   PERSON
Confidence: 83%
On ground:  14.2s
Zone:       WARNING School Zone
Time:       14:32:07
[snapshot image attached]
```

- `camera_label → office_name` tells the officer exactly which camera fired and which ward was notified
- `Zone: WARNING <name>` appears when the camera is inside a HIGH_SENSITIVITY_ZONE, `Standard` otherwise
- Snapshot is uploaded to imgbb first, public HTTPS URL passed to Twilio as media attachment
- Alert thread is `daemon=False` — process waits for alert to complete even when video file source ends

---

## Installation & Setup

### 1. Clone Repository
```bash
git clone https://github.com/yourusername/TRACE.git
cd TRACE
```

### 2. Create Virtual Environment
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux / Mac
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure API Keys

Create `ml_pipeline/.env`:
```
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
IMGBB_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Twilio sandbox note: each recipient must send the sandbox join code to `+14155238886` on WhatsApp once before receiving alerts.

### 5. Edit config.py
Set real camera sources, GPS coordinates, municipality office phone numbers, and sensitivity zones.

---

## Running The System

**Start backend:**
```bash
uvicorn backend.main:app --reload
```

**Start detection pipeline:**
```bash
python ml_pipeline/detect.py
```

**Open dashboard:**
```
http://localhost:8000
```

**Test WhatsApp alert standalone** (no backend or detect.py needed):
```bash
cd ml_pipeline
python test_whatsapp.py
```

---

## Detection State Machine

Each tracked trash object moves through states independently:

```
UNKNOWN    → trash detected, no owner assigned yet
CARRYING   → person/vehicle within CARRY_DISTANCE (150px) or overlapping
SEPARATION → owner moved beyond CARRY_DISTANCE, timer started
STATIONARY → object hasn't moved >15px for 30+ frames since separation
ALERTED    → owner beyond ABANDON_DISTANCE (250px) — confirmed litter event
CANCELLED  → owner returned within CANCEL_DISTANCE (100px) — false alarm cleared
```

Owner identity is verified using ByteTrack IDs — a different person passing near the stationary object does not trigger CANCELLED. Falls back to positional distance if IDs are unavailable (first frame of new track).

---

## Geofencing Logic — geo.py

All geographic logic is in `ml_pipeline/geo.py`:

**`haversine(lat1, lng1, lat2, lng2)`** — returns distance in metres using the curved-earth formula. Raw degree subtraction is not used because 1 degree ≈ 111km, making `radius_m` comparisons completely incorrect without conversion.

**`nearest_office(cam_lat, cam_lng)`** — finds the closest `MUNICIPALITY_OFFICES` entry by Haversine distance. Replaces per-camera phone numbers — any camera anywhere routes correctly with zero manual assignment.

**`in_high_sensitivity_zone(cam_lat, cam_lng)`** — returns zone name if camera is within `radius_m` metres of any `HIGH_SENSITIVITY_ZONES` centre, else None.

**`get_geo_skip(current_skip, cam_lat, cam_lng)`** — overrides LOW skip (8) to MEDIUM skip (5) for cameras in sensitive zones. HIGH is never touched.

---

## Dashboard Features

**Dashboard tab:** Today's stat cards · Recent incidents table with snapshots · Trash type pie chart · Active cameras panel with priority + zone badges · 7-day history bar chart

**Live Stats tab:** Per-camera cards showing live stream thumbnail, today/all-time breakdown, priority badge (GREEN=HIGH / AMBER=MEDIUM / GREY=LOW), zone badge (orange, only shown if in sensitivity zone)

**Live Feed tab:** MJPEG streams for all cameras · Add Camera prompt for runtime additions

**Incidents tab:** Full incident log with snapshots (click to enlarge lightbox)

**Vehicles tab:** Repeat offender tracking by license plate with incident count

---

## Limitations

- Reduced detection accuracy in low light and adverse weather
- OCR accuracy drops on blurred or angled license plates
- GPU memory limits concurrent camera count (~4 cameras at full load on RTX 2050)
- `seen_trash_ids` set not pruned over very long sessions (memory grows slowly)
- Twilio sandbox requires recipient join code before first alert

---

## Future Scope

- WebRTC ultra-low latency streaming (replace MJPEG)
- Edge AI deployment — Jetson Orin Nano (one-line change: `YOLO("weights/yolov8s.engine")`)
- RL-based adaptive priority — learn optimal thresholds per camera from historical patterns
- Content-aware frame differencing — skip trash model on truly static frames
- Automated challan generation with legal-grade evidence packaging
- Cloud-scale multi-city deployment (Render backend + Vercel frontend already documented)
- MIN_CARRY_FRAMES passerby fix — reject CARRYING events that lasted fewer than 8 frames

---

## Dataset Credits

**TACO** — Trash Annotations in Context  
https://tacodataset.org — used for fine-tuning the trash detection model

**COCO** — Common Objects in Context  
https://cocodataset.org — used via pretrained YOLOv8 weights for person and vehicle detection

---

## Research Sources

- SAWN: A Smart Alert and Warning Network for Littering Surveillance — *Nature Scientific Reports, 2025*  
  https://www.nature.com/articles/s41598-024-77118-x

- Real-time Detection and Monitoring of Public Littering Behavior Using Deep Learning  
  https://www.researchgate.net/publication/388326795

- Real-Time Litter Detection System Using Deep Learning Techniques — *IRE Journals*  
  https://www.irejournals.com/formatedpaper/1712601.pdf

- Intelligent Garbage Detection and Alert System — *SAMVAKTI Journals*  
  https://www.samvaktijournals.com/system/files/sjrit/2021.02.19/intelligent_garbage_detection_and_alert_system.pdf

- AI-Based Camera Systems for Roadside Litter Detection and Offender Identification — *IJERT*  
  https://www.ijert.org/ai-based-camera-systems-for-roadsidel-itter-detection-and-offender-identification-ijertv15is010642

---

## Team

**Arnab Datta** — Team Leader  
ML Pipeline · Model Training · Detection Logic · State Machine · Geofencing · System Integration

**Sumit Paul** — Backend Engineer  
FastAPI Backend · Database Design · API Development · Streaming 

**Deepraj Paul** — Frontend & Documentation Lead  
Dashboard · UI/UX · Documentation · Presentation

📍 India

---

## License

MIT License — free for research and academic use.

---

*TRACE demonstrates a complete real-time AI surveillance pipeline — detection, tracking, event logic, OCR, geofenced alerting, and live analytics — designed for real-world municipal-scale deployment.*
