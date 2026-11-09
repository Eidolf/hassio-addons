"""Test retention cleanup functionality."""
import os
import sys
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1] / "rootfs/app/backend"
sys.path.insert(0, str(backend_dir))

from db_migrations import run_retention_cleanup_sync

class RetentionCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.thumb_dir = os.path.join(self.temp_dir.name, "thumbnails")
        os.makedirs(self.thumb_dir, exist_ok=True)
        self.db_path = os.path.join(self.temp_dir.name, "test_retention.db")

        # Create recordings table matching schema
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE recordings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_name VARCHAR(100) NOT NULL,
                file_path VARCHAR(1000) UNIQUE NOT NULL,
                relative_path VARCHAR(1000) NOT NULL,
                filename VARCHAR(255) NOT NULL,
                file_size INTEGER DEFAULT 0,
                duration FLOAT DEFAULT 0.0,
                width INTEGER DEFAULT 1920,
                height INTEGER DEFAULT 1080,
                codec VARCHAR(50) DEFAULT 'h264',
                media_type VARCHAR(10) NOT NULL DEFAULT 'video',
                recorded_at DATETIME NOT NULL,
                event_type VARCHAR(50) DEFAULT 'regular',
                thumbnail_path VARCHAR(1000),
                created_at DATETIME
            );
        """)
        conn.close()

    def test_purges_expired_videos_and_images(self):
        now = datetime.utcnow()

        # Create dummy physical files
        vid_old_file = os.path.join(self.temp_dir.name, "old_video.mp4")
        with open(vid_old_file, "wb") as f:
            f.write(b"video data")

        vid_new_file = os.path.join(self.temp_dir.name, "new_video.mp4")
        with open(vid_new_file, "wb") as f:
            f.write(b"video data")

        img_old_file = os.path.join(self.temp_dir.name, "old_snap.jpg")
        with open(img_old_file, "wb") as f:
            f.write(b"image data")

        thumb_file = os.path.join(self.thumb_dir, "thumb_old_video.jpg")
        with open(thumb_file, "wb") as f:
            f.write(b"thumb data")

        conn = sqlite3.connect(self.db_path)
        # 1. Video 40 days old (should be purged if video_days=30)
        conn.execute("""
            INSERT INTO recordings (camera_name, file_path, relative_path, filename, media_type, recorded_at, thumbnail_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("Einfahrt", vid_old_file, "Einfahrt/old_video.mp4", "old_video.mp4", "video", (now - timedelta(days=40)).isoformat(), "thumb_old_video.jpg"))

        # 2. Video 10 days old (should be kept)
        conn.execute("""
            INSERT INTO recordings (camera_name, file_path, relative_path, filename, media_type, recorded_at, thumbnail_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("Einfahrt", vid_new_file, "Einfahrt/new_video.mp4", "new_video.mp4", "video", (now - timedelta(days=10)).isoformat(), None))

        # 3. Image 15 days old (should be purged if image_days=7)
        conn.execute("""
            INSERT INTO recordings (camera_name, file_path, relative_path, filename, media_type, recorded_at, thumbnail_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("Einfahrt", img_old_file, "Einfahrt/old_snap.jpg", "old_snap.jpg", "image", (now - timedelta(days=15)).isoformat(), None))
        conn.commit()
        conn.close()

        rules = {
            "Einfahrt": {
                "video_days": 30,
                "image_days": 7
            }
        }

        stats = run_retention_cleanup_sync(self.temp_dir.name, rules, thumb_dir=self.thumb_dir, db_path=self.db_path)

        self.assertEqual(stats["deleted_videos"], 1)
        self.assertEqual(stats["deleted_images"], 1)
        self.assertEqual(stats["deleted_thumbnails"], 1)

        # Check physical files deleted
        self.assertFalse(os.path.exists(vid_old_file))
        self.assertFalse(os.path.exists(img_old_file))
        self.assertFalse(os.path.exists(thumb_file))
        self.assertTrue(os.path.exists(vid_new_file))

        # Check DB rows
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT filename FROM recordings").fetchall()
        conn.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "new_video.mp4")

if __name__ == "__main__":
    unittest.main()
