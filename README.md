# Automated Littering Detection & Alert System
# Hackathon Prototype | AI-powered Real-time Urban Surveillance


# 🧠 Project Overview

**Automated Littering Detection & Alert System for Public Spaces** is an 
AI-powered real-time surveillance solution that analyzes CCTV and camera feeds 
to detect littering behavior, identify offenders, and generate instant alerts 
with legally usable visual and textual evidence.

The system leverages:
- Deep Learning
- Multi-object tracking
- State-machine logic
- OCR
- Real-time streaming
- Live analytics dashboard

This project was developed as a **Hackathon Prototype** and demonstrates a 
complete **end-to-end AI + Backend + Dashboard pipeline**.

🎯 Target Areas:
- Municipal surveillance
- Smart cities
- Railway stations
- Markets & public roads
- Campuses
- Urban monitoring systems


# 🔁 System Architecture

 Cameras (USB / RTSP / Video Files)  
            ↓  
 Multi-Threaded Frame Capture  
            ↓  
     YOLOv8 Detection  
   (Person + Litter + Vehicle)  
            ↓  
     ByteTrack Tracking  
            ↓  
      State Machine  
 (Carry → Drop → Stationary → Abandon)  
            ↓  
 Evidence Capture + EasyOCR  
            ↓  
     FastAPI Backend  
            ↓  
    Database + Analytics  
            ↓  
   MJPEG Live Streaming  
            ↓  
     Admin Dashboard  


# ⚙️ Processing Pipeline

 Capture Frame
       ↓
 Resize & Preprocess
       ↓
 YOLOv8 Detection
 (Person + Trash + Vehicle)
       ↓
 ByteTrack Tracking
       ↓
 State Machine Logic
       ↓
 Littering Event Decision
       ↓
 Evidence Capture + OCR
       ↓
 Backend Logging + Dashboard Update


# 🚀 Key Features

✅ Multi-camera real-time processing  
✅ Threaded streaming pipeline (zero FPS impact)  
✅ YOLOv8-based object detection  
✅ ByteTrack multi-object tracking  
✅ State-machine based littering detection logic  
✅ Automatic evidence capture  
✅ License plate OCR (EasyOCR)  
✅ FastAPI backend  
✅ SQLite database logging  
✅ Real-time analytics dashboard  
✅ MJPEG live video streaming  
✅ Per-camera statistics  
✅ Real-time charts & graphs  
✅ Cost-effective AI surveillance solution  


# 🧠 Tech Stack

# 🔬 ML & Computer Vision

| Component        | Technology |
|------------------|-------------|
| Detection Model  | YOLOv8s |
| Dataset          | TACO |
| Tracking         | ByteTrack |
| OCR              | EasyOCR |
| Image Processing | OpenCV |
| Training         | PyTorch + CUDA |


# 🧩 Backend

| Component | Technology |
|------------|-------------|
| API Server | FastAPI |
| Database   | SQLite |
| Streaming  | MJPEG |
| Language   | Python |


# 🖥️ Frontend Dashboard

| Component | Technology |
|-------------|--------------|
| UI          | HTML + CSS |
| Logic       | JavaScript |
| Charts      | Chart.js |
| Streaming   | MJPEG |


# 📊 Performance Benchmarks

# Test Machine:
# CPU: Intel i5-12450HX
# GPU: NVIDIA RTX 2050 (4GB VRAM)
# RAM: 12GB

| Cameras | FPS | Notes |
|-----------|------|--------|
| 1 | ~28 FPS | Real-time |
| 3 | ~20 FPS | Stable |
| 4 | ~16 FPS | GPU bound |

✔ Multi-camera stable performance  
✔ Fully real-time detection  


# 📁 Folder Structure

LitterWatch/  
│  
├── backend/  
│    ├── main.py  
│    ├── DBMS.py  
│    ├── database.py  
│    └── main.db  
│  
├── frontend/  
│   ├── index.html  
│   ├── app.js  
│   └── styles.css  
│  
├── ml_pipeline/  
│   ├── detect.py  
│   ├── api_client.py  
│   ├── config.py  
│   └── models/  
│  
├── docs/  
├── test/  
├── training/  
│  
└── README.md  


# ⚡ Installation & Setup

# 1️⃣ Clone Repository
```
git clone https://github.com/yourusername/LitterWatch.git
cd LitterWatch
```

# 2️⃣ Create Virtual Environment
```
python -m venv venv
```

# 3️⃣ Activate Environment

# Windows
```
venv\Scripts\activate
```
# Linux / Mac
```
source venv/bin/activate
```

# 4️⃣ Install Dependencies
```
pip install -r requirements.txt
```

# ▶️ Running The System

# Start Backend Server
```
uvicorn backend.main:app --reload
```

# Start Detection Pipeline
```
python ml_pipeline/detect.py
```

# Open Dashboard

Open: frontend/index.html  
or  
http://localhost:8000


# 📦 Dataset

Primary Dataset Used:

🗑️ **TACO (Trash Annotations in Context)**  
- Public dataset for waste detection  
- Diverse trash object classes  
- Used for custom YOLOv8 training  


