# Installing skills

Use the repository's `install-skills.sh` script to make skills available under
an agents home directory. It creates a symbolic link for each skill directory
containing `SKILL.md`:

```text
<agents-home>/skills/<skill-name> -> <repository>/<skill-name>
```

The default agents home is `~/.agents`.

## For people

Run these commands from the repository, or use the path to the script from
another working directory:

```sh
# Install every skill in this repository
./install-skills.sh

# Install only one skill
./install-skills.sh delegate-local-tasks

# Use a different agents home
./install-skills.sh --agents-home "$HOME/.agents-work"

# Combine a custom agents home with one skill
./install-skills.sh --agents-home "$HOME/.agents-work" delegate-local-tasks
```

The script is safe to run again: an existing link to the same skill is left in
place. If the destination already contains a different link, file, or
directory, installation stops rather than replacing it. Resolve that
destination conflict before retrying.

## For agents

Run `install-skills.sh` with no skill name to install all repository skills.
Pass a skill's directory name to install only that skill. If the user specifies
a non-default agents home, pass it with `--agents-home PATH`; otherwise the
script uses `$HOME/.agents`. Check the script's exit status and output before
reporting success. It creates links, not copies, and can be invoked from any
working directory.
