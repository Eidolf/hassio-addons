"""SQLite schema upgrades, independent of the application's ORM."""
import os
import re
import sqlite3
import logging
from typing import Optional
from datetime import datetime, timedelta

logger = logging.getLogger("adlernest")


_ADDITIONS = (
    ("ha_entity_id", "ALTER TABLE cameras ADD COLUMN ha_entity_id VARCHAR(200)"),
    ("folder_mapping", "ALTER TABLE cameras ADD COLUMN folder_mapping VARCHAR(255)"),
    ("highres_stream_url", "ALTER TABLE cameras ADD COLUMN highres_stream_url VARCHAR(500)"),
    ("highres_ha_entity_id", "ALTER TABLE cameras ADD COLUMN highres_ha_entity_id VARCHAR(200)"),
    ("fullscreen_highres", "ALTER TABLE cameras ADD COLUMN fullscreen_highres BOOLEAN NOT NULL DEFAULT 0"),
)


def _make_stream_url_nullable(conn: sqlite3.Connection) -> None:
    columns = conn.execute("PRAGMA table_info(cameras)").fetchall()
    if not any(row[1] == "stream_url" and row[3] for row in columns):
        return

    original_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='cameras'"
    ).fetchone()[0]
    # Change only the known legacy declaration; retain all other constraints.
    new_sql, changed = re.subn(
        r"(\bstream_url\s+VARCHAR\s*\(\s*500\s*\))\s+NOT\s+NULL\b",
        r"\1", original_sql, flags=re.IGNORECASE,
    )
    if changed != 1:
        raise sqlite3.DatabaseError("Unsupported legacy cameras.stream_url declaration")
    new_sql, renamed = re.subn(
        r'^CREATE\s+TABLE\s+(?:"cameras"|cameras)\s*\(',
        'CREATE TABLE "cameras_nullable_migration" (',
        new_sql, count=1, flags=re.IGNORECASE,
    )
    if renamed != 1:
        raise sqlite3.DatabaseError("Unsupported legacy cameras table declaration")

    schema_objects = conn.execute(
        "SELECT sql FROM sqlite_master WHERE tbl_name='cameras' "
        "AND type IN ('index', 'trigger') AND sql IS NOT NULL"
    ).fetchall()
    names = ", ".join('"' + row[1].replace('"', '""') + '"' for row in columns)
    conn.execute(new_sql)
    conn.execute(
        f'INSERT INTO cameras_nullable_migration ({names}) SELECT {names} FROM cameras'
    )
    conn.execute("DROP TABLE cameras")
    conn.execute("ALTER TABLE cameras_nullable_migration RENAME TO cameras")
    for (sql,) in schema_objects:
        conn.execute(sql)


def migrate_database(db_path: str) -> None:
    """Upgrade atomically; preserve camera rows, indexes, triggers and references."""
    conn = sqlite3.connect(db_path)
    try:
        # SQLite's table-rebuild procedure requires FK enforcement disabled before
        # BEGIN. Validate references before committing instead (no cascade deletes).
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("BEGIN IMMEDIATE")
        columns = {row[1] for row in conn.execute("PRAGMA table_info(cameras)")}
        if columns:
            for column, sql in _ADDITIONS:
                if column not in columns:
                    conn.execute(sql)
            _make_stream_url_nullable(conn)
        recording_columns = {row[1] for row in conn.execute("PRAGMA table_info(recordings)")}
        if recording_columns and "media_type" not in recording_columns:
            conn.execute("ALTER TABLE recordings ADD COLUMN media_type VARCHAR(10) NOT NULL DEFAULT 'video'")
        if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise sqlite3.IntegrityError("Foreign key validation failed during migration")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def correlate_timeline_events(raw_items: list) -> list:
    """Group and correlate snapshots (images) to corresponding videos of the same camera."""
    by_cam = {}
    for it in raw_items:
        by_cam.setdefault(it["camera_name"], []).append(it)

    items = []
    for cam_name, cam_items in by_cam.items():
        vids = [i for i in cam_items if i.get("media_type") == "video"]
        imgs = [i for i in cam_items if i.get("media_type") == "image"]

        vids.sort(key=lambda x: x["start_sec"])
        for v in vids:
            v["snapshots"] = []

        for img in imgs:
            t = img["start_sec"]
            matched_vid = None
            best_diff = float("inf")
            for v in vids:
                # Correlate if snapshot occurred near or within video window (with +/- 45s leeway)
                if (v["start_sec"] - 45.0) <= t <= (v["end_sec"] + 45.0):
                    mid = (v["start_sec"] + v["end_sec"]) / 2.0
                    diff = abs(t - mid)
                    if diff < best_diff:
                        best_diff = diff
                        matched_vid = v

            if matched_vid is not None:
                matched_vid["snapshots"].append({
                    "id": img["id"],
                    "filename": img["filename"],
                    "recorded_at": img["recorded_at"],
                    "start_sec": img["start_sec"],
                    "thumbnail_path": img["thumbnail_path"],
                    "event_type": img["event_type"],
                })
                # If video has no thumbnail yet or snapshot has richer AI detection/event, inherit thumbnail
                if not matched_vid.get("thumbnail_path") and img.get("thumbnail_path"):
                    matched_vid["thumbnail_path"] = img["thumbnail_path"]
                if matched_vid.get("event_type") in ("regular", "motion", None) and img.get("event_type") not in ("regular", "motion", None):
                    matched_vid["event_type"] = img["event_type"]

        # Timeline is strictly videos; images serve exclusively as thumbprints and overlays
        items.extend(vids)

    items.sort(key=lambda x: (x["start_sec"], x["id"]))
    return items


