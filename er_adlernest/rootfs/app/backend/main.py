import os
import json
import logging
import asyncio
import urllib.request
import urllib.error
from typing import List, Optional
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException, Query, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from models import get_db, Camera, Recording, AppSetting, get_setting, set_setting, SessionLocal, run_migrations
from indexer import scan_directory_sync

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("adlernest")

app = FastAPI(
    title="ER-Adlernest CCTV & Video Archive Manager",
    version="1.0.3",
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

SCAN_TASK = None
IS_SCANNING = False

def get_configured_storage_path():
    db_path = get_setting("storage_path", "").strip()
    if db_path:
        return db_path
    
    options_file = "/data/options.json"
    if os.path.exists(options_file):
        try:
            with open(options_file, "r") as f:
                opts = json.load(f)
                val = opts.get("local_path", "").strip()
                if val:
                    return val
        except Exception:
            pass
            
    return os.getenv("RECORDINGS_PATH", "/media")

async def run_scan_async():
    global IS_SCANNING
    if IS_SCANNING:
        return
    IS_SCANNING = True
    try:
        path = get_configured_storage_path()
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, scan_directory_sync, path)
    except Exception as e:
        logger.error(f"Scan execution failed: {e}")
    finally:
        IS_SCANNING = False

async def periodic_scanner():
    await asyncio.sleep(15)
    while True:
        try:
            await run_scan_async()
        except Exception as e:
            logger.error(f"Periodic scanner error: {e}")
        await asyncio.sleep(300)

@app.on_event("startup")
async def startup_event():
    global SCAN_TASK
    run_migrations()
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
    storage_path = get_configured_storage_path()

    return {
        "status": "healthy",
        "addon": "er_adlernest",
        "is_scanning": IS_SCANNING,
        "statistics": {
            "total_recordings": rec_count,
            "total_cameras": cam_count,
            "total_storage_bytes": total_size,
            "last_recording_time": last_rec.recorded_at.isoformat() if last_rec else None
        },
        "storage_path": storage_path,
        "storage_exists": os.path.exists(storage_path)
    }

# --- Settings & Storage Path Management from UI ---
@app.get("/api/settings")
def get_settings():
    return {
        "storage_path": get_configured_storage_path(),
        "samba_server": get_setting("samba_server", ""),
        "samba_share": get_setting("samba_share", ""),
        "samba_username": get_setting("samba_username", "")
    }

@app.post("/api/settings")
def save_settings(data: dict):
    if "storage_path" in data:
        new_path = data["storage_path"].strip()
        set_setting("storage_path", new_path)
        logger.info(f"Storage path updated in database to: {new_path}")
    if "samba_server" in data:
        set_setting("samba_server", data["samba_server"].strip())
    if "samba_share" in data:
        set_setting("samba_share", data["samba_share"].strip())
    if "samba_username" in data:
        set_setting("samba_username", data["samba_username"].strip())
    return {"message": "Settings saved successfully", "storage_path": get_configured_storage_path()}

# --- Directory & Folder Browser ---
@app.get("/api/fs/browse")
def browse_filesystem(path: str = Query("/media")):
    cleaned = (path or "").strip()
    if not cleaned:
        cleaned = "/media"
    
    safe_path = os.path.abspath(cleaned)
    parent = os.path.dirname(safe_path) if safe_path != "/" else None

    # Check if target directory exists
    if not os.path.exists(safe_path) or not os.path.isdir(safe_path):
        # Fallback to root mounts available in HA container
        candidates = ["/media", "/share", "/data", "/"]
        for c in candidates:
            if os.path.exists(c) and os.path.isdir(c):
                safe_path = c
                parent = os.path.dirname(safe_path) if safe_path != "/" else None
                break

    try:
        entries = os.scandir(safe_path)
        folders = [e.name for e in entries if e.is_dir() and not e.name.startswith(".")]
        folders.sort()
        return {"current": safe_path, "parent": parent, "folders": folders, "exists": True}
    except Exception as e:
        logger.warning(f"Browse error for {safe_path}: {e}")
        return {"current": safe_path, "parent": parent, "folders": [], "error": str(e), "exists": False}

