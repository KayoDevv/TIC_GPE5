#!/usr/bin/env bash
# Replaces the unpacked Charon extension with the build the website currently serves.
#
# Chrome only auto-updates store (or policy-installed) extensions. An unpacked one keeps its ID,
# and so its history and settings, as long as it is reloaded from the same folder: this script
# refreshes that folder, then you click the reload arrow on chrome://extensions.
#
# First time: run it, then "Load unpacked" -> pick the folder it prints.
# Usage: update-extension.sh [folder]   (default ~/charon-extension)
#        CHARON_SITE=http://host update-extension.sh   to use another site
set -euo pipefail

site=${CHARON_SITE:-http://172.16.249.133}
dest=${1:-$HOME/charon-extension}
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

curl -fsSL "$site/charon-extension.zip" -o "$tmp/charon.zip"
unzip -q "$tmp/charon.zip" -d "$tmp/new"
# Never replace a working extension with something that is not one.
[ -f "$tmp/new/manifest.json" ] || { echo "error: the download has no manifest.json" >&2; exit 1; }

rm -rf "$dest"
mv "$tmp/new" "$dest"
version=$(sed -n 's/.*"version": *"\([^"]*\)".*/\1/p' "$dest/manifest.json" | head -1)
echo "Charon $version is in $dest"
echo "Now open chrome://extensions and click the reload arrow on Charon."
