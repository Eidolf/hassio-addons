"""Test correlation and thumbprint attaching for timeline recordings."""
import sys
import unittest
from datetime import datetime
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parents[1] / "rootfs/app/backend"
sys.path.insert(0, str(backend_dir))

from db_migrations import correlate_timeline_events

class TimelineCorrelationTests(unittest.TestCase):
    def test_correlates_image_as_thumbprint_to_video(self):
        raw_items = [
            {
                "id": 1,
                "camera_name": "Einfahrt",
                "filename": "einfahrt_1000.mp4",
                "recorded_at": "2026-11-06T10:00:00",
                "start_sec": 36000.0,
                "end_sec": 36060.0,
                "duration": 60.0,
                "event_type": "motion",
                "media_type": "video",
                "thumbnail_path": None,
            },
            {
                "id": 2,
                "camera_name": "Einfahrt",
                "filename": "einfahrt_snap_100015.jpg",
                "recorded_at": "2026-11-06T10:00:15",
                "start_sec": 36015.0,
                "end_sec": 36020.0,
                "duration": 5.0,
                "event_type": "person",
                "media_type": "image",
                "thumbnail_path": "thumb_person_einfahrt.jpg",
            },
            {
                "id": 3,
                "camera_name": "Einfahrt",
                "filename": "einfahrt_snap_180000.jpg",
                "recorded_at": "2026-11-06T18:00:00",
                "start_sec": 64800.0,
                "end_sec": 64805.0,
                "duration": 5.0,
                "event_type": "regular",
                "media_type": "image",
                "thumbnail_path": "thumb_solo.jpg",
            },
        ]

        items = correlate_timeline_events(raw_items)

        # Expect 2 items: the merged video with snapshot attached, and the standalone snapshot
        self.assertEqual(len(items), 2)

        merged_vid = [i for i in items if i["id"] == 1][0]
        self.assertEqual(merged_vid["media_type"], "video")
        self.assertEqual(len(merged_vid["snapshots"]), 1)
        self.assertEqual(merged_vid["snapshots"][0]["id"], 2)
        # Inherited thumbnail from snapshot for thumbprint
        self.assertEqual(merged_vid["thumbnail_path"], "thumb_person_einfahrt.jpg")
        # Promoted event_type to "person"
        self.assertEqual(merged_vid["event_type"], "person")

        solo_item = [i for i in items if i["id"] == 3][0]
        self.assertEqual(solo_item["media_type"], "image")
        self.assertEqual(solo_item["thumbnail_path"], "thumb_solo.jpg")

if __name__ == "__main__":
    unittest.main()

