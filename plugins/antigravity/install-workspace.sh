#!/usr/bin/env sh
set -eu
workspace="${1:-$PWD}"
source_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/specimpact"
target="$workspace/.agents/plugins/specimpact"
mkdir -p "$(dirname "$target")"
cp -R "$source_dir" "$target"
printf 'Installed SpecImpact Antigravity plugin to %s\n' "$target"
