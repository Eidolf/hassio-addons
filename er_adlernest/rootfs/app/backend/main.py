import os
import json
import logging
import asyncio
import urllib.request
import urllib.error
from typing import Optional, Literal
from datetime import datetime, date, time, timedelta
import mimetypes

from fastapi import FastAPI, Depends, HTTPException, Query, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from models import get_db, Camera, Recording, get_setting, set_setting, run_migrations
from indexer import scan_directory_sync
import storage as storage_svc

# ---------------------------------------------------------------------------
# Logging – honour LOG_LEVEL from run.sh
# ---------------------------------------------------------------------------
_VALID_LEVELS = {"debug": logging.DEBUG, "info": logging.INFO,
                 "warning": logging.WARNING, "error": logging.ERROR}
_raw_level = os.getenv("LOG_LEVEL", "info").lower().strip()
_log_level = _VALID_LEVELS.get(_raw_level, logging.INFO)
logging.basicConfig(
    level=_log_level,
    format="%(levelname)s:%(name)s:%(message)s",
)
logger = logging.getLogger("adlernest")

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="ER-Adlernest CCTV & Video Archive Manager",
    version="1.2.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Ingress path-normalisation middleware
# HA Ingress prepends a variable prefix; the browser sends requests like
#   GET /api/hassio_ingress/TOKEN//api/status
# which leaves an extra leading slash after the prefix is stripped, turning
# the path seen by uvicorn into  //api/status  → 404.
# This middleware collapses consecutive slashes in the path to one, without
# touching the query string or any path parameters.
# ---------------------------------------------------------------------------
class NormaliseSlashesMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        scope = request.scope
        raw_path: bytes = scope.get("path", "").encode()
        # collapse //+ → /
        import re as _re
        clean = _re.sub(r"/+", "/", scope["path"])
        if clean != scope["path"]:
            scope["path"] = clean
            scope["raw_path"] = clean.encode()
        return await call_next(request)

app.add_middleware(NormaliseSlashesMiddleware)

# ---------------------------------------------------------------------------
# Scanner state
# ---------------------------------------------------------------------------
SCAN_TASK = None
IS_SCANNING = False
LAST_SCAN: dict = {}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_configured_storage_path() -> str:
    db_path = get_setting("storage_path", "").strip()
    if db_path:
        return db_path
    return os.getenv("RECORDINGS_PATH", "/media")


async def run_scan_async():
    global IS_SCANNING, LAST_SCAN
    if IS_SCANNING:
        return
    IS_SCANNING = True
    start = datetime.utcnow()
    path = get_configured_storage_path()
    try:
        loop = asyncio.get_event_loop()
        new_count = await loop.run_in_executor(None, scan_directory_sync, path)
        LAST_SCAN = {
            "started_at": start.isoformat(),
            "finished_at": datetime.utcnow().isoformat(),
            "path": path,
            "new_recordings": new_count,
            "status": "ok",
        }
    except Exception as exc:
        logger.error("Scan execution failed: %s", exc)
        LAST_SCAN = {
            "started_at": start.isoformat(),
            "finished_at": datetime.utcnow().isoformat(),
            "path": path,
            "status": "error",
            "error": str(exc)[:200],
        }
    finally:
        IS_SCANNING = False


async def periodic_scanner():
    await asyncio.sleep(15)
    while True:
        try:
            await run_scan_async()
        except Exception as exc:
            logger.error("Periodic scanner error: %s", exc)
        await asyncio.sleep(300)


@app.on_event("startup")
async def startup_event():
    global SCAN_TASK
    run_migrations()
    storage_svc._ensure_dirs()
    # Reconnect persisted SMB sources in the background (non-blocking)
    asyncio.create_task(_reconnect_bg())
    SCAN_TASK = asyncio.create_task(periodic_scanner())
    # Startup diagnostics (no tokens, no passwords)
    roots = [str(r) for r in storage_svc.LOCAL_ROOTS if r.exists()]
    smb_count = len(storage_svc._load())
    token_present = bool(os.getenv("SUPERVISOR_TOKEN"))
    logger.info(
        "ER-Adlernest started | log_level=%s | local_roots=%s | smb_sources=%d | ha_token=%s",
        _raw_level, roots, smb_count, "yes" if token_present else "no",
    )


async def _reconnect_bg():
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, storage_svc.reconnect_all)
    except Exception as exc:
        logger.warning("SMB reconnect on startup failed: %s", exc)


@app.on_event("shutdown")
async def shutdown_event():
    if SCAN_TASK:
        SCAN_TASK.cancel()

