# Changelog - ER-Adlernest

All notable changes to the ER-Adlernest Home Assistant Add-on will be documented in this file.

## [1.2.1] - 2026-11-05

### Fixed
- **Timeline Ruler & Clip Alignment**:
  - Aligned the 24h timeline ruler exactly with camera clip tracks by adding an aligned header spacer corresponding to the camera label column width.
  - Eliminated the offset where timeline segments were shifted relative to the ruler scale and red playhead indicator.
- **Timeline Play/Pause Button State**:
  - Fixed HTML rendering of icon and label on `tlPlayPauseBtn` by properly updating `innerHTML` instead of `textContent` (`<i class="bi bi-pause-fill"></i> Pause`).

### Added
- **Multi-Level Timeline Zoom & Pan**:
  - Added Timeline Zoom controls: `24h` (1x), `12h` (2x), `6h` (4x), `3h` (8x), and `1.5h` (16x).
  - Synchronized horizontal scrolling across the ruler and camera tracks with smooth auto-centering on the playhead.
  - Mouse wheel and drag panning across zoomed timeline sections to quickly locate and scrub key recording events.

## [1.2.0] - 2026-11-05

### Added
- **Multi-Track CCTV 24h Timeline**:
  - Dedicated "Timeline 24h" navigation tab with an interactive 24-hour ruler.
  - Multi-track timeline view displaying parallel recording tracks for all cameras simultaneously.
  - Interactive scrubbing: Click or drag the playhead marker along the 24h timeline to seek and play recordings directly.
  - Single-camera focus: Click on camera labels or filter dropdown to isolate a single camera's timeline.
  - Playback controls: Play/pause, fast forward/rewind 10s, playback speed (0.5x, 1x, 2x, 4x, 8x), fullscreen, and automatic playback transition to subsequent clips.
  - Direct "TIMELINE" shortcut button on live camera cards in the Live Matrix tab.
  - Backend API endpoint `/api/recordings/timeline` with date and camera filtering.

### Fixed
- **Mobile Responsive Camera Management**:
  - Fixed issue where camera cards in "Cameras & Mappings" overflowed the mobile screen width, hiding the edit and delete buttons.
  - Added word-break protection for long stream URLs and HA entity IDs.
  - Implemented responsive column stacking for camera cards on small screens (`<= 768px`).

## [1.1.5] - 2026-11-05

### Added
- **Mobile Navigation Touch Scrolling**:
  - Menubar (`.nav-tabs`) can now be swiped horizontally on touchscreens without shifting the entire page.
  - Hidden scrollbars with smooth `-webkit-overflow-scrolling: touch`.
  - Added overflow protection (`html, body { max-width: 100%; overflow-x: hidden; }`) against page shifting.

## [1.1.4] - 2026-11-05

### Added
- **Live Matrix Fullscreen & HighRes**:
  - Fullscreen view for live camera cards with HighRes stream/snapshot toggling.
  - Direct archive navigation shortcut on camera cards.
  - Camera edit modal (`openEditCameraModal`) with support for HighRes stream and HA entity IDs.
- Clean UI: Stats bar hidden on the Live Matrix tab for a cleaner dashboard view.

### Fixed
- Fixed HighRes HA entity dropdown population in the camera edit modal.

## [1.1.3] - 2026-11-05

### Added
- **Image Archive Support**:
  - Image file indexing (`jpg`, `jpeg`, `png`, `webp`, `bmp`) with EXIF rotation correction and thumbnail caching.
  - Media type filter (All, Videos, Images) in the archive tab.
  - Lightbox modal for image viewing.
  - Day timeline strip with recording counts per day (`/api/recordings/days`).
  - Additive database migration for `media_type` column.

## [1.1.2] - 2026-11-05

### Added
- **Archive Pagination**:
  - 50 recordings per page with Previous/Next controls and page indicators.
  - Stale response guard (`archiveRequestId`) against race conditions during rapid filter changes.

## [1.1.1] - 2026-11-05

### Fixed
- **Database Schema Migration**:
  - Transactional SQLite table rebuild (`db_migrations.py`) allowing `cameras.stream_url` to be nullable for Home Assistant camera entities.

## [1.1.0] - 2026-11-05

### Added
- Dynamic SMB/CIFS mount management via UI and backend (`storage.py`).
- Directory browser for storage paths.

## [1.0.4] - 2026-11-04

### Fixed
- Ingress relative path routing for API calls.

## [1.0.3] - 2026-11-04

### Fixed
- JSON serialization fixes on camera endpoints.

## [1.0.2] - 2026-11-03

### Added
- Tactical cyber-security CCTV UI theme.
- SQLite auto-migration helper.

## [1.0.1] - 2026-11-03

### Fixed
- Resolved 502 Bad Gateway during heavy startup directory scans.

## [1.0.0] - 2026-11-03

### Added
- Initial release of ER-Adlernest Add-on for Home Assistant.