# 🧾 Output & Evidence

System automatically stores:

📸 Evidence images  
🔤 OCR extracted license plate text  
🗄️ Database logs  
📊 Analytics  
🎥 Live MJPEG streams  


# ⚠️ Limitations & Challenges

⚠️ Reduced detection in low-light & adverse weather  
⚠️ Camera angle variability  
⚠️ OCR issues on blurred plates  
⚠️ GPU memory limitations at scale  
⚠️ Dataset size constraints for hand-object detection  


# 🔮 Future Scope

🚀 WebRTC ultra-low latency streaming  
🚀 Edge AI deployment (Jetson Nano / Orin)  
🚀 Cloud-scale multi-city monitoring  
🚀 Heatmap-based violation analysis  
🚀 Smart city integration  
🚀 Legal-grade evidence storage  
🚀 Automated challan generation  


# 🖼️ Screenshots

## Dash Board screenshots

DashBoard.png  

<img width="1919" height="874" alt="DashBoard" src="docs\screenshots\DashBoard.png" />
Incidents.png  

<img width="1916" height="874" alt="incidents" src="docs\screenshots\incidents.png" />
Live Feed.png  

<img width="1916" height="874" alt="incidents" src="docs\screenshots\Live Feed.png" />

## Program
Detect.png  

<img width="1916" height="874" alt="incidents" src="docs\screenshots\Detect.png" />
## Full Image Snap Shots
full.jpg  

<img width="478" height="850" alt="incidents" src="docs\screenshots\full.jpg" />
full2.jpg  

<img width="478" height="850" alt="incidents" src="docs\screenshots\full2.jpg" />
full3.jpg  

<img width="478" height="850" alt="incidents" src="docs\screenshots\full3.jpg" />

## Offenders SnapShots  
culprit_1.jpg  

<img width="158" height="383" alt="incidents" src="docs\screenshots\culprit_1.jpg" />
culprit_2.jpg  

<img width="149" height="320" alt="incidents" src="docs\screenshots\culprit_2.jpg" />  

## Vehicles  

car.jpg  
<img width="265" height="347" alt="incidents" src="docs\screenshots\car.jpg" />


# 🏆 Deployment Status

### Currently runs on Local not deployed

🚧 Hackathon Prototype  
✔ Fully functional  
✔ Real-time capable  
✔ Scalable architecture  


# 👨‍💻 Team

👤 **Arnab Datta** — *Team Leader*  
ML Pipeline Architecture • Model Training • Detection Logic • System Integration • Testing • Project Planning  

👤 **Sumit Paul** — *Backend Engineer*  
FastAPI Backend • Database Design • API Development • Data Handling  

👤 **Deepraj Paul** — *Frontend & Documentation Lead*  
UI/UX Design • Dashboard Development • Project Documentation • Presentation Design  

📍 India  

**Core Technologies:**

YOLOv8 · ByteTrack · EasyOCR · FastAPI · OpenCV · Chart.js  

# 📦 Dataset Credits

• **TACO** — Trash Annotations in Context Dataset  
  https://tacodataset.org  
  Used for training the trash detection model.

• **COCO** — Common Objects in Context Dataset  
  https://cocodataset.org  
  Used via pretrained YOLOv8 weights for person & vehicle detection.

# 📚 Research References & Inspiration

This project is inspired by and aligned with current academic research in automated litter detection, 
computer vision–based surveillance, and intelligent environmental monitoring systems. The design of the 
detection pipeline, tracking strategy, and state-machine-based decision logic is guided by the following works:

• **SAWN: A Smart Alert and Warning Network for Littering Surveillance**  
  Nature Scientific Reports, 2025  
  https://www.nature.com/articles/s41598-024-77118-x  

• **Real-time Detection and Monitoring of Public Littering Behavior Using Deep Learning for a Sustainable Environment**  
  https://www.researchgate.net/publication/388326795_Real_time_detection_and_monitoring_of_public_littering_behavior_using_deep_learning_for_a_sustainable_environment  

• **Real-Time Litter Detection System Using Deep Learning Techniques**  
  IRE Journals  
  https://www.irejournals.com/formatedpaper/1712601.pdf  

• **Intelligent Garbage Detection and Alert System**  
  SAMVAKTI Journals  
  https://www.samvaktijournals.com/system/files/sjrit/2021.02.19/intelligent_garbage_detection_and_alert_system.pdf  

• **AI-Based Camera Systems for Roadside Litter Detection and Offender Identification**  
  IJERT  
  https://www.ijert.org/ai-based-camera-systems-for-roadsidel-itter-detection-and-offender-identification-ijertv15is010642  

These studies validate the feasibility of AI-driven litter surveillance and helped shape the 
architecture, detection logic, and system workflow used in this project.  

# 📜 License

**MIT License** — Free for research & academic use.


# ⭐ Final Note

This project demonstrates a **complete real-time AI surveillance pipeline** 
integrating:

✔ Deep Learning  
✔ Tracking  
✔ Event logic  
✔ OCR  
✔ Backend analytics  
✔ Live dashboard  

Designed for **real-world municipal-scale deployment** 🚀
