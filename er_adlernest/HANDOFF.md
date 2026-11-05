# ER-Adlernest – Abschlussbericht & Übergabe an Folge-KI

**Stand:** v1.1.4, lokal committed, **nicht gepusht** (Stand: 2026-11-05)
**Ausgangsbasis für Weiterarbeit:** exakt dieser Code-Stand. Nichts hypothetisch
hinzufügen – die Codebasis ist vollständig und funktionsfähig.

---

## Was implementiert und gefixt wurde

### v1.1.1 – HA-Kamera-Speicherfehler behoben

**Problem:** HA-Kameras ließen sich auswählen, beim Speichern kam
`NOT NULL constraint failed: cameras.stream_url`, weil die alte SQLite-Spalte
NOT NULL war, die API aber `NULL` schreibt (HA-Kameras haben keine RTSP-URL).

**Lösung:**
- `db_migrations.py` (neu): transaktionaler SQLite-Tabellen-Rebuild, der
  `cameras.stream_url` auf nullable setzt, dabei Daten, Indizes, Trigger und
  Fremdschlüsselreferenzen erhält. Bei Fehler wird vollständig zurückgerollt.
- `models.py`: Migration-Aufruf ausgelagert; `run_migrations()` nutzt nun
  `migrate_database()`.
- 5 Unit-Tests in `tests/test_db_migrations.py`: Datenübernahme, Idempotenz,
  Rollback bei Fremdschlüsselfehler, Rollback bei nicht unterstütztem Schema,
  No-op bei bereits nullable Spalte.

### v1.1.2 – Archiv-Pagination

**Problem:** ~4.000 indexierte Videos, aber nur 50 angezeigt, keine Möglichkeit
für weitere Seiten.

**Lösung:**
- Frontend (`index.html`): Vor/Zurück-Navigation, Seitenanzeige, 50 Einträge/Seite.
- Filterwechsel springen auf Seite 1 zurück.
- Race-Condition-Schutz: veraltete Antworten können keine neueren Filter-
  ergebnisse überschreiben (`archiveRequestId`-Mechanismus).
- Backend: stabile Sortierung `ORDER BY recorded_at DESC, id DESC`.
- 4 Node.js-Tests in `tests/test_archive_pagination.cjs`.

### v1.1.3 – Bildarchiv, Tagesansicht, Medientyp-Filter

**Problem:** Nur Videos wurden indexiert; keine Bild-/Videofilterung; keine
Tages-/Zeitleistenansicht.

**Lösung:**
- **Bildindexierung** (`indexer.py`): `extract_image()` mit Pillow, EXIF-
  Orientation-Korrektur, SHA256-basierter Thumbnail-Hash. `IMAGE_EXTENSIONS`
  ergänzt (`jpg, jpeg, png, webp, bmp`).
- **`media_type`-Spalte** an `recordings` (additive Migration, `NOT NULL DEFAULT
  'video'`). Indexer setzt `media_type` beim Neuanlegen und Aktualisieren.
- **Medientyp-Filter** im Archiv (Alle / Videos / Bilder).
- **Datumsfilter** (`<input type="date">`) + löschbar per Button.
- **Tages-Zeitleiste**: scrollbarer Strip mit Tagen und Aufnahmeanzahl, klickbar
  zum Filtern. Backend-Endpunkt `/api/recordings/days` liefert `{date, count}`.
- **Bild-Lightbox**: Bilder öffnen in einem eigenen Modal, nicht im Video-Player.
- **Stream-Endpunkt**: liefert korrekten `Content-Type` für Bilder und Videos
  via `mimetypes.guess_type()`.
- **Kamera-Spalten vorbereitet**: `highres_stream_url`,
  `highres_ha_entity_id`, `fullscreen_highres` (Datenbank + Migration).
- **Verbesserte Ordnerzuordnung** im Indexer: längste-Präfix-Matching über
  komplette Pfadkomponenten; unveränderte Dateien werden bei
  Mapping-Änderungen neu zugeordnet.

