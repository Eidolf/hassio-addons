# ER-Adlernest Documentation

## Getting Started

1. Add this repository to your Home Assistant Add-on Store:
   `https://github.com/Eidolf/hassio-addons`
2. Search for **ER-Adlernest** and click **Install**.
3. Start the add-on and open the Web UI via the HA sidebar (Ingress).
4. In the **Storage & System** tab, select your archive root folder and configure any SMB/CIFS connections.

## Configuration (config.yaml)

Only the log level needs to be set here. All storage paths, SMB credentials, and camera settings are
managed exclusively in the Web UI.

```yaml
log_level: "info"   # debug | info | warning | error
```

## Storage

### Local / HA-mounted paths

Folders under `/media` and `/share` are provided directly by Home Assistant. If HA has already
mounted a NAS share (e.g. `/media/Kamera_Dateien`), you can browse and select it straight away in
the **Storage & System** tab — no extra configuration needed.

### Additional SMB / CIFS sources

If a network share is **not** already mounted by HA, you can add it in the **Storage & System** tab
under *Network Sources (SMB / CIFS)*. The add-on stores credentials securely in `/data/credentials/`
(not in config.yaml) and mounts the share under `/data/mounts/<id>`. After a successful connection
you can browse the mount path in the folder browser and set it as the active archive root.

> **Note:** App-initiated CIFS mounts require the `SYS_ADMIN` capability and kernel mount support.
> If your HA host or protection mode prevents kernel mounts, the source will remain visible in the UI
> with an *Offline* status — no data is lost, and HA-provided local paths always work independently.

## Archive Indexer

The indexer scans the configured root folder every 5 minutes and on-demand after a manual scan or
path change. It tracks file size and modification time to detect changes and skips files that were
modified less than 5 seconds ago (still-writing guard). Thumbnails and metadata are re-generated for
changed files. A scan against an offline NAS will not delete existing index entries.

## Camera Viewer

- **HA camera entities** (`ha_camera` source): displays a snapshot fetched via the Supervisor proxy
  (`http://supervisor/core/api/camera_proxy/<entity>`). The image refreshes on each page load.
  This is a snapshot, not a continuous video stream.
- **MJPEG streams**: displayed as a live `<img>` source directly in the browser.
- **RTSP / Reolink / ONVIF**: stream URL is stored for archive folder mapping; direct browser playback
  of RTSP is not available without transcoding.

## REST API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/status` | Health, statistics, storage sources |
| `GET/POST` | `/api/settings` | Get/set active archive path |
| `GET` | `/api/storage/sources` | List local + SMB sources |
| `POST` | `/api/storage/sources` | Add/update SMB source |
| `POST` | `/api/storage/sources/test` | Test + connect SMB source |
| `POST` | `/api/storage/sources/{id}/mount` | Mount SMB source |
| `POST` | `/api/storage/sources/{id}/unmount` | Unmount SMB source |
| `DELETE` | `/api/storage/sources/{id}` | Delete SMB source |
| `GET` | `/api/fs/browse?path=…` | Browse allowed folder tree |
| `GET` | `/api/ha/cameras` | List HA camera entities |
| `GET` | `/api/ha/camera_proxy/{entity}` | Proxy HA snapshot |
| `GET/POST` | `/api/cameras` | List/add camera configs |
| `DELETE` | `/api/cameras/{id}` | Remove camera config |
| `GET` | `/api/recordings` | Filtered archive with pagination |
| `GET` | `/api/recordings/{id}/stream` | Stream video file |
| `GET` | `/api/recordings/{id}/thumbnail` | Thumbnail image |
| `POST` | `/api/archive/scan` | Trigger background scan |
