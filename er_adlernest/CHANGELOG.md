# Changelog - ER-Adlernest

All notable changes to the ER-Adlernest Home Assistant Add-on will be documented in this file.

## [1.3.0] - 2026-11-09

### Added
- **Tactical Live Matrix Layout Switcher**:
  - Added layout configuration buttons (`Auto`, `Compact`, `2-Col`, `Focus`, `Large`) in the Live View tab.
  - Allows adapting tile arrangement and video height based on screen size, camera count, or preferred spotlight focus.
  - Saves layout preference persistently in `localStorage`.
- **Modernized Floating Camera Header on Hover**:
  - Replaced the static header strip on camera cards with a sleek, translucent floating overlay header (`.cam-header`) with backdrop blur and pill buttons (`.cam-action-pill`).
  - Overlay automatically appears smoothly on mouse hover (or focus/touch) and stays hidden otherwise, providing an unobstructed full video stream view.
- **Per-Subfolder Retention Rules & Automatic Cleanup**:
  - Added customizable retention days for videos and images per camera / archive subfolder under "Storage & System".
  - Includes prominent advisory warning that image retention should not be shorter than video retention to prevent losing associated AI thumbprints on the timeline.
  - Automatic retention cleanup runs during scheduled background scans, with a "Clean Now" button for manual execution (`POST /api/archive/cleanup`).

## [1.2.9] - 2026-11-06

### Added
- **Modern Tactical Calendar Date Picker**:
  - Replaced native browser date input with a custom dark-themed interactive calendar dropdown overlay (`#tlCalendarDropdown`).
  - Features quick month navigation (`<` / `>`), active day highlighting, "Today" shortcut, and indicators (`dp-has-recordings`) for dates with existing footage queried via `/api/recordings/days`.

### Changed
- **Pure Video Timeline Stream**:
  - Image snapshots are now exclusively used as thumbprints, event descriptors, and overlay hover previews.
  - Excluded snapshot images from being rendered as standalone track entities on the timeline, eliminating clutter right before or during video clips and providing a completely clean video-centric timeline.
  - Increased snapshot-to-video correlation window to $\pm 45\text{s}$ to ensure pre-event AI detection snapshots accurately enrich their corresponding video recording.

## [1.2.8] - 2026-11-06

### Added
- **Timeline Hover Preview Popover**:
  - Hovering over any recording segment on the timeline displays a tactical popover window with a large preview image (snapshot / thumbnail).
  - Shows event metadata including camera name, event type tag (`PERSON`, `VEHICLE`, `MOTION`, etc.), exact recording time, duration, and count of correlated AI snapshots.
  - Automatically calculates viewport constraints, positioning itself above or below the cursor to remain visible at all times.

## [1.2.7] - 2026-11-06

### Added
- **Timeline Smart Snapshot Correlation & Video Thumbprints**:
  - Automatically associates snapshot images to video recordings on the same camera based on recording timestamps.
  - Snapshot images are no longer listed as redundant separate entities on the timeline; instead, they serve as rich visual thumbprints attached to the corresponding video clip.
  - Video clips inherit high-priority event types (e.g. `person`, `vehicle`) and detection snapshots from associated images.
  - At zoom level $\ge 4\times$ (6h, 3h, 1.5h), recording segments expand to 56px height and display the detected image thumbprint directly inside the timeline track bar.
  - Displays snapshot count badges on segments with multiple AI detections and in the timeline video player header.

## [1.2.6] - 2026-11-06

### Added
- **Native WebRTC & HLS Fullscreen Live Player with Audio**:
  - Fullscreen view upgraded from MJPEG to HTML5 `<video>` supporting native Home Assistant WebRTC (`camera/webrtc/offer`) and HLS (`camera/stream`).
  - Added direct audio playback support from camera entities (unmuted/controllable live audio feed).
  - Sub-second instant playback for High-Res (4K) streams via hardware-accelerated video decoder.
  - Added backend WebSocket proxy endpoints `/api/ha/camera_webrtc/{entity_id}` and `/api/ha/camera_hls/{entity_id}` for standalone browser access.
  - Vendored full `hls.min.js` (v1.5.17) for fast HLS streaming with audio on desktop and mobile browsers.
  - Added spinning animation to `camFsStatusBadge` during stream negotiation.

