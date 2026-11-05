"""Background indexer: scan a directory tree and register video files in the DB."""
import json
import logging
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from models import Recording, Camera, SessionLocal

logger = logging.getLogger("adlernest.indexer")
SUPPORTED_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".ts"}
# Minimum file age in seconds before a file is treated as fully written
_STABILITY_SECS = 5


def extract_metadata(file_path: str):
    """Return (duration, width, height, codec) via ffprobe. Falls back to defaults."""
    try:
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", "--", file_path,
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, timeout=10, check=False)
        if not result.stdout.strip():
            return 0.0, 1920, 1080, "unknown"
        data = json.loads(result.stdout)
        duration = float(data.get("format", {}).get("duration", 0.0) or 0.0)
        vstream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
        width = int(vstream.get("width", 1920) or 1920)
        height = int(vstream.get("height", 1080) or 1080)
        codec = vstream.get("codec_name", "h264") or "h264"
        return duration, width, height, codec
    except Exception as exc:
        logger.debug("ffprobe fallback for %s: %s", file_path, exc)
        return 0.0, 1920, 1080, "unknown"


def generate_thumbnail(video_path: str, thumb_path: str) -> bool:
    """Generate a JPEG thumbnail. Returns True on success."""
    try:
        os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
        cmd = [
            "ffmpeg", "-y", "-ss", "00:00:01", "-i", video_path,
            "-vframes", "1", "-vf", "scale=480:-1", "--", thumb_path,
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=10, check=False)
        return os.path.exists(thumb_path)
    except Exception as exc:
        logger.debug("Thumbnail skipped for %s: %s", video_path, exc)
        return False


def parse_recording_info(file_path: str, root_dir: str, folder_mappings: dict):
    """Derive (camera_name, rel_path, filename, size, mtime, recorded_at, event_type) from a file."""
    p = Path(file_path)
    rel = p.relative_to(root_dir)
    parts = rel.parts

    # Longest-prefix folder → camera mapping
    camera_name = "DefaultCamera"
    if len(parts) > 1:
        top_folder = parts[0]
        camera_name = folder_mappings.get(top_folder, top_folder)

    try:
        stat = p.stat()
        file_size = stat.st_size
        mtime = stat.st_mtime
        recorded_at = datetime.fromtimestamp(mtime)
    except OSError:
        file_size = 0
        mtime = 0.0
        recorded_at = datetime.utcnow()

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

    return camera_name, str(rel), p.name, file_size, mtime, recorded_at, event_type


def scan_directory_sync(root_dir: str, thumb_dir: str = "/data/thumbnails") -> int:
    """Scan *root_dir* recursively and index new/changed video files. Returns new-record count."""
    if not root_dir or not os.path.exists(root_dir):
        logger.info("Scan path '%s' does not exist; skipping.", root_dir)
        return 0
    if not os.access(root_dir, os.R_OK):
        logger.warning("Scan path '%s' is not readable; skipping.", root_dir)
        return 0

    t_start = time.monotonic()
    logger.info("Scan started: %s", root_dir)
    db: Session = SessionLocal()
    new_records = 0
    skipped = 0
    updated = 0
    errors = 0

    try:
        cams = db.query(Camera).all()
        folder_mappings = {c.folder_mapping.strip(): c.name for c in cams if c.folder_mapping}

        for dirpath, _dirs, files in os.walk(root_dir, followlinks=False):
            for filename in files:
                if Path(filename).suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue
                full_path = os.path.join(dirpath, filename)

                try:
                    stat = os.stat(full_path)
                    # Skip files that are still being written
                    if time.time() - stat.st_mtime < _STABILITY_SECS:
                        logger.debug("Skipping unstable file: %s", full_path)
                        skipped += 1
                        continue

                    existing = (
                        db.query(Recording)
                        .filter(Recording.file_path == full_path)
                        .first()
                    )

                    if existing:
                        # Re-index if size or mtime changed
                        if existing.file_size == stat.st_size and abs(
                            existing.recorded_at.timestamp() - stat.st_mtime
                        ) < 1:
                            skipped += 1
                            continue

                    cam_name, rel_path, fname, size, mtime, recorded_at, event_type = (
                        parse_recording_info(full_path, root_dir, folder_mappings)
                    )
                    duration, width, height, codec = extract_metadata(full_path)

                    thumb_filename = f"thumb_{abs(hash(full_path))}.jpg"
                    thumb_full = os.path.join(thumb_dir, thumb_filename)
                    if generate_thumbnail(full_path, thumb_full):
                        thumb_rel = thumb_filename
                    else:
                        thumb_rel = None

                    if existing:
                        existing.camera_name = cam_name
                        existing.relative_path = rel_path
                        existing.filename = fname
                        existing.file_size = size
                        existing.duration = duration
                        existing.width = width
                        existing.height = height
                        existing.codec = codec
                        existing.recorded_at = recorded_at
                        existing.event_type = event_type
                        if thumb_rel:
                            existing.thumbnail_path = thumb_rel
                        updated += 1
                    else:
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
                            thumbnail_path=thumb_rel,
                        )
                        db.add(rec)
                        new_records += 1

                    if (new_records + updated) % 25 == 0:
                        db.commit()

                except OSError as exc:
                    logger.warning("Skipping unreadable file %s: %s", full_path, exc)
                    errors += 1
                except Exception as exc:
                    logger.warning("Skipping problematic file %s: %s", full_path, exc)
                    errors += 1
                    try:
                        db.rollback()
                    except Exception:
                        pass

        db.commit()
    except OSError as exc:
        logger.error("Scan aborted (NAS/IO error) for %s: %s", root_dir, exc)
        try:
            db.rollback()
        except Exception:
            pass
    except Exception as exc:
        logger.error("Scan error for %s: %s", root_dir, exc)
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()

    elapsed = time.monotonic() - t_start
    if new_records or updated:
        logger.info(
            "Scan finished: %s | new=%d updated=%d skipped=%d errors=%d elapsed=%.1fs",
            root_dir, new_records, updated, skipped, errors, elapsed,
        )
    else:
        logger.debug(
            "Scan finished (no changes): %s | skipped=%d errors=%d elapsed=%.1fs",
            root_dir, skipped, errors, elapsed,
        )
    return new_records
