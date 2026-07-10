#!/usr/bin/env sh
set -eu
source_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/specimpact"
target="$HOME/.gemini/config/plugins/specimpact"
mkdir -p "$(dirname "$target")"
cp -R "$source_dir" "$target"
printf 'Installed SpecImpact Antigravity plugin to %s\n' "$target"
