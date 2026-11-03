# ER-Adlernest

> **"Your Eagle Eye for Home Assistant Surveillance"**

A modern self-hosted CCTV surveillance and video management solution for Home Assistant, inspired by MotionEye, designed specifically for multi-camera environments, Reolink cameras, and automated NAS/FTP video archive indexing.

---

## 🦅 Features

- **Storage-Independent Video Archive**:
  - Automatically indexes existing video archives uploaded by cameras via FTP or SMB.
  - Native **Samba/CIFS** mount support right from the add-on configuration.
  - Local disks and volume mount support (`/share`, `/media`).
- **Live Multi-Camera Grid**:
  - Responsive layout supporting 1, 2, 4, 6, 9, and 16 camera feeds.
  - Reolink PoE / WiFi camera and Doorbell stream optimization.
  - Generic RTSP, ONVIF, and MJPEG support.
- **Modern Media Library**:
  - Fast search by Camera, Date, Time, and Filename.
  - Automatic event tag classification (`Motion`, `Person`, `Vehicle`, `Doorbell`).
  - Automated thumbnail generation using FFmpeg.
- **Home Assistant Ingress Integration**:
  - Runs directly within the Home Assistant sidebar.
  - Role-based Home Assistant authentication.
- **Future Frigate Interoperability**:
  - Architectural hooks prepared for Frigate event and snapshot database import.

---

## ⚙️ Configuration

Example add-on configuration in Home Assistant:

```yaml
storage_type: "cifs" # or "local"
local_path: "/share/er_adlernest/recordings"
samba_enabled: true
samba_server: "192.168.1.50"
samba_share: "cctv_archive"
samba_username: "cctv_user"
samba_password: "SecretPassword123"
scan_interval_minutes: 5
cameras:
  - name: "Driveway"
    source_type: "reolink"
    url: "rtsp://admin:password@192.168.1.100:554/h264Preview_01_main"
    substream_url: "rtsp://admin:password@192.168.1.100:554/h264Preview_01_sub"
    fps: 15
```

---

## 🏗️ Architecture

- **Backend**: Python 3.12 + FastAPI + SQLite / SQLAlchemy.
- **Video & Indexing Engine**: Native FFmpeg and FFprobe background indexing service with thumbnail extraction and EXIF/metadata parsing.
- **Storage Subsystem**: Kernel-level CIFS/Samba mount handler (`cifs-utils`).
- **Frontend**: Responsive Single Page App styled with Modern Slate/Navy (#0F172A) & Cyan (#06B6D4) Cyber-Eagle theme.

---

## 📄 License
Copyright (c) Eidolf. Licensed under MIT.