# ---------------------------------------------------------------------------
# Health / Status
# ---------------------------------------------------------------------------

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
        "last_scan": LAST_SCAN or None,
        "statistics": {
            "total_recordings": rec_count,
            "total_cameras": cam_count,
            "total_storage_bytes": total_size,
            "last_recording_time": last_rec.recorded_at.isoformat() if last_rec else None,
        },
        "storage_path": storage_path,
        "storage_exists": os.path.exists(storage_path),
        "storage_sources": storage_svc.list_sources(),
    }

# ---------------------------------------------------------------------------
# Settings (archive path only – no SMB credentials here)
# ---------------------------------------------------------------------------

@app.get("/api/settings")
def get_settings():
    return {"storage_path": get_configured_storage_path()}


@app.post("/api/settings")
def save_settings(data: dict):
    if "storage_path" in data:
        raw = str(data["storage_path"]).strip()
        if not raw:
            raise HTTPException(status_code=400, detail="storage_path must not be empty")
        try:
            resolved = str(storage_svc.resolve_allowed_directory(raw))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        set_setting("storage_path", resolved)
        logger.info("Storage path updated: %s", resolved)
        return {"message": "Settings saved", "storage_path": resolved}
    return {"message": "Nothing changed", "storage_path": get_configured_storage_path()}

# ---------------------------------------------------------------------------
# Storage sources (local browse + SMB)
# ---------------------------------------------------------------------------

@app.get("/api/storage/sources")
def list_storage_sources():
    return storage_svc.list_sources()