### Changed
- Live Matrix grid overview remains on efficient 5-second snapshot polling, preserving bandwidth while reserving full-rate 4K and audio streaming for fullscreen view.

## [1.2.5] - 2026-11-06

### Added
- **Dynamic Stream Buffering & Low Latency Indicators**:
  - Added `#camFsStatusBadge` in camera fullscreen view displaying `BUFFERING STREAM...` while connecting, `LIVE` / `LIVE 4K` when playing, and `STREAM OFFLINE` with diagnostics on failure.
  - Implemented dual-layer rendering in fullscreen modal: pre-renders an instant snapshot underneath while FFmpeg connects to eliminate black screens during startup.

### Optimized
- **4K Ultra HD & RTSP Live Transcoding**:
  - Added FFmpeg ultra-low latency flags (`-fflags nobuffer -flags low_delay`) and 5s socket timeout (`-stimeout 5000000`) to RTSP-to-MJPEG pipeline.
  - Added dynamic scaling for high-bandwidth streams: automatically transcodes 4K streams to 1080p (`scale=-2:1080`, 15fps, ~3.5 Mbps) and standard streams to 720p (`scale=-2:720`, 12fps, ~1.5 Mbps) to prevent browser buffer choking, frame drops, and black screen stalls.

## [1.2.4] - 2026-11-06

### Fixed
- **Camera Fullscreen MJPEG Streaming**:
  - Replaced blocking HA `camera_proxy_stream` call with ultra-reliable high-frequency snapshot MJPEG streamer directly from `/api/camera_proxy/`. Home Assistant Core does not send headers on `camera_proxy_stream` without dynamic websocket/query entity tokens, which previously caused the stream to hang indefinitely at `receive_response_headers`.
  - Corrected MIME `boundary` header parameter from `boundary=--frame` to standard `boundary=frame`.
  - Added standard `Content-Length` headers per JPEG frame for immediate image decoding in all modern browsers.

## [1.2.3] - 2026-11-06

### Fixed
- **ASGI & Streaming Stability**:
  - Replaced `BaseHTTPMiddleware` with pure ASGI middleware (`NormaliseSlashesASGIMiddleware`) to avoid `CancelledError` task drops and buffering deadlocks during HTTP streaming.
  - Added graceful cancellation handling (`asyncio.CancelledError` and `request.is_disconnected()`) in `/api/ha/camera_stream/` so client disconnects do not trigger 500 crashes.
  - Fixed `/api/recordings/days` endpoint using SQLite-native `func.strftime('%Y-%m-%d', ...)` instead of `cast(..., Date) GROUP BY "day"`, resolving 500 error on days strip.
  - Added client-side fallback interval in fullscreen camera view: if HA streaming proxy is unavailable, snapshots are automatically polled every 1s for a live feed.

## [1.2.2] - 2026-11-06

### Fixed
- **Live Stream in Fullscreen View**:
  - Fixed missing `subprocess` and `StreamingResponse` imports in backend, resolving crashes on stream endpoints.
  - Added `-c:v mjpeg` encoder to RTSP transcoding in `ffmpeg`, correctly generating live multipart/x-mixed-replace JPEG streams.
  - Modernized Home Assistant camera entity proxy streaming using asynchronous `httpx` with automatic fallback to high-frequency live snapshot stream if `camera_proxy_stream` is not natively supported by the camera entity.
- **Background Video Audio on Tab Switch**:
  - Automatically pause timeline video playback when switching to other navigation tabs (e.g. Live Matrix), preventing unwanted background sound.

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

