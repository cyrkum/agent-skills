#!/bin/sh
set -eu

skill_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/delegate-local-tasks"
host=$(uname -n)
case "$host" in
    ""|*[!a-zA-Z0-9._-]*) echo "Cannot use this hostname for bootstrap state." >&2; exit 1 ;;
esac
marker="$state_dir/bootstrap-v1-$host"
lock="$marker.lock"

mkdir -p "$state_dir"
[ ! -f "$marker" ] || exit 0
if ! mkdir "$lock" 2>/dev/null; then
    echo "Bootstrap is already running or left a stale lock: $lock" >&2
    exit 1
fi
cleanup() {
    rm -f "$lock/installer" "$lock/complete"
    rmdir "$lock"
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
[ ! -f "$marker" ] || exit 0

os=$(uname -s)
case "$os" in
    Darwin|Linux) ;;
    *) echo "Unsupported system: $os (supported: macOS and Linux)." >&2; exit 1 ;;
esac

python_ok() {
    command -v python3 >/dev/null 2>&1 &&
        python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))'
}

if [ "$os" = Darwin ]; then
    PATH="$PATH:/opt/homebrew/bin:/usr/local/bin"
    export PATH
    if ! python_ok || ! command -v ollama >/dev/null 2>&1; then
        if ! command -v brew >/dev/null 2>&1; then
            echo "Installing Homebrew (administrator approval may be required)." >&2
            curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh -o "$lock/installer"
            NONINTERACTIVE=1 /bin/bash "$lock/installer"
            rm -f "$lock/installer"
        fi
        if ! python_ok; then
            brew install python
            PATH="$(brew --prefix)/bin:$PATH"
            export PATH
        fi
        if ! command -v ollama >/dev/null 2>&1; then brew install ollama; fi
    fi
else
    if ! python_ok; then
        if command -v apt-get >/dev/null 2>&1; then
            sudo -A apt-get update
            sudo -A apt-get install -y python3
        elif command -v dnf >/dev/null 2>&1; then
            sudo -A dnf install -y python3
        else
            echo "Install Python 3.9+ using your distribution's package manager, then retry." >&2
            exit 1
        fi
    fi
    if ! command -v ollama >/dev/null 2>&1; then
        if ! command -v curl >/dev/null 2>&1; then
            if command -v apt-get >/dev/null 2>&1; then
                sudo -A apt-get update
                sudo -A apt-get install -y curl
            elif command -v dnf >/dev/null 2>&1; then
                sudo -A dnf install -y curl
            else
                echo "Install curl using your distribution's package manager, then retry." >&2
                exit 1
            fi
        fi
        echo "Installing Ollama using its official Linux installer." >&2
        curl -fsSL https://ollama.com/install.sh -o "$lock/installer"
        sudo -A /bin/sh "$lock/installer"
        rm -f "$lock/installer"
    fi
fi

python_ok || { echo "Python 3.9+ is not available on PATH after installation." >&2; exit 1; }
command -v ollama >/dev/null 2>&1 || { echo "Ollama is not available on PATH after installation." >&2; exit 1; }
worker="$skill_dir/scripts/worker.py"
if ! python3 "$worker" doctor >/dev/null 2>&1; then
    echo "Starting Ollama; logs: $state_dir/ollama.log" >&2
    nohup ollama serve >"$state_dir/ollama.log" 2>&1 </dev/null &
    ready=0
    for delay in 1 1 1 1 1 1 1 1 1 1; do
        if python3 "$worker" doctor >/dev/null 2>&1; then ready=1; break; fi
        sleep "$delay"
    done
    [ "$ready" -eq 1 ] || { echo "Ollama did not start; inspect $state_dir/ollama.log." >&2; exit 1; }
fi
python3 "$worker" setup --profile small
printf '%s\n' "complete" > "$lock/complete"
mv "$lock/complete" "$marker"
