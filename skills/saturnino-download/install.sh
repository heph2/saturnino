#!/bin/sh
set -eu

name='saturnino-download'
target='all'
scope='project'

usage() {
    cat <<'EOF'
Usage: install.sh [--target codex|claude|pi|all] [--scope project|user]

Install the Saturnino skill into one or all supported harnesses.
Project installs are relative to the current directory; user installs use the
harness home directories.
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --target)
            [ "$#" -ge 2 ] || { usage >&2; exit 2; }
            target=$2
            shift 2
            ;;
        --scope)
            [ "$#" -ge 2 ] || { usage >&2; exit 2; }
            scope=$2
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            usage >&2
            exit 2
            ;;
    esac
done

case "$target" in
    codex|claude|pi|all) ;;
    *) echo "unsupported target: $target" >&2; exit 2 ;;
esac
case "$scope" in
    project|user) ;;
    *) echo "unsupported scope: $scope" >&2; exit 2 ;;
esac

script_dir=$(CDPATH= cd "$(dirname "$0")" && pwd)

install_for() {
    harness=$1
    case "$scope:$harness" in
        project:codex) root='.agents/skills' ;;
        project:claude) root='.claude/skills' ;;
        project:pi) root='.pi/skills' ;;
        user:codex) root="${CODEX_HOME:-$HOME/.codex}/skills" ;;
        user:claude) root="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills" ;;
        user:pi) root="${PI_AGENT_DIR:-$HOME/.pi/agent}/skills" ;;
    esac

    destination="$root/$name"
    mkdir -p "$destination"
    cp "$script_dir/SKILL.md" "$destination/SKILL.md"
    printf 'installed %s -> %s\n' "$harness" "$destination/SKILL.md"
}

case "$target" in
    all)
        install_for codex
        install_for claude
        install_for pi
        ;;
    *)
        install_for "$target"
        ;;
esac