@app.post("/api/storage/sources")
async def create_or_update_storage_source(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None, storage_svc.upsert_source, payload
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return result


@app.post("/api/storage/sources/{source_id}/mount")
async def mount_storage_source(source_id: str):
    try:
        return await asyncio.get_event_loop().run_in_executor(
            None, storage_svc.mount_source, source_id
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/storage/sources/{source_id}/unmount")
async def unmount_storage_source(source_id: str):
    try:
        return await asyncio.get_event_loop().run_in_executor(
            None, storage_svc.unmount_source, source_id
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/storage/sources/test")
async def test_storage_source(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    try:
        return await asyncio.get_event_loop().run_in_executor(
            None, storage_svc.test_source, payload
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete("/api/storage/sources/{source_id}")
async def delete_storage_source(source_id: str):
    try:
        await asyncio.get_event_loop().run_in_executor(
            None, storage_svc.delete_source, source_id
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"deleted": True, "id": source_id}


# ---------------------------------------------------------------------------
# Filesystem browser (restricted to allowed roots)
# ---------------------------------------------------------------------------

@app.get("/api/fs/browse")
def browse_filesystem(path: str = Query("/media")):
    cleaned = (path or "").strip()
    if not cleaned or cleaned == "undefined":
        cleaned = "/media"
    # Resolve and restrict to allowed roots
    try:
        safe_path = storage_svc.resolve_allowed_directory(cleaned, require_exists=True)
    except ValueError:
        # Fallback to first available local root
        for fallback in storage_svc.LOCAL_ROOTS:
            if fallback.exists():
                safe_path = fallback
                break
        else:
            raise HTTPException(status_code=400, detail="No allowed storage root available")

    parent_str = str(safe_path.parent) if str(safe_path) != "/" else None
    # Only expose parent if it's still within an allowed root
    if parent_str:
        try:
            storage_svc.resolve_allowed_directory(parent_str, require_exists=False)
        except ValueError:
            parent_str = None

    try:
        entries = list(safe_path.iterdir())
        folders = sorted(e.name for e in entries if e.is_dir() and not e.name.startswith("."))
        return {"current": str(safe_path), "parent": parent_str, "folders": folders, "exists": True}
    except PermissionError as exc:
        logger.warning("Browse permission denied for %s: %s", safe_path, exc)
        raise HTTPException(status_code=403, detail="Permission denied")
    except OSError as exc:
        logger.warning("Browse error for %s: %s", safe_path, exc)
        return {"current": str(safe_path), "parent": parent_str, "folders": [], "error": str(exc), "exists": False}

# ---------------------------------------------------------------------------
# Home Assistant cameras
# ---------------------------------------------------------------------------

@app.get("/api/ha/cameras")
def list_homeassistant_cameras():
    token = os.getenv("SUPERVISOR_TOKEN")
    if not token:
        logger.info("SUPERVISOR_TOKEN not present – homeassistant_api may not be enabled")
        return {"error": "SUPERVISOR_TOKEN not available (ensure homeassistant_api: true)", "cameras": []}
    try:
        req = urllib.request.Request(
            "http://supervisor/core/api/states",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status != 200:
                return {"error": f"HA API returned HTTP {resp.status}", "cameras": []}
            states = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        logger.warning("HA camera list HTTP error: %d %s", exc.code, exc.reason)
        return {"error": f"HTTP {exc.code}: {exc.reason}", "cameras": []}
    except Exception as exc:
        logger.warning("HA camera list failed: %s", exc)
        return {"error": str(exc)[:200], "cameras": []}

    cams = []
    for s in states:
        eid = s.get("entity_id", "")
        if eid.startswith("camera."):
            attrs = s.get("attributes", {})
            cams.append({
                "entity_id": eid,
                "name": attrs.get("friendly_name", eid),
                "state": s.get("state"),
                "brand": attrs.get("brand", "Home Assistant Camera"),
            })
    return {"cameras": cams}


@app.get("/api/ha/camera_proxy/{entity_id:path}")
def proxy_ha_camera(entity_id: str):
    # Validate entity id
    if not entity_id.startswith("camera.") or "/" in entity_id:
        raise HTTPException(status_code=400, detail="Invalid entity id")
    token = os.getenv("SUPERVISOR_TOKEN")
    if not token:
        raise HTTPException(status_code=503, detail="Supervisor token missing")
    try:
        req = urllib.request.Request(
            f"http://supervisor/core/api/camera_proxy/{entity_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            content = resp.read()
            content_type = resp.headers.get("Content-Type", "image/jpeg")
            return Response(content=content, media_type=content_type)
    except Exception as exc:
        logger.debug("Camera proxy failed for %s: %s", entity_id, exc)
        raise HTTPException(status_code=502, detail="Could not retrieve snapshot")

# ---------------------------------------------------------------------------
# Archive scan trigger
# ---------------------------------------------------------------------------

@app.post("/api/archive/scan")
def trigger_scan(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_scan_async)
    return {"message": "Scan scheduled", "target_path": get_configured_storage_path()}

# ---------------------------------------------------------------------------
# Camera CRUD
# ---------------------------------------------------------------------------

@app.get("/api/cameras")
def list_cameras(db: Session = Depends(get_db)):
    return [_cam_dict(c) for c in db.query(Camera).all()]


def _cam_dict(c: Camera) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "source_type": c.source_type,
        "stream_url": c.stream_url,
        "substream_url": c.substream_url,
        "ha_entity_id": c.ha_entity_id,
        "folder_mapping": c.folder_mapping,
        "highres_stream_url": getattr(c, "highres_stream_url", None),
        "highres_ha_entity_id": getattr(c, "highres_ha_entity_id", None),
        "fullscreen_highres": bool(getattr(c, "fullscreen_highres", False)),
        "fps": c.fps,
        "enabled": c.enabled,
    }


@app.post("/api/cameras")
async def create_or_update_camera(request: Request, db: Session = Depends(get_db)):
    try:
        cam = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}")

    name = str(cam.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Camera name is required")

    cam_id = cam.get("id")
    camera = None
    if cam_id:
        try:
            camera = db.query(Camera).filter(Camera.id == int(cam_id)).first()
        except Exception:
            pass
    if not camera:
        camera = db.query(Camera).filter(Camera.name == name).first()
    if not camera:
        camera = Camera(name=name)
        db.add(camera)

    camera.name = name
    camera.source_type = str(cam.get("source_type") or "rtsp").strip()
    camera.stream_url = str(cam.get("stream_url") or "").strip() or None
    camera.substream_url = str(cam.get("substream_url") or "").strip() or None
    camera.ha_entity_id = str(cam.get("ha_entity_id") or "").strip() or None
    camera.folder_mapping = str(cam.get("folder_mapping") or "").strip() or None
    camera.highres_stream_url = str(cam.get("highres_stream_url") or "").strip() or None
    camera.highres_ha_entity_id = str(cam.get("highres_ha_entity_id") or "").strip() or None
    camera.fullscreen_highres = bool(cam.get("fullscreen_highres", False))
    try:
        camera.fps = int(cam.get("fps") or 15)
    except Exception:
        camera.fps = 15
    camera.enabled = bool(cam.get("enabled", True))

    try:
        db.commit()
        db.refresh(camera)
    except Exception as exc:
        db.rollback()
        logger.error("Camera save failed: %s", exc)
        raise HTTPException(status_code=500, detail="Database error")

    logger.info("Camera saved: id=%d name=%s type=%s", camera.id, camera.name, camera.source_type)
    return _cam_dict(camera)


@app.delete("/api/cameras/{camera_id}")
def delete_camera(camera_id: int, db: Session = Depends(get_db)):
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    db.delete(cam)
    db.commit()
    return {"deleted": True, "id": camera_id}

# ---------------------------------------------------------------------------
# Recordings
# ---------------------------------------------------------------------------

@app.get("/api/recordings")
def get_recordings(
    camera: Optional[str] = None,
    event_type: Optional[str] = None,
    media_type: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(Recording)
    if camera:
        query = query.filter(Recording.camera_name == camera)
    if event_type:
        query = query.filter(Recording.event_type == event_type)
    if media_type in ("video", "image"):
        query = query.filter(Recording.media_type == media_type)
    if date_from:
        query = query.filter(Recording.recorded_at >= datetime.combine(date_from, time.min))
    if date_to:
        query = query.filter(Recording.recorded_at < datetime.combine(date_to + timedelta(days=1), time.min))
    total = query.count()
    records = query.order_by(desc(Recording.recorded_at), desc(Recording.id)).offset(offset).limit(limit).all()
    return {
        "total": total, "limit": limit, "offset": offset,
        "items": [_rec_dict(r) for r in records],
    }


def _rec_dict(r: Recording) -> dict:
    return {
        "id": r.id, "camera_name": r.camera_name, "filename": r.filename,
        "relative_path": r.relative_path, "file_size": r.file_size,
        "duration": r.duration, "width": r.width, "height": r.height,
        "codec": r.codec, "media_type": getattr(r, "media_type", "video"),
        "recorded_at": r.recorded_at.isoformat() if r.recorded_at else None,
        "event_type": r.event_type, "thumbnail_path": r.thumbnail_path,
    }


@app.get("/api/recordings/timeline")
def get_timeline_data(
    date: str = Query(..., description="Date formatted as YYYY-MM-DD"),
    camera: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Return all recording events on a given day for timeline track rendering."""
    try:
        day_start = datetime.strptime(date, "%Y-%m-%d")
        day_end = datetime(day_start.year, day_start.month, day_start.day, 23, 59, 59, 999999)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format, expected YYYY-MM-DD")

    query = db.query(Recording).filter(
        Recording.recorded_at >= day_start,
        Recording.recorded_at <= day_end,
    )
    if camera:
        query = query.filter(Recording.camera_name == camera)

    # Sort ascending for timeline flow
    records = query.order_by(Recording.recorded_at.asc(), Recording.id.asc()).all()

    items = []
    for r in records:
        start_dt = r.recorded_at
        dur = float(r.duration or 0)
        # For images or 0-duration videos, default visual segment duration to 5 seconds
        if dur <= 0:
            dur = 5.0
        start_sec = start_dt.hour * 3600 + start_dt.minute * 60 + start_dt.second + start_dt.microsecond / 1_000_000.0
        end_sec = min(86400.0, start_sec + dur)
        items.append({
            "id": r.id,
            "camera_name": r.camera_name,
            "filename": r.filename,
            "recorded_at": start_dt.isoformat(),
            "start_sec": round(start_sec, 2),
            "end_sec": round(end_sec, 2),
            "duration": dur,
            "event_type": r.event_type or "regular",
            "media_type": getattr(r, "media_type", "video"),
            "thumbnail_path": r.thumbnail_path,
        })

    return {
        "date": date,
        "camera": camera,
        "count": len(items),
        "items": items,
    }


@app.get("/api/recordings/days")
def get_recording_days(
    camera: Optional[str] = None,
    media_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Return list of {date, count} for all days that have recordings."""
    from sqlalchemy import cast, Date as SADate
    query = db.query(
        cast(Recording.recorded_at, SADate).label("day"),
        func.count(Recording.id).label("cnt"),
    )
    if camera:
        query = query.filter(Recording.camera_name == camera)
    if media_type in ("video", "image"):
        query = query.filter(Recording.media_type == media_type)
    rows = query.group_by("day").order_by(desc("day")).all()
    return {"days": [{"date": str(r.day), "count": r.cnt} for r in rows]}


@app.get("/api/recordings/{rec_id}/stream")
def stream_video(rec_id: int, db: Session = Depends(get_db)):
    rec = db.query(Recording).filter(Recording.id == rec_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")
    # Path-traversal guard
    try:
        storage_svc.resolve_allowed_directory(str(os.path.dirname(rec.file_path)), require_exists=True)
    except ValueError:
        raise HTTPException(status_code=403, detail="File outside allowed storage")
    if not os.path.exists(rec.file_path):
        raise HTTPException(status_code=404, detail="File not found")
    # Serve with the correct content type for videos or images
    content_type = mimetypes.guess_type(rec.file_path)[0] or "application/octet-stream"
    return FileResponse(rec.file_path, media_type=content_type)


@app.get("/api/recordings/{rec_id}/thumbnail")
def get_recording_thumbnail(rec_id: int, db: Session = Depends(get_db)):
    rec = db.query(Recording).filter(Recording.id == rec_id).first()
    if not rec or not rec.thumbnail_path:
        raise HTTPException(status_code=404, detail="Thumbnail not available")
    thumb_full = os.path.join("/data/thumbnails", rec.thumbnail_path)
    if not os.path.exists(thumb_full):
        raise HTTPException(status_code=404, detail="Thumbnail file missing")
    return FileResponse(thumb_full, media_type="image/jpeg")

# ---------------------------------------------------------------------------
# Static frontend (must be last)
# ---------------------------------------------------------------------------
FRONTEND_DIR = "/app/frontend/dist"
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
