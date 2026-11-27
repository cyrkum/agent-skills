#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -P "$(dirname "$0")" && pwd -P)"

usage() {
    cat <<EOF
Usage: $0 [--agents-home PATH] [SKILL_NAME]

Install all skill directories containing SKILL.md, or install only SKILL_NAME.
The default agents home is \$HOME/.agents.

Options:
  --agents-home PATH  Use PATH instead of \$HOME/.agents
  --help              Show this help
EOF
}

fail() {
    printf 'Error: %s\n' "$1" >&2
    exit 1
}

agents_home="$HOME/.agents"
skill_name=""
skill_selected=0

while [ "$#" -gt 0 ]; do
    case "$1" in
        --help)
            usage
            exit 0
            ;;
        --agents-home)
            [ "$#" -ge 2 ] || fail "--agents-home requires a path."
            agents_home="$2"
            [ -n "$agents_home" ] || fail "--agents-home path cannot be empty."
            shift 2
            ;;
        --agents-home=*)
            agents_home="${1#--agents-home=}"
            [ -n "$agents_home" ] || fail "--agents-home path cannot be empty."
            shift
            ;;
        -*)
            fail "Unknown option '$1'. Use --help for usage."
            ;;
        *)
            [ "$skill_selected" -eq 0 ] || fail "Specify at most one skill name."
            skill_name="$1"
            skill_selected=1
            shift
            ;;
    esac
done

skills_home="$agents_home/skills"
skills_home_ready=0

prepare_skills_home() {
    if [ "$skills_home_ready" -eq 0 ]; then
        mkdir -p "$skills_home"
        skills_home="$(CDPATH= cd -P "$skills_home" && pwd -P)"
        skills_home_ready=1
    fi
}

install_skill() {
    name="$1"
    case "$name" in
        ""|.|..|*/*)
            fail "Invalid skill name '$name'."
            ;;
    esac

    skill_dir="$SCRIPT_DIR/$name"
    [ -f "$skill_dir/SKILL.md" ] || fail "Unknown skill '$name' (expected $skill_dir/SKILL.md)."

    prepare_skills_home
    destination="$skills_home/$name"
    if [ -L "$destination" ]; then
        existing_target="$(readlink "$destination")"
        if [ "$existing_target" = "$skill_dir" ]; then
            printf "Skill '%s' is already installed at %s\n" "$name" "$destination"
            return 0
        fi
        fail "Destination '$destination' is a symlink to '$existing_target'; not replacing it."
    fi
    [ ! -e "$destination" ] || fail "Destination '$destination' already exists; not replacing it."

    ln -s "$skill_dir" "$destination"
    printf "Installed skill '%s' at %s -> %s\n" "$name" "$destination" "$skill_dir"
}

if [ "$skill_selected" -eq 1 ]; then
    install_skill "$skill_name"
else
    found_skill=0
    for skill_file in "$SCRIPT_DIR"/*/SKILL.md; do
        [ -f "$skill_file" ] || continue
        skill_dir="${skill_file%/SKILL.md}"
        install_skill "${skill_dir##*/}"
        found_skill=1
    done
    [ "$found_skill" -eq 1 ] || fail "No skill directories containing SKILL.md were found."
fi
