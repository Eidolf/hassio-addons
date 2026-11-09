"""Background indexer: scan a directory tree and register video files in the DB."""
import hashlib
import json

from PIL import Image, ImageOps
import logging
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from models import Recording, Camera, SessionLocal

logger = logging.getLogger("adlernest.indexer")
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".ts"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
SUPPORTED_EXTENSIONS = VIDEO_EXTENSIONS | IMAGE_EXTENSIONS
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


def extract_image(image_path: str, thumb_path: str):
    """Return (0.0, width, height, 'image', has_thumb) for a still image.

    Uses Pillow to read dimensions and write a JPEG thumbnail, respecting
    EXIF orientation so the thumbnail is always right-side up.
    """
    try:
        with Image.open(image_path) as img:
            img = ImageOps.exif_transpose(img)
            width, height = img.size
            os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
            thumb = img.copy()
            thumb.thumbnail((480, 480), Image.LANCZOS)
            thumb = thumb.convert("RGB")
            thumb.save(thumb_path, "JPEG", quality=85, optimize=True)
            return 0.0, width, height, "image", True
    except Exception as exc:
        logger.debug("Image thumbnail skipped for %s: %s", image_path, exc)
        try:
            width, height = Image.open(image_path).size
        except Exception:
            width, height = 0, 0
        return 0.0, width, height, "image", False


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

    # Match complete folder components; prefer the most specific mapping.
    camera_name = parts[0] if len(parts) > 1 else "DefaultCamera"
    best_length = -1
    for folder, name in folder_mappings.items():
        prefix = tuple(part for part in folder.replace("\\", "/").strip("/").split("/") if part)
        if prefix and len(prefix) < len(parts) and parts[:len(prefix)] == prefix:
            if len(prefix) > best_length:
                camera_name, best_length = name, len(prefix)

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

    pruned = 0
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

                    cam_name, rel_path, fname, size, mtime, recorded_at, event_type = (
                        parse_recording_info(full_path, root_dir, folder_mappings)
                    )
                    media_type = "image" if Path(filename).suffix.lower() in IMAGE_EXTENSIONS else "video"
                    if existing and existing.file_size == stat.st_size and abs(
                        existing.recorded_at.timestamp() - stat.st_mtime
                    ) < 1 and existing.media_type == media_type:
                        # Mapping changes must apply even when the file is unchanged.
                        if existing.camera_name != cam_name or existing.relative_path != rel_path:
                            existing.camera_name = cam_name
                            existing.relative_path = rel_path
                            updated += 1
                            if updated % 25 == 0:
                                db.commit()
                        else:
                            skipped += 1
                        continue

                    thumb_filename = f"thumb_{hashlib.sha256(full_path.encode()).hexdigest()[:24]}.jpg"
                    thumb_full = os.path.join(thumb_dir, thumb_filename)
                    if media_type == "image":
                        duration, width, height, codec, has_thumb = extract_image(full_path, thumb_full)
                    else:
                        duration, width, height, codec = extract_metadata(full_path)
                        has_thumb = generate_thumbnail(full_path, thumb_full)
                    if has_thumb:
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
                        existing.media_type = media_type
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
                            media_type=media_type,
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

        # Prune orphan database records whose physical files were deleted externally or by retention policy
        try:
            stored_records = db.query(Recording.id, Recording.file_path, Recording.thumbnail_path).all()
            missing_ids = []
            for r_id, f_path, t_rel in stored_records:
                if f_path and not os.path.exists(f_path):
                    missing_ids.append(r_id)
                    if t_rel:
                        t_full = os.path.join(thumb_dir, t_rel)
                        if os.path.exists(t_full):
                            try:
                                os.remove(t_full)
                            except OSError:
                                pass

            if missing_ids:
                # Delete in batches of 500
                for i in range(0, len(missing_ids), 500):
                    batch = missing_ids[i:i+500]
                    db.query(Recording).filter(Recording.id.in_(batch)).delete(synchronize_session=False)
                db.commit()
                pruned = len(missing_ids)
                logger.info("Pruned %d orphan database records whose files no longer exist", pruned)
        except Exception as exc:
            logger.warning("Error pruning orphan recordings: %s", exc)
            try:
                db.rollback()
            except Exception:
                pass

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
    if new_records or updated or pruned:
        logger.info(
            "Scan finished: %s | new=%d updated=%d pruned=%d skipped=%d errors=%d elapsed=%.1fs",
            root_dir, new_records, updated, pruned, skipped, errors, elapsed,
        )
    else:
        logger.debug(
            "Scan finished (no changes): %s | skipped=%d errors=%d elapsed=%.1fs",
            root_dir, skipped, errors, elapsed,
        )
    return new_records

