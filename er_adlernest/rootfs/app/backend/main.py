import os
import json
import logging
import asyncio
from typing import List, Optional
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from models import get_db, Camera, Recording, SessionLocal
from indexer import scan_directory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("adlernest")

app = FastAPI(
    title="ER-Adlernest CCTV & Video Archive Manager",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Background scheduler task for auto-indexing
SCAN_TASK = None

def get_scan_path():
    # Check CIFS mount first, then local configured path
    cifs_path = "/mnt/nas_recordings"
    if os.path.exists(cifs_path) and os.listdir(cifs_path):
        return cifs_path
    
    # Read from addon options if available
    options_file = "/data/options.json"
    if os.path.exists(options_file):
        try:
            with open(options_file, "r") as f:
                opts = json.load(f)
                return opts.get("local_path", "/share/er_adlernest/recordings")
        except Exception:
            pass
    return os.getenv("RECORDINGS_PATH", "/share/er_adlernest/recordings")

async def periodic_scanner():
    while True:
        try:
            path = get_scan_path()
            scan_directory(path)
        except Exception as e:
            logger.error(f"Error during periodic scan: {e}")
        await asyncio.sleep(300) # every 5 minutes

@app.on_event("startup")
async def startup_event():
    global SCAN_TASK
    # Initial scan in background
    SCAN_TASK = asyncio.create_task(periodic_scanner())

@app.on_event("shutdown")
async def shutdown_event():
    if SCAN_TASK:
        SCAN_TASK.cancel()

# --- Health & Status ---
@app.get("/api/status")
def get_status(db: Session = Depends(get_db)):
    rec_count = db.query(func.count(Recording.id)).scalar() or 0
    cam_count = db.query(func.count(Camera.id)).scalar() or 0
    total_size = db.query(func.sum(Recording.file_size)).scalar() or 0
    last_rec = db.query(Recording).order_by(desc(Recording.recorded_at)).first()

    return {
        "status": "healthy",
        "addon": "er_adlernest",
        "tagline": "Your Eagle Eye for Home Assistant Surveillance",
        "statistics": {
            "total_recordings": rec_count,
            "total_cameras": cam_count,
            "total_storage_bytes": total_size,
            "last_recording_time": last_rec.recorded_at.isoformat() if last_rec else None
        },
        "storage_path": get_scan_path(),
        "storage_mounted": os.path.exists(get_scan_path())
    }

# --- Trigger Indexing ---
@app.post("/api/archive/scan")
def trigger_scan(background_tasks: BackgroundTasks):
    path = get_scan_path()
    background_tasks.add_task(scan_directory, path)
    return {"message": "Scan triggered in background", "target_path": path}

# --- Camera Endpoints ---
@app.get("/api/cameras")
def list_cameras(db: Session = Depends(get_db)):
    return db.query(Camera).all()

@app.post("/api/cameras")
def create_camera(cam: dict, db: Session = Depends(get_db)):
    camera = Camera(
        name=cam.get("name"),
        source_type=cam.get("source_type", "rtsp"),
        stream_url=cam.get("stream_url", ""),
        substream_url=cam.get("substream_url"),
        fps=cam.get("fps", 15),
        enabled=cam.get("enabled", True)
    )
    db.add(camera)
    db.commit()
    db.refresh(camera)
    return camera

@app.delete("/api/cameras/{camera_id}")
def delete_camera(camera_id: int, db: Session = Depends(get_db)):
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    db.delete(cam)
    db.commit()
    return {"deleted": True, "id": camera_id}

# --- Recording & Archive Endpoints ---
@app.get("/api/recordings")
def get_recordings(
    camera: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    query = db.query(Recording)
    if camera:
        query = query.filter(Recording.camera_name == camera)
    if event_type:
        query = query.filter(Recording.event_type == event_type)
    
    total = query.count()
    records = query.order_by(desc(Recording.recorded_at)).offset(offset).limit(limit).all()
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": records
    }

@app.get("/api/recordings/{rec_id}")
def get_recording_detail(rec_id: int, db: Session = Depends(get_db)):
    rec = db.query(Recording).filter(Recording.id == rec_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")
    return rec

@app.get("/api/recordings/{rec_id}/stream")
def stream_video(rec_id: int, db: Session = Depends(get_db)):
    rec = db.query(Recording).filter(Recording.id == rec_id).first()
    if not rec or not os.path.exists(rec.file_path):
        raise HTTPException(status_code=404, detail="Video file not found")
    return FileResponse(rec.file_path, media_type="video/mp4")

@app.get("/api/recordings/{rec_id}/thumbnail")
def get_recording_thumbnail(rec_id: int, db: Session = Depends(get_db)):
    rec = db.query(Recording).filter(Recording.id == rec_id).first()
    if not rec or not rec.thumbnail_path:
        raise HTTPException(status_code=404, detail="Thumbnail not available")
    
    thumb_full = os.path.join("/data/thumbnails", rec.thumbnail_path)
    if not os.path.exists(thumb_full):
        raise HTTPException(status_code=404, detail="Thumbnail file missing")
    return FileResponse(thumb_full, media_type="image/jpeg")

# Serve frontend build static files if present
FRONTEND_DIR = "/app/frontend/dist"
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
else:
    @app.get("/")
    def root():
        return {
            "name": "ER-Adlernest",
            "tagline": "Your Eagle Eye for Home Assistant Surveillance",
            "status": "Online",
            "api_docs": "/api/docs"
        }