### v1.1.4 – Live-Matrix: Vollbild, HighRes, Archiv-Link, Kamera-Bearbeiten

**Problem:** Live-Kachel nicht klickbar, kein Vollbild, keine HighRes-Quelle,
kein direkter Archiv-Sprung, Kameras nur löschbar nicht bearbeitbar.

**Lösung:**
- **Stats-Leiste ausgeblendet** auf Live-Tab für schlichten Einstieg.
- **Vollbild-Modal**: klickbare Kachel + Button öffnen Fullscreen; Bild füllt
  Karte mit `object-fit:contain`.
- **HighRes-Unterstützung**: optionale zweite Stream-URL oder HA-Entity pro
  Kamera; Umschalt-Button im Vollbild wechselt zwischen Haupt- und HighRes-
  Quelle. `fullscreen_highres`-Flag steuert Startverhalten.
- **Archiv-Link** pro Kamera-Karte: springt ins Archiv mit gesetztem Kamera-
  Filter.
- **Kamera-Bearbeiten**: Edit-Button öffnet vorausgefülltes Modal; `openEditCameraModal()` lädt alle Felder inkl. HighRes.
- **HighRes-Felder im Kamera-Modal**: ein zusammenhängender Bereich, der je
  nach Quelltyp (RTSP → URL-Eingabe, HA → Dropdown) umschaltet. Die HA-Dropdown-
  Liste für HighRes wird in demselben `loadHACameras()`-Aufruf wie die Haupt-
  liste befüllt. **(Fix 8fb2b27 – siehe unten.)**

### Fix 8fb2b27 – HighRes HA-Dropdown befüllt

**Problem:** Beim Bearbeiten/Anlegen erhielt das HighRes-Feld bei HA-Kameras
keine Auswahlliste.

**Ursache:** Zwei getrennte Feld-Gruppen (`groupHighResStream` für RTSP,
`groupHighResHa` für HA) wurden unabhängig voneinander umgeschaltet;
`loadHACameras()` befüllte nur das Haupt-Dropdown.

**Lösung:** Zusammenführung zu einem Container `groupHighResStream` mit zwei
Sub-Gruppen (`highresUrlGroup` / `highresHaGroup`), die je nach Quelltyp
umgeschaltet werden. `loadHACameras()` klont die Optionen in beide Dropdowns;
bestehende HighRes-Auswahl bleibt beim Refresh erhalten.

---

## Architektur-Übersicht (aktueller Stand)

```
er_adlernest/
├── config.yaml          # Add-on-Metadaten, Version 1.1.4
├── rootfs/
│   ├── run.sh            # Start-Skript (uvicorn, log-level)
│   └── app/
│       ├── backend/
│       │   ├── main.py          # FastAPI-App, alle Endpunkte
│       │   ├── models.py        # SQLAlchemy-Modelle, run_migrations()
│       │   ├── db_migrations.py # SQLite-Tabellen-Rebuild-Migration
│       │   ├── indexer.py       # Verzeichnis-Scanner, Bild+Video-Indexierung
│       │   ├── storage.py        # SMB/CIFS-Mount-Verwaltung
│       │   └── requirements.txt
│       └── frontend/
│           └── dist/index.html   # Single-File-Frontend (HTML+CSS+JS)
└── tests/
    ├── test_db_migrations.py      # 5 Python-Tests (unittest)
    └── test_archive_pagination.cjs # 4 Node.js-Tests (node:test)
```

### Datenbank-Schema (relevante Spalten)

**cameras:** `id, name, source_type, stream_url (nullable), substream_url,
ha_entity_id, folder_mapping, highres_stream_url, highres_ha_entity_id,
fullscreen_highres, fps, enabled, created_at`

**recordings:** `id, camera_name, file_path, relative_path, filename,
file_size, duration, width, height, codec, media_type, recorded_at,
event_type, thumbnail_path, created_at`

### API-Endpunkte (Auswahl)

