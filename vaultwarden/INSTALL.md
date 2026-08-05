# Installing this Vaultwarden add-on in Home Assistant

This is a fork of [`hassio-addons/app-vaultwarden`][upstream] that ships
**Vaultwarden 1.37.0** while the official add-on is stuck on 1.36.0.

## Should you use this?

Read this before installing — it is a password manager.

The official add-on is stuck because its build is broken, not because it was
abandoned. Two pinned Debian packages (`libpq5`, `nginx`) were dropped from the
Debian 13 mirror, so every build fails at `apt-get install`. Upstream
[PR #424][pr424] already carries the 1.37.0 bump but cannot go green until the
pins are fixed; [PR #430][pr430] fixes them.

**This fork is a stopgap.** Installing it means trusting a personally built
image (`ghcr.io/jaytalge/bitwarden`) with your vault, instead of one built by
the Home Assistant Community Add-ons project. The Dockerfile differs from
upstream by exactly three lines — the Vaultwarden version and the two package
pins — and you can verify that yourself:

```sh
git clone https://github.com/JayTalge/app-vaultwarden
cd app-vaultwarden
git remote add upstream https://github.com/hassio-addons/app-vaultwarden
git fetch upstream
git diff upstream/main -- vaultwarden/Dockerfile
```

If you would rather wait for the official fix, that is a reasonable choice.
Once upstream merges, follow [MIGRATE-BACK.md](MIGRATE-BACK.md) to move to it.

## Before you start

- **Take a Home Assistant backup.** Settings → System → Backups → *Create
  backup*. Do not skip this.
- The add-on binds **port 7277/tcp**. If the official Vaultwarden add-on is
  installed and running, both want that port, and only one can have it.
- This installs as a **separate add-on with its own data directory**. It is not
  an in-place upgrade — your existing vault does not follow it automatically.
  Migrating data is step 5 and is optional only if you are starting fresh.

## 1. Add the repository

1. Settings → Add-ons → **Add-on Store**
2. Top-right **⋮** menu → **Repositories**
3. Paste:

   ```
   https://github.com/JayTalge/app-vaultwarden
   ```

4. **Add**, then **Close**

A new section called **JayTalge Vaultwarden Add-on** appears in the store.

## 2. Install

Find **Vaultwarden** under that new section — *not* the one under "Home
Assistant Community Add-ons". Both are named "Vaultwarden"; the repository
heading above the card is what tells them apart.

Click it, then **Install**. It pulls a prebuilt image rather than compiling on
your device, so it takes about a minute rather than an hour on a Pi. `amd64`
and `aarch64` are both published.

Do **not** start it yet if you are migrating existing data.

## 3. Stop the old add-on

Skip if you have never used the official Vaultwarden add-on.

Settings → Add-ons → **Vaultwarden** (the Community Add-ons one) → **Stop**.

Set its **Start on boot** to off while you are there, so it cannot claim port
7277 after a restart.

Stopping is mandatory before copying data: Vaultwarden uses SQLite in WAL mode,
and copying a live database risks a torn, unusable copy.

## 4. First start, to create the data directory

Start the new add-on once and let it come up, then **stop** it again.

This makes the Supervisor create its data directory with the right ownership.
It also generates a throwaway database and a temporary admin token, both of
which step 5 overwrites.

## 5. Migrate your existing vault

Skip if you are starting fresh.

Open the **Terminal & SSH** or **Advanced SSH & Web Terminal** add-on's web UI.
It must have **Protection mode disabled** so it can reach the Docker socket.
Run these on the Home Assistant host — not on your desktop.

### 5a. Find your slugs and data directory

Add-on slugs contain a per-repository hash, so yours may differ from the
examples here. The data root also differs between Home Assistant versions —
newer ones use `.../supervisor/apps/data`, older ones `.../supervisor/addons/data`.
Discover both rather than assuming:

```sh
for c in $(docker ps --filter name=app_ --format '{{.Names}}'); do
  s=$(docker inspect "$c" --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Source}}{{end}}{{end}}')
  [ -n "$s" ] && { DATAROOT=$(dirname "$s"); break; }
done
echo "data root: $DATAROOT"
ls -la "$DATAROOT" | grep -i bitwarden
```

You should see two directories ending in `_bitwarden`. The one containing a
large `db.sqlite3` is your existing vault (**SRC**); the other is the new
add-on (**DST**).

> Add-on containers are deleted when the add-on is stopped, so
> `docker inspect addon_..._bitwarden` will fail right now. That is expected —
> the data directory persists independently of the container.

### 5b. Copy the data
> If $DATAROOT is no correctly set, it also work if you change the variable down 
> in the script with the complete path like "/mnt/data/apps"

Substitute your own slugs into `SRC` and `DST`:

```sh
docker run --rm -v "$DATAROOT":/d alpine sh -c '
set -e
SRC=/d/a0d7b954_bitwarden
DST=/d/ef847b1a_bitwarden
[ -f "$SRC/db.sqlite3" ] || { echo "ABORT: no db.sqlite3 in $SRC"; exit 1; }
[ -d "$DST" ]           || { echo "ABORT: $DST missing"; exit 1; }
cp -a "$DST/options.json" /tmp/options.json
rm -rf "$DST"/* "$DST"/.[!.]* 2>/dev/null || true
cp -a "$SRC"/. "$DST"/
cp -a /tmp/options.json "$DST/options.json"
echo "=== RESULT ==="; ls -la "$DST"
echo "=== INTEGRITY ==="
md5sum "$SRC/db.sqlite3" "$DST/db.sqlite3"
'
```

It aborts before deleting anything if either path is wrong, so a bad slug fails
harmlessly instead of wiping the destination.

Three things it does deliberately:

- **Copies `db.sqlite3-wal` and `-shm` with the database.** The write-ahead log
  holds your most recent changes; moving the `.sqlite3` alone can lose them.
- **Preserves the destination's `options.json`.** That file belongs to the
  Supervisor, not Vaultwarden.
- **Uses `cp -a`**, keeping ownership and timestamps — `rsa_key.pem` and the
  attachment files need their permissions intact.

**The two md5 hashes must match.** If they do not, stop and restore your backup.

## 6. Start and verify

Start the new add-on, then check its log (add-on page → **Log**). You want:

```
Version 1.37.0
[INFO] Using saved config from `/data/config.json` for configuration.
```

Two absences confirm the migration took:

- **No** `Private key '/data/rsa_key.pem' created correctly` — it is using your
  original key rather than making a new one.
- **No** "temporary random admin token" banner — your migrated config replaced it.

If you see either of those, it started on an empty database. Stop it and
recheck step 5.

Now open the web UI at `https://<your-home-assistant>:7277` and log in.
Confirm your entries, folders, and attachments are present. Clients need no
changes: same host, same port.

## 7. Afterwards

- Leave the old add-on installed but stopped for a few days as a rollback. It
  still holds an untouched copy of your data. To roll back: stop the new one,
  re-enable "Start on boot" on the old one, start it.
- Once satisfied, uninstall the old add-on to reclaim the duplicate database
  and clear the confusing second "Vaultwarden" from your store.
- If you started the new add-on before migrating, its log contains a plaintext
  temporary `ADMIN_TOKEN`. It grants nothing after migration, but restart the
  add-on to rotate the log.

## When upstream is fixed

Move back to the official add-on. See [MIGRATE-BACK.md](MIGRATE-BACK.md).

[upstream]: https://github.com/hassio-addons/app-vaultwarden
[pr424]: https://github.com/hassio-addons/app-vaultwarden/pull/424
[pr430]: https://github.com/hassio-addons/app-vaultwarden/pull/430
