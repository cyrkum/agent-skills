# First-use installation

Run `sh "$skill_dir/scripts/bootstrap.sh"` before using this skill. On macOS
and Linux, the first successful run per user and hostname installs missing
dependencies, starts Ollama if needed, downloads the small profile if missing,
and runs its eight evidence checks. Later runs only check the completion marker;
they do not check, repair, download, or requalify dependencies. This relies on
the agent following the skill instructions; invoking `worker.py` directly does
not trigger bootstrap.

Dependencies are a POSIX shell and standard Unix utilities, network access,
Python 3.9+, Ollama, and `qwen3.5:9b-q4_K_M` (approximately 6.6 GB). Downloads
and inference require sufficient disk space and memory. `curl` is required for
installers. The optional `standard` profile (`phi4:14b`, approximately 9.1 GB)
is installed only when explicitly selected with `setup --profile standard`.
No Python packages are needed.

On macOS, missing Python or Ollama is installed with Homebrew. If Homebrew is
missing, its official installer is downloaded from GitHub and run first. macOS
must already have `curl` and the prerequisites required by Homebrew, including
Apple command-line developer tools. On Linux, missing Python and curl are
installed with `apt-get` or `dnf`, and missing Ollama with the official Ollama
Linux installer. Other Linux package managers require Python and curl to be
installed beforehand. The selected distribution must supply Python 3.9 or
newer. Official installers can themselves require additional system tools or
privileges. These workflows execute downloaded vendor installation scripts and
modify the system; administrator approval and network access may be required.
Direct package-manager commands use `sudo -A`; configure an askpass helper if
sudo needs a password. Consult the vendor installers' own requirements.

If Ollama is not reachable on loopback, bootstrap starts `ollama serve` in the
background and writes its output to `ollama.log` in the state directory.
Failure is reported and leaves no completion marker, so the next invocation
retries. Once complete, the marker is
`${XDG_STATE_HOME:-$HOME/.local/state}/delegate-local-tasks/bootstrap-v1-<hostname>`.
To deliberately reinstall or reverify, remove that specific marker and rerun
bootstrap. Concurrent attempts fail rather than running installers twice; after
an interrupted process, inspect the stale `<marker>.lock` directory, remove any
leftover `installer` or `complete` file inside it, and then remove that lock
directory.
For later service failures, inspect the log and use `python3 "$worker" doctor`;
requalify with `python3 "$worker" eval --profile small` after changing the
model, Ollama version, or worker prompt.
