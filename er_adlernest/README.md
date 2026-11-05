# ER-Adlernest

> **"Your Eagle Eye for Home Assistant Surveillance"**

A modern self-hosted CCTV surveillance and video archive manager for Home Assistant.
Designed for multi-camera environments, Reolink / ONVIF cameras, and automated NAS/FTP video archive indexing.

---

## Features

- **Flexible archive storage**
  - Browse any HA-provided local path (`/media`, `/share` and their subdirectories)
  - Connect additional SMB/CIFS network shares directly in the UI — credentials are stored securely on disk, never in config.yaml
  - Automatic background indexing with size/mtime change detection and thumbnail generation
- **Home Assistant camera integration**
  - Import `camera.*` entities from HA via the Supervisor Core API
  - Display live snapshots in the camera grid (MJPEG streams play directly; RTSP stored for archive mapping)
- **Archive browser**
  - Filter by camera, event type (motion, person, vehicle, doorbell)
  - Video playback with progressive streaming
- **Ingress integration** — runs entirely in the HA sidebar; no separate port or login required

---

## Configuration

Only the log level needs to be set here. Everything else (storage paths, SMB credentials, cameras) is
managed in the Web UI under **Storage & System**.

```yaml
log_level: "info"   # debug | info | warning | error
```

---

## Architecture

- **Backend:** Python 3.12 + FastAPI + SQLite/SQLAlchemy
- **Indexer:** FFmpeg/FFprobe for thumbnail and metadata extraction
- **Storage:** HA-mounted folders + optional app-managed CIFS mounts (`cifs-utils`)
- **Frontend:** Single-page app, dark cyber-eagle theme, Bootstrap Icons

---

## License

Copyright (c) Eidolf. Licensed under MIT.
