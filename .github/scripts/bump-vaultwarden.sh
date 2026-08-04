#!/usr/bin/env bash
# Bring the add-on version in line with the pinned Vaultwarden release.
#
# Usage: .github/scripts/bump-vaultwarden.sh [vaultwarden-version]
#
# With a version argument the Dockerfile pin is rewritten first; without one
# the pin is taken as-is. That second form is what runs after Renovate has
# already bumped the pin on main — Renovate rewrites the Dockerfile and
# nothing else, so the add-on version, changelog and README still have to
# catch up or Home Assistant never sees a new release.
#
# Rewrites, in place:
#   vaultwarden/Dockerfile    only when a version argument is given
#   vaultwarden/config.yaml   the add-on version Home Assistant sees
#   vaultwarden/CHANGELOG.md  a new entry on top
#   README.md                 the version this fork advertises
#
# The add-on version follows the shape of the Vaultwarden bump: a new minor
# bumps the add-on minor, a new patch bumps the add-on patch.
#
# In GitHub Actions the result is written to $GITHUB_OUTPUT as `changed`
# (true/false), `shipped`, `version` and `addon_version`.
set -euo pipefail

root="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
dockerfile="${root}/vaultwarden/Dockerfile"
config="${root}/vaultwarden/config.yaml"
changelog="${root}/vaultwarden/CHANGELOG.md"
readme="${root}/README.md"

emit() {
    [[ -n "${GITHUB_OUTPUT:-}" ]] || return 0
    printf '%s\n' "$@" >>"${GITHUB_OUTPUT}"
}

# What the image is built from, and what the last release actually shipped.
# The changelog is the record of the latter: config.yaml carries the add-on
# version but says nothing about which Vaultwarden it corresponds to.
pinned="$(sed -n \
    's|^FROM "vaultwarden/server:\(.*\)" AS vaultwarden$|\1|p' "${dockerfile}")"
shipped="$(sed -n \
    's|^- .* Update Vaultwarden to \([0-9][0-9.]*\)$|\1|p' "${changelog}" \
    | head -n1)"
cur_addon="$(sed -n 's|^version: \(.*\)$|\1|p' "${config}")"

if [[ -z "${pinned}" || -z "${shipped}" || -z "${cur_addon}" ]]; then
    echo "Could not read the current versions; has the layout changed?" >&2
    exit 1
fi

target="${pinned}"
[[ $# -gt 0 ]] && target="${1#v}"

if [[ "${target}" == "${shipped}" ]]; then
    echo "Add-on ${cur_addon} already ships Vaultwarden ${shipped}."
    emit "changed=false" "shipped=${shipped}" "version=${target}" \
        "addon_version=${cur_addon}"
    exit 0
fi

if [[ "$(printf '%s\n%s\n' "${shipped}" "${target}" | sort -V | tail -n1)" \
    != "${target}" ]]; then
    echo "Refusing to downgrade: shipped ${shipped}, asked for ${target}." >&2
    exit 1
fi

# Only now that the request is known good is anything written, so a refusal
# leaves the tree exactly as it was found.
if [[ "${target}" != "${pinned}" ]]; then
    sed -i \
        "s|^FROM \"vaultwarden/server:.*\" AS vaultwarden$|FROM \"vaultwarden/server:${target}\" AS vaultwarden|" \
        "${dockerfile}"
fi

IFS=. read -r old_major old_minor _ <<<"${shipped}"
IFS=. read -r new_major new_minor _ <<<"${target}"
IFS=. read -r addon_major addon_minor addon_patch <<<"${cur_addon}"

if [[ "${new_major}.${new_minor}" == "${old_major}.${old_minor}" ]]; then
    new_addon="${addon_major}.${addon_minor}.$((addon_patch + 1))"
else
    new_addon="${addon_major}.$((addon_minor + 1)).0"
fi

sed -i "s|^version: .*$|version: ${new_addon}|" "${config}"

# Prepend the entry, keeping the "# Changelog" heading in place.
tmp="$(mktemp)"
{
    printf '# Changelog\n\n## %s\n\n- ⬆️ Update Vaultwarden to %s\n' \
        "${new_addon}" "${target}"
    tail -n +2 "${changelog}"
} >"${tmp}"
mv "${tmp}" "${changelog}"

# The README headlines the shipped version in a handful of anchored spots. A
# pattern that stops matching only means the README drifts, so warn, do not
# fail the release over prose.
before="$(cat "${readme}")"
sed -i \
    -e "s|^\(# Vaultwarden add-on for Home Assistant — \)[0-9][0-9.]*\( fork\)$|\1${target}\2|" \
    -e "s|\*\*Vaultwarden [0-9][0-9.]*\*\*|**Vaultwarden ${target}**|g" \
    -e "s|\(\`vaultwarden/server\` [0-9][0-9.]* → \*\*\)[0-9][0-9.]*\(\*\*\)|\1${target}\2|" \
    -e "s|a release with [0-9][0-9.]* or newer|a release with ${target} or newer|" \
    "${readme}"
if [[ "${before}" == "$(cat "${readme}")" ]]; then
    echo "Warning: README.md was not touched; check its version references." >&2
fi

echo "Vaultwarden ${shipped} -> ${target} (add-on ${cur_addon} -> ${new_addon})"
emit "changed=true" "shipped=${shipped}" "version=${target}" \
    "addon_version=${new_addon}"