def run_retention_cleanup_sync(root_dir: str, retention_rules: dict, thumb_dir: str = "/data/thumbnails", db_path: Optional[str] = None) -> dict:
    """Purge recording files, database rows, and thumbnails older than configured retention days using sqlite3 directly."""
    stats = {"deleted_videos": 0, "deleted_images": 0, "deleted_thumbnails": 0}
    if not retention_rules:
        return stats

    target_db = db_path or os.getenv("DB_PATH", "/data/adlernest.db")
    if not os.path.exists(target_db):
        return stats

    now = datetime.utcnow()
    conn = sqlite3.connect(target_db)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        for subfolder, rules in retention_rules.items():
            if not isinstance(rules, dict):
                continue
            video_days = int(rules.get("video_days", 0) or 0)
            image_days = int(rules.get("image_days", 0) or 0)
            if video_days <= 0 and image_days <= 0:
                continue

            folder_clean = subfolder.strip("/")
            cursor = conn.execute(
                """
                SELECT id, camera_name, file_path, relative_path, media_type, recorded_at, thumbnail_path
                FROM recordings
                WHERE camera_name = ?
                   OR relative_path LIKE ?
                   OR relative_path LIKE ?
                """,
                (subfolder, f"{folder_clean}/%", f"{folder_clean}\\%")
            )
            rows = cursor.fetchall()
            ids_to_delete = []

            for r_id, cam_name, file_path, rel_path, media_type, rec_at_raw, thumb_path in rows:
                mtype = media_type or "video"
                limit_days = image_days if mtype == "image" else video_days
                if limit_days <= 0:
                    continue

                try:
                    # ISO format parsing or sqlite timestamp
                    rec_at = datetime.fromisoformat(rec_at_raw) if isinstance(rec_at_raw, str) else rec_at_raw
                except Exception:
                    continue

                if rec_at < (now - timedelta(days=limit_days)):
                    # Delete physical file
                    if file_path and os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                        except OSError as exc:
                            logger.warning("Could not delete expired file %s: %s", file_path, exc)

                    # Delete thumbnail
                    if thumb_path:
                        t_full = os.path.join(thumb_dir, thumb_path)
                        if os.path.exists(t_full):
                            try:
                                os.remove(t_full)
                                stats["deleted_thumbnails"] += 1
                            except OSError:
                                pass

                    if mtype == "image":
                        stats["deleted_images"] += 1
                    else:
                        stats["deleted_videos"] += 1
                    ids_to_delete.append(r_id)

            if ids_to_delete:
                placeholders = ",".join("?" for _ in ids_to_delete)
                conn.execute(f"DELETE FROM recordings WHERE id IN ({placeholders})", ids_to_delete)

        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.error("Retention cleanup error: %s", exc)
    finally:
        conn.close()

    if stats["deleted_videos"] or stats["deleted_images"]:
        logger.info(
            "Retention cleanup finished: deleted_videos=%d deleted_images=%d deleted_thumbnails=%d",
            stats["deleted_videos"], stats["deleted_images"], stats["deleted_thumbnails"]
        )
    return stats

