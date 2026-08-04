# Migrating back to the official Vaultwarden add-on

This fork exists only because the official add-on's build is broken. Once
upstream ships a release with Vaultwarden 1.37.0 or newer, **move back to it**
— it is maintained, signed, and built by the Home Assistant Community Add-ons
project, and this fork is a single-person stopgap.

## 1. Check whether upstream is actually ready

Do not go by the PRs being merged. Go by a released version.

Two things must both be true:

- **[PR #430][pr430]** (or equivalent) is merged, fixing the `libpq5` and
  `nginx` pins so the build succeeds.
- **[PR #424][pr424]** (or a later Renovate bump) is merged, and a **release**
  has shipped that version to the store.

Check the released version directly:

```sh
curl -s https://raw.githubusercontent.com/hassio-addons/repository/master/bitwarden/config.yaml \
  | grep -E '^(version|image):'
```

If `version:` is still `0.27.0`, upstream has not shipped yet — wait. In Home
Assistant, the official add-on's store page showing 0.28.0 or later is the same
signal.

Confirm the Vaultwarden version inside that release matches or exceeds what you
are running now, otherwise migrating back is a downgrade. Vaultwarden does not
support downgrading its database schema.

## 2. Back up

Settings → System → Backups → **Create backup**. Do not skip this. The data
move below is destructive to the destination.

## 3. Reinstall the official add-on, if you removed it

Settings → Add-ons → Add-on Store → **Home Assistant Community Add-ons** →
**Vaultwarden** → **Install**.

Do not start it yet.

If you never uninstalled it, it is still there with stale data from before you
switched. That stale copy is about to be overwritten, which is intended — your
current data lives in the fork's add-on now.

## 4. Stop both add-ons

Both must be stopped before copying. Vaultwarden uses SQLite in WAL mode and a
live copy can be torn and unusable.

- Stop the fork's **Vaultwarden** (under "JayTalge Vaultwarden Add-on")
- Stop the official **Vaultwarden**, if running

## 5. Start the official one once, then stop it

This makes the Supervisor create its data directory with correct ownership if
it is a fresh install. Let it come up, then stop it again.

Ignore the temporary admin token it prints — step 6 overwrites it.

## 6. Copy the data back

Open the **Terminal & SSH** / **Advanced SSH & Web Terminal** add-on's web UI,
with **Protection mode disabled**. Run on the Home Assistant host.

### 6a. Find the slugs and data root

```sh
for c in $(docker ps --filter name=addon_ --format '{{.Names}}'); do
  s=$(docker inspect "$c" --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Source}}{{end}}{{end}}')
  [ -n "$s" ] && { DATAROOT=$(dirname "$s"); break; }
done
echo "data root: $DATAROOT"
ls -la "$DATAROOT" | grep -i bitwarden
```

Two `_bitwarden` directories. The official add-on's is `a0d7b954_bitwarden`
(that hash is stable — it is derived from the `hassio-addons/repository` URL).
The other is the fork's, and it is the one holding your **current** data.

Confirm before copying — check which has the recently-modified, larger
`db.sqlite3`:

```sh
docker run --rm -v "$DATAROOT":/d alpine sh -c 'ls -la /d/*_bitwarden/db.sqlite3'
```

> Note the direction has reversed. Here **SRC is the fork's directory** and
> **DST is `a0d7b954_bitwarden`**. Getting this backwards overwrites your live
> vault with stale data. Read the two paths twice before running.

### 6b. Copy

Substitute your fork slug into `SRC`:

```sh
docker run --rm -v "$DATAROOT":/d alpine sh -c '
set -e
SRC=/d/ef847b1a_bitwarden
DST=/d/a0d7b954_bitwarden
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

**The two md5 hashes must match.** If not, stop and restore your backup.

## 7. Start the official add-on and verify

Start it, then read its log. You want:

```
Version 1.37.0        (or newer)
[INFO] Using saved config from `/data/config.json` for configuration.
```

And you should **not** see `Private key '/data/rsa_key.pem' created correctly`
or a temporary admin token banner — either means it started on an empty
database, not your data.

Open `https://<your-home-assistant>:7277` and confirm your entries, folders,
and attachments. Same host and port as before, so clients need no changes.

## 8. Set boot flags

- Official add-on: **Start on boot** on, **Watchdog** on
- Fork's add-on: **Start on boot** off

Both bind port 7277, so leaving both on boot means a race after every restart.

## 9. Clean up, once you are confident

Give it a few days first — until then the fork's add-on is your rollback, with
an intact copy of your data.

When ready:

1. Uninstall the fork's **Vaultwarden** add-on.
2. Settings → Add-ons → Add-on Store → **⋮** → **Repositories** → remove
   `https://github.com/JayTalge/app-vaultwarden`.

Removing the repository does not delete data belonging to an add-on that is
still installed — uninstall first, in that order.

## Rollback

If the official add-on misbehaves, at any point before step 9:

1. Stop the official add-on.
2. Set the fork's add-on **Start on boot** back on and start it.

Its data directory is untouched by this procedure, so it comes back exactly as
it was.

[pr424]: https://github.com/hassio-addons/app-vaultwarden/pull/424
[pr430]: https://github.com/hassio-addons/app-vaultwarden/pull/430
