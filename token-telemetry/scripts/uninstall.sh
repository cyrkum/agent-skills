#!/usr/bin/env bash
set -eu

agents_home="${HOME}/.agents"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --agents-home) [ "$#" -ge 2 ] || exit 2; agents_home="$2"; shift 2 ;;
    --preserve-data) shift ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done
destination="$agents_home/skills/token-telemetry"
if [ -L "$destination" ]; then
  rm "$destination"
  echo "Uninstalled $destination; runtime telemetry was preserved."
elif [ -e "$destination" ]; then
  echo "Destination is not a symlink; refusing removal: $destination" >&2
  exit 1
fi
