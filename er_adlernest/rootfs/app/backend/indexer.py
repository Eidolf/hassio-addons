import os
import json
import logging
import asyncio
import subprocess
from datetime import datetime
from pathlib import Path
from sqlalchemy.orm import Session
from models import Recording, Camera, SessionLocal

logger = logging.getLogger("adlernest.indexer")
SUPPORTED_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".ts"}

def extract_metadata(file_path: str):
    """Extract metadata (duration, width, height, codec) using ffprobe safely."""
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            file_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        if not result.stdout or not result.stdout.strip():
            return 0.0, 1920, 1080, "unknown"
            
        data = json.loads(result.stdout)
        duration = float(data.get("format", {}).get("duration", 0.0) or 0.0)
        video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
        width = int(video_stream.get("width", 1920) or 1920)
        height = int(video_stream.get("height", 1080) or 1080)
        codec = video_stream.get("codec_name", "h264") or "h264"
        return duration, width, height, codec
    except Exception as e:
        logger.debug(f"ffprobe fallback for {file_path}: {e}")
        return 0.0, 1920, 1080, "unknown"

def generate_thumbnail(video_path: str, thumb_path: str):
    """Generate preview thumbnail from video safely."""
    try:
        os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
        cmd = [
            "ffmpeg",
            "-y",
            "-ss", "00:00:01",
            "-i", video_path,
            "-vframes", "1",
            "-vf", "scale=480:-1",
            thumb_path
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        return os.path.exists(thumb_path)
    except Exception as e:
        logger.debug(f"Thumbnail skipped for {video_path}: {e}")
        return False

def parse_recording_info(file_path: str, root_dir: str, folder_mappings: dict):
    """Deduce camera name, date, event type from filename/directory structure and folder mappings."""
    p = Path(file_path)
    rel = p.relative_to(root_dir)
    parts = rel.parts

    # First check mapped folder
    camera_name = "DefaultCamera"
    if len(parts) > 1:
        top_folder = parts[0]
        # Check explicit camera folder mapping
        camera_name = folder_mappings.get(top_folder, top_folder)

    # File modification time & size
    try:
        stat = p.stat()
        file_size = stat.st_size
        recorded_at = datetime.fromtimestamp(stat.st_mtime)
    except Exception:
        file_size = 0
        recorded_at = datetime.utcnow()

    # Detect event type from name patterns (Reolink / FTP standards)
    fname_lower = p.name.lower()
    event_type = "regular"
    if "person" in fname_lower:
        event_type = "person"
    elif "vehicle" in fname_lower or "car" in fname_lower:
        event_type = "vehicle"
    elif "motion" in fname_lower or "_m_" in fname_lower or "alarm" in fname_lower:
        event_type = "motion"
    elif "doorbell" in fname_lower or "ring" in fname_lower:
        event_type = "doorbell"

    return camera_name, str(rel), p.name, file_size, recorded_at, event_type

def scan_directory_sync(root_dir: str, thumb_dir: str = "/data/thumbnails"):
    """Scan directory recursively in background thread."""
    if not root_dir or not os.path.exists(root_dir):
        logger.info(f"Scan path '{root_dir}' does not exist yet. Waiting for configuration.")
        return 0

    logger.info(f"Scanning recordings directory: {root_dir}")
    db: Session = SessionLocal()
    new_records = 0

    try:
        # Load folder-to-camera mappings
        cams = db.query(Camera).all()
        folder_mappings = {}
        for cam in cams:
            if cam.folder_mapping:
                folder_mappings[cam.folder_mapping.strip()] = cam.name

        for root, _, files in os.walk(root_dir):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in SUPPORTED_EXTENSIONS:
                    full_path = os.path.join(root, file)
                    
                    try:
                        # Check if already indexed
                        existing = db.query(Recording.id).filter(Recording.file_path == full_path).first()
                        if existing:
                            continue

                        cam_name, rel_path, fname, size, recorded_at, event_type = parse_recording_info(full_path, root_dir, folder_mappings)
                        duration, width, height, codec = extract_metadata(full_path)
                        
                        thumb_filename = f"thumb_{abs(hash(full_path))}.jpg"
                        thumb_full_path = os.path.join(thumb_dir, thumb_filename)
                        if generate_thumbnail(full_path, thumb_full_path):
                            thumb_rel = thumb_filename
                        else:
                            thumb_rel = None

                        rec = Recording(
                            camera_name=cam_name,
                            file_path=full_path,
                            relative_path=rel_path,
                            filename=fname,
                            file_size=size,
                            duration=duration,
                            width=width,
                            height=height,
                            codec=codec,
                            recorded_at=recorded_at,
                            event_type=event_type,
                            thumbnail_path=thumb_rel
                        )
                        db.add(rec)
                        new_records += 1

                        if new_records % 25 == 0:
                            db.commit()
                    except Exception as item_err:
                        logger.warning(f"Skipping problematic file {full_path}: {item_err}")
                        continue

        db.commit()
        logger.info(f"Indexing finished: {new_records} new recordings discovered.")
    except Exception as e:
        logger.error(f"Error while indexing directory: {e}")
        db.rollback()
    finally:
        db.close()

    return new_records