| Methode | Pfad | Funktion |
|---------|------|----------|
| GET | `/api/status` | Statistik, Speicherpfad, Quellen |
| GET | `/api/recordings` | Paginierte Aufnahmen; Filter: `camera, event_type, media_type, date_from, date_to, limit, offset` |
| GET | `/api/recordings/days` | Tage mit Aufnahmen für Zeitleiste; Filter: `camera, media_type` |
| GET | `/api/recordings/{id}/stream` | Datei-Stream mit korrektem Content-Type |
| GET | `/api/recordings/{id}/thumbnail` | Thumbnail-JPEG |
| GET/POST | `/api/cameras` | Liste / Anlegen+Aktualisieren (inkl. HighRes-Felder) |
| DELETE | `/api/cameras/{id}` | Löschen |
| GET | `/api/ha/cameras` | HA-Kamera-Entitäten |
| GET | `/api/ha/camera_proxy/{entity_id}` | Snapshot-Proxy |
| Storage-Endpunkte | `/api/storage/sources*` | SMB/CIFS-Quellen-Verwaltung |
| GET | `/api/fs/browse` | Verzeichnis-Browser |

---

## Bekannte Limitierungen / Offene Punkte

Diese Punkte sind **nicht** als Bugs zu verstehen, sondern als mögliche
folgende Erweiterungen. Die Codebasis läuft auch ohne sie.

1. **Kein Push zu GitHub erfolgt** – alle Commits sind lokal auf `main`.
   Vor einem HA-Update muss gepusht werden.
2. **RTSP im Browser**: RTSP-Streams sind im Browser nicht direkt abspielbar
   (nur MJPEG und HA-Snapshots). Vollbild zeigt für RTSP einen Hinweis.
   Eine mögliche Erweiterung wäre HLS-Transkodierung via ffmpeg/ingest.
3. **HA-Kamera-Snapshots sind statisch**: Das Live-Grid zeigt für HA-Kameras
   Momentaufnahmen, keinen kontinuierlichen Stream. Eine `camera_proxy/cid`
   Stream-Endpunkt-Erweiterung wäre denkbar.
4. **Keine Build-Pipeline**: Das Frontend ist eine einzelne `index.html` ohne
   Bundler. Bei größerem UI-Umfang könnte ein Build-Step sinnvoll werden.
5. **`__pycache__` wurde in früheren Commits mitcommittet** (vor 1.1.1). Eine
   `.gitignore`-Bereinigung wäre möglich, ist nicht funktionsrelevant.
6. **Keine Authentifizierung**: Das Add-on läuft hinter HA Ingress; keine
   eigene Auth-Schicht. Dies ist HA-Add-on-Konvention.

---

## Test-Ausführung

```bash
# Python-Migrationstests (5 Tests)
python3 -B -m unittest discover -s er_adlernest/tests -v

# Node.js-Paginationstests (4 Tests)
node --test er_adlernest/tests/test_archive_pagination.cjs
```

**Lokale Voraussetzungen:** `python3` (stdlib only), `node`. SQLAlchemy wird
für die Tests nicht benötigt (Migrationstests nutzen direktes `sqlite3`).

**Status beim letzten Durchlauf:** 9/9 Tests bestanden.

---

## Hinweise für die Folge-KI

- Die `index.html` ist ~1.100 Zeilen, alles inline (HTML+CSS+JS). Sucht
  nach Funktionsnamen, nicht nach separaten Dateien.
- Der Indexer läuft alle 300 Sekunden im Hintergrund (`periodic_scanner`).
  Ein Rescan reicht aus, um geänderte Ordnerzuordnungen zu übernehmen – ein
  manueller Fix dafür ist nicht mehr nötig (vom Nutzer bestätigt).
- Migrationen laufen beim Import von `models.py` automatisch (`run_migrations()`
  am Modul-Ende). Änderungen am Schema immer in `db_migrations.py` eintragen,
  nicht nur im ORM-Modell.
- Die `stream_url`-Nullable-Migration ist ein Tabellen-Rebuild, kein einfaches
  `ALTER TABLE`. SQLite unterstützt keine `ALTER COLUMN`. Das ist bewusst so
  gelöst und getestet.
