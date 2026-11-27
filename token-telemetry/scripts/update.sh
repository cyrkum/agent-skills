#!/usr/bin/env bash
set -eu
exec "$(CDPATH= cd -P "$(dirname "$0")" && pwd -P)/install.sh" "$@"