# --- Home Assistant Native Integration: Entity Discovery & Proxy ---
@app.get("/api/ha/cameras")
def list_homeassistant_cameras():
    """Fetch camera entities directly from Home Assistant Supervisor / Core API using urllib."""
    supervisor_token = os.getenv("SUPERVISOR_TOKEN")
    ha_url = "http://supervisor/core/api/states"
    
    if not supervisor_token:
        logger.info("SUPERVISOR_TOKEN not present in container environment.")
        return {"error": "SUPERVISOR_TOKEN not set", "cameras": []}

    try:
        req = urllib.request.Request(
            ha_url,
            headers={
                "Authorization": f"Bearer {supervisor_token}",
                "Content-Type": "application/json"
            }
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                body = response.read().decode("utf-8")
                states = json.loads(body)
                cams = []
                for s in states:
                    eid = s.get("entity_id", "")
                    if eid.startswith("camera."):
                        attrs = s.get("attributes", {})
                        cams.append({
                            "entity_id": eid,
                            "name": attrs.get("friendly_name", eid),
                            "state": s.get("state"),
                            "brand": attrs.get("brand", "Home Assistant Camera")
                        })
                return {"cameras": cams}
            return {"error": f"HA API status {response.status}", "cameras": []}
    except Exception as e:
        logger.warning(f"Error querying Home Assistant cameras: {e}")
        return {"error": str(e), "cameras": []}

@app.get("/api/ha/camera_proxy/{entity_id}")
def proxy_ha_camera(entity_id: str):
    """Proxy live image snapshot from Home Assistant camera entity."""
    supervisor_token = os.getenv("SUPERVISOR_TOKEN")
    if not supervisor_token:
        raise HTTPException(status_code=500, detail="Supervisor token missing")

    url = f"http://supervisor/core/api/camera_proxy/{entity_id}"
    try:
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {supervisor_token}"}
        )
        with urllib.request.urlopen(req, timeout=6) as response:
            content = response.read()
            content_type = response.headers.get("Content-Type", "image/jpeg")
            return Response(content=content, media_type=content_type)
    except urllib.error.HTTPError as he:
        raise HTTPException(status_code=he.code, detail=f"HA camera_proxy error: {he.reason}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Trigger Indexing ---
@app.post("/api/archive/scan")
def trigger_scan(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_scan_async)
    return {"message": "Scan scheduled in background", "target_path": get_configured_storage_path()}

# --- Camera Endpoints ---
@app.get("/api/cameras")
def list_cameras(db: Session = Depends(get_db)):
    return db.query(Camera).all()

@app.post("/api/cameras")
async def create_or_update_camera(request: Request, db: Session = Depends(get_db)):
    try:
        cam = await request.json()
    except Exception as e:
        raw_body = await request.body()
        logger.error(f"Invalid JSON received in /api/cameras: {raw_body.decode('utf-8', errors='ignore')}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {e}")

    cam_id = cam.get("id")
    camera = None
    if cam_id:
        try:
            camera = db.query(Camera).filter(Camera.id == int(cam_id)).first()
        except Exception:
            pass

    name = str(cam.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Camera name is required")

    if not camera:
        camera = db.query(Camera).filter(Camera.name == name).first()
        if not camera:
            camera = Camera(name=name)
            db.add(camera)

    camera.name = name
    camera.source_type = str(cam.get("source_type") or "rtsp").strip()
    camera.stream_url = str(cam.get("stream_url") or "").strip()
    camera.substream_url = str(cam.get("substream_url") or "").strip() or None
    camera.ha_entity_id = str(cam.get("ha_entity_id") or "").strip() or None
    camera.folder_mapping = str(cam.get("folder_mapping") or "").strip() or None
    
    fps_val = cam.get("fps")
    try:
        camera.fps = int(fps_val) if fps_val is not None else 15
    except Exception:
        camera.fps = 15
        
    camera.enabled = bool(cam.get("enabled", True))
    
    db.commit()
    db.refresh(camera)
    return {
        "id": camera.id,
        "name": camera.name,
        "source_type": camera.source_type,
        "stream_url": camera.stream_url,
        "ha_entity_id": camera.ha_entity_id,
        "folder_mapping": camera.folder_mapping
    }

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

@app.get("/api/logo")
def get_logo():
    for p in ["/app/frontend/dist/icon.png", "/er_adlernest/icon.png", os.path.join(os.path.dirname(__file__), "../../../icon.png")]:
        if os.path.exists(p):
            return FileResponse(p, media_type="image/png")
    raise HTTPException(status_code=404, detail="Logo not found")

# Serve frontend static assets
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
