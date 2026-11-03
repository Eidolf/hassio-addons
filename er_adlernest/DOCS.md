# ER-Adlernest Documentation

## Getting Started

1. Add this repository to your Home Assistant Add-on Store:
   `https://github.com/Eidolf/hassio-addons`
2. Search for **ER-Adlernest** and click **Install**.
3. In the **Configuration** tab, specify your video storage path or Samba/CIFS credentials.
4. Start the add-on and open the Web UI via the sidebar.

## Storage Configurations

### Local Storage
If your cameras save recordings to Home Assistant's `/share` folder via an FTP add-on:
```yaml
storage_type: "local"
local_path: "/share/ftp/recordings"
samba_enabled: false
```

### Samba / NAS Storage
If recordings are stored on Synology, QNAP, TrueNAS, or Unraid:
```yaml
storage_type: "cifs"
samba_enabled: true
samba_server: "192.168.1.10"
samba_share: "surveillance"
samba_username: "ha_viewer"
samba_password: "my_secure_password"
```

## REST API Overview

- `GET /api/status`: System, storage, and indexer statistics.
- `GET /api/cameras`: Configured camera feeds and streams.
- `POST /api/cameras`: Register or update camera stream.
- `GET /api/recordings`: Filtered recordings archive with pagination.
- `GET /api/recordings/{id}/stream`: Progressive video streaming.
- `GET /api/recordings/{id}/thumbnail`: Video preview thumbnail.
- `POST /api/archive/scan`: Trigger manual background indexing.

