#!/usr/bin/env bash
set -eu

usage() {
  cat <<'EOF'
Usage: install.sh [--source DIR] [--agents-home DIR]
EOF
}

source_dir=""
agents_home="$HOME/.agents"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --source) [ "$#" -ge 2 ] || exit 2; source_dir="$2"; shift 2 ;;
    --agents-home) [ "$#" -ge 2 ] || exit 2; agents_home="$2"; shift 2 ;;
    --help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done
source_dir="${source_dir:-$(CDPATH= cd -P "$(dirname "$0")/.." && pwd -P)}"
mkdir -p "$agents_home/skills"
destination="$agents_home/skills/token-telemetry"
if [ -L "$destination" ]; then
  [ "$(readlink "$destination")" = "$source_dir" ] && exit 0
  echo "Refusing to replace conflicting symlink: $destination" >&2
  exit 1
fi
if [ -e "$destination" ]; then
  echo "Destination exists: $destination" >&2
  exit 1
fi
ln -s "$source_dir" "$destination"
printf 'Installed token-telemetry at %s\n' "$destination"
