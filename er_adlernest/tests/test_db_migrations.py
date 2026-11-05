"""Run with: python3 -B -m unittest discover -s er_adlernest/tests -v."""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "rootfs/app/backend"))
from db_migrations import migrate_database


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / "legacy.db")
        self.conn = sqlite3.connect(self.path)
        self.addCleanup(self.conn.close)

    def legacy_schema(self, declaration="VARCHAR(500) NOT NULL"):
        self.conn.executescript(f"""
            CREATE TABLE cameras (
                id INTEGER NOT NULL PRIMARY KEY,
                name VARCHAR(100) NOT NULL UNIQUE,
                source_type VARCHAR(50),
                stream_url {declaration},
                substream_url VARCHAR(500),
                fps INTEGER DEFAULT 15,
                enabled BOOLEAN DEFAULT 1,
                created_at DATETIME
            );
            CREATE INDEX ix_cameras_id ON cameras(id);
            CREATE TABLE audit (camera_id INTEGER);
            CREATE TRIGGER camera_added AFTER INSERT ON cameras
                BEGIN INSERT INTO audit VALUES (new.id); END;
            CREATE TABLE recordings (
                id INTEGER PRIMARY KEY,
                camera_id INTEGER REFERENCES cameras(id) ON DELETE CASCADE,
                file_path TEXT NOT NULL
            );
            INSERT INTO cameras (id, name, source_type, stream_url)
                VALUES (7, 'Existing RTSP', 'rtsp', 'rtsp://example/live');
            INSERT INTO recordings VALUES (1, 7, '/media/existing.mp4');
        """)

    def test_legacy_rows_constraints_indexes_triggers_and_references_survive(self):
        self.legacy_schema()
        migrate_database(self.path)
        self.assertEqual(self.conn.execute(
            "SELECT id, name, stream_url, fps, enabled FROM cameras"
        ).fetchall(), [(7, "Existing RTSP", "rtsp://example/live", 15, 1)])
        self.assertEqual(self.conn.execute("SELECT * FROM recordings").fetchall(),
                         [(1, 7, "/media/existing.mp4")])
        self.assertEqual(self.conn.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertIsNotNone(self.conn.execute(
            "SELECT name FROM sqlite_master WHERE name='ix_cameras_id'"
        ).fetchone())
        self.conn.execute("INSERT INTO cameras (name, source_type, stream_url, ha_entity_id, "
                          "folder_mapping) VALUES (?, ?, ?, ?, ?)",
                          ("Terrasse", "ha_camera", None, "camera.terrasse", "terrasse"))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0], 2)
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("INSERT INTO cameras (name) VALUES ('Terrasse')")
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("INSERT INTO cameras (name) VALUES (NULL)")
        self.conn.commit()

    def test_second_run_is_a_noop(self):
        self.legacy_schema()
        migrate_database(self.path)
        before = self.conn.execute("SELECT type, name, sql FROM sqlite_master ORDER BY name").fetchall()
        migrate_database(self.path)
        self.assertEqual(before, self.conn.execute(
            "SELECT type, name, sql FROM sqlite_master ORDER BY name").fetchall())

    def test_current_nullable_schema_needs_no_rebuild(self):
        self.legacy_schema("VARCHAR(500)")
        migrate_database(self.path)
        self.conn.execute("INSERT INTO cameras (name, stream_url) VALUES ('HA', NULL)")
        self.conn.commit()
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM cameras").fetchone()[0], 2)

    def test_unsupported_schema_rolls_back_all_changes(self):
        self.legacy_schema("TEXT NOT NULL")
        before = self.conn.execute("SELECT type, name, sql FROM sqlite_master ORDER BY name").fetchall()
        with self.assertRaisesRegex(sqlite3.DatabaseError, "Unsupported legacy"):
            migrate_database(self.path)
        self.assertEqual(before, self.conn.execute(
            "SELECT type, name, sql FROM sqlite_master ORDER BY name").fetchall())
        self.assertEqual(self.conn.execute("SELECT stream_url FROM cameras").fetchall(),
                         [("rtsp://example/live",)])

    def test_foreign_key_failure_rolls_back_rebuild(self):
        self.legacy_schema()
        self.conn.execute("INSERT INTO recordings VALUES (2, 999, '/media/orphan.mp4')")
        self.conn.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            migrate_database(self.path)
        columns = {row[1]: row for row in self.conn.execute("PRAGMA table_info(cameras)")}
        self.assertEqual(columns["stream_url"][3], 1)
        self.assertNotIn("ha_entity_id", columns)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM recordings").fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
