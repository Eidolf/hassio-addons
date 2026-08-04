# Vaultwarden add-on for Home Assistant — 1.37.1 fork

![Supports aarch64 Architecture][aarch64-shield]
![Supports amd64 Architecture][amd64-shield]
[![License][license-shield]](LICENSE.md)

An unofficial fork of [`hassio-addons/app-vaultwarden`][upstream] that ships
**Vaultwarden 1.37.1**, while the official add-on is stuck on 1.36.0.

> [!WARNING]
> This is a stopgap maintained by one person, not by the Home Assistant
> Community Add-ons project. It builds your password manager from a personal
> GHCR image. Read [Should you use this?](#should-you-use-this) before
> installing, and move back to the official add-on once it is fixed.

## Why this fork exists

The official add-on is not abandoned — its **build is broken**. Two pinned
Debian packages were dropped from the Debian 13 mirror, so every build fails:

```
E: Version '17.9-0+deb13u1' for 'libpq5' was not found
E: Version '1.26.3-3+deb13u2' for 'nginx' was not found
```

Upstream [PR #424][pr424] already carries the 1.37.0 bump but cannot go green
until those pins are fixed. [PR #430][pr430] — submitted from this fork — fixes
them. Once that lands and a release ships, **this fork is obsolete.**

## What differs from upstream

Three lines in `vaultwarden/Dockerfile`, plus the packaging needed to publish
from a fork:

| Change | Why |
|---|---|
| `vaultwarden/server` 1.36.0 → **1.37.1** | the point of the fork |
| `libpq5` → `17.10-0+deb13u1` | stale pin, gone from the mirror |
| `nginx` → `1.26.3-3+deb13u7` | stale pin, gone from the mirror |
| `image:` → `ghcr.io/jaytalge/bitwarden` | pull a prebuilt image, not a local build |
| `repository.json` added | required for HA to accept this as a custom repository |
| `.github/workflows/*` rewritten | the shared `hassio-addons/workflows` calls cannot run from a fork |

Verify the code difference yourself:

```sh
git clone https://github.com/JayTalge/app-vaultwarden
cd app-vaultwarden
git remote add upstream https://github.com/hassio-addons/app-vaultwarden
git fetch upstream
git diff upstream/main -- vaultwarden/Dockerfile
```

Images are built by [GitHub Actions](.github/workflows/deploy.yaml) on push to
`main` and published to `ghcr.io/jaytalge/bitwarden` for `amd64` and `aarch64`.

New Vaultwarden releases are picked up on their own, the same way upstream does
it — [Renovate][renovate] opens a pull request bumping the pinned
`vaultwarden/server` tag, and automerges it once the build passes:

1. **Renovate** raises the PR ([config](.github/renovate.json)). It also keeps
   the pinned Debian packages current — stale `libpq5` and `nginx` pins are
   what broke upstream in the first place.
2. **[CI](.github/workflows/ci.yaml)** builds the add-on for `amd64` and
   `aarch64` and throws it away. Renovate holds the PR until this is green, so
   a release that does not build never reaches `main`.
3. **[Stamp](.github/workflows/stamp.yaml)** raises the add-on version, writes
   the changelog entry and updates this README. Renovate only touches the
   Dockerfile, and without this step the add-on store would never offer an
   update.
4. **[Deploy](.github/workflows/deploy.yaml)** publishes to GHCR.

Major Vaultwarden releases are deliberately left for a human to merge.

## Should you use this?

It is a password manager, so decide deliberately.

Using this fork means trusting an image built by an individual rather than by
the Community Add-ons project. The source difference is three lines and you can
audit it in under a minute with the commands above — but the build pipeline,
the GHCR account, and the release process are all mine, not theirs.

Waiting for the official fix is a legitimate choice. If you need 1.37.0 now,
this gets you there, and [MIGRATE-BACK.md](MIGRATE-BACK.md) gets you home.

## Install

Full instructions, including migrating an existing vault:
**[INSTALL.md](INSTALL.md)**

The short version:

1. Settings → Add-ons → Add-on Store → **⋮** → **Repositories**
2. Add `https://github.com/JayTalge/app-vaultwarden`
3. Install **Vaultwarden** from the new *JayTalge Vaultwarden Add-on* section —
   not the identically named one under *Home Assistant Community Add-ons*
4. **Back up first.** Stop the official add-on if it is running — both bind
   port `7277/tcp`
5. This is a separate add-on with its own data directory. Existing vault data
   does **not** follow automatically; see [INSTALL.md](INSTALL.md) step 5

## Moving back to the official add-on

When upstream ships a release with 1.37.1 or newer, switch back:
**[MIGRATE-BACK.md](MIGRATE-BACK.md)**

Gate on a released version, not on merged PRs — merging changes nothing in your
add-on store until a release goes out.

## Support

**Do not raise issues about this fork with upstream.** Their Discord, forum
thread, and issue tracker do not cover this image, and reporting fork problems
there wastes maintainer time on something they did not ship.

- Problems with **this fork**: [open an issue here][issue]
- Problems with the **official add-on**: [upstream issues][upstream-issues]
- Problems with **Vaultwarden itself**: [dani-garcia/vaultwarden][vaultwarden]

## Credits

All the real work is [Franck Nijhof][frenck]'s and the
[Home Assistant Community Add-ons][upstream-org] contributors'. This fork adds
a version bump and two package pins. Upstream documentation for the add-on's
options and configuration still applies: [DOCS.md](vaultwarden/DOCS.md).

## License

MIT License

Copyright (c) 2019-2026 Franck Nijhof

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
[frenck]: https://github.com/frenck
[issue]: https://github.com/JayTalge/app-vaultwarden/issues
[license-shield]: https://img.shields.io/github/license/JayTalge/app-vaultwarden.svg
[pr424]: https://github.com/hassio-addons/app-vaultwarden/pull/424
[renovate]: https://github.com/apps/renovate
[pr430]: https://github.com/hassio-addons/app-vaultwarden/pull/430
[upstream-issues]: https://github.com/hassio-addons/app-vaultwarden/issues
[upstream-org]: https://github.com/hassio-addons
[upstream]: https://github.com/hassio-addons/app-vaultwarden
[vaultwarden]: https://github.com/dani-garcia/vaultwarden
