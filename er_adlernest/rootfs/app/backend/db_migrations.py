"""SQLite schema upgrades, independent of the application's ORM."""
import re
import sqlite3


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
