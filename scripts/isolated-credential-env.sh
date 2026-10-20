#!/usr/bin/env bash
#
# Run a command with an isolated credential environment.
#
# WHY THIS EXISTS
#   The pre-commit "logout" hook runs `yt auth logout`, which clears the
#   credentials the CLI holds for the current user: it rewrites the credential
#   file (~/.config/youtrack-cli/.env) and deletes the matching OS keychain
#   entries.  Run against a developer's real home directory that hook silently
#   logs the machine out of YouTrack, and every later `yt` call fails to
#   authenticate until the developer logs in again.
#
#   The credential file path is derived from the home directory (Path.home()),
#   but the OS keychain does not live under it, so redirecting the home
#   directory alone would still let the hook delete the real keychain entry.
#   Both carriers therefore have to be redirected, which is what this wrapper
#   does:
#
#     HOME, USERPROFILE       -> a throwaway directory, so the credential file
#                                (and the theme and log directories) resolve
#                                inside it.
#     PYTHON_KEYRING_BACKEND  -> keyring.backends.null.Keyring, a backend that
#                                reads and writes nothing, so the OS keychain
#                                is never read and never written.
#     UV_CACHE_DIR            -> the real cache, so `uv run` still resolves the
#     UV_PYTHON_INSTALL_DIR   -> project environment without re-downloading it
#                                into the throwaway home directory.
#
#   Everything else is inherited unchanged, so a command that is meant to act
#   on a credential still finds one -- it just can never reach the caller's
#   own credential file or keychain entry.
#
# USAGE
#   scripts/isolated-credential-env.sh <command> [args...]
#
#   The throwaway directory is removed when the command exits.

set -euo pipefail

if [ "$#" -eq 0 ]; then
    echo "usage: $(basename "$0") <command> [args...]" >&2
    exit 2
fi

# Resolve the real tool directories before the home directory is redirected:
# both are derived from it, so afterwards they would resolve inside the
# throwaway directory and `uv` would re-download everything it needs.
real_cache_dir=""
real_python_dir=""
if command -v uv >/dev/null 2>&1; then
    real_cache_dir="$(uv cache dir 2>/dev/null || true)"
    real_python_dir="$(uv python dir 2>/dev/null || true)"
fi

scratch_home="$(mktemp -d "${TMPDIR:-/tmp}/yt-cli-credential-home.XXXXXX")"
cleanup() {
    rm -rf "$scratch_home"
}
trap cleanup EXIT

export HOME="$scratch_home"
export USERPROFILE="$scratch_home"
export PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring"
if [ -n "$real_cache_dir" ]; then
    export UV_CACHE_DIR="$real_cache_dir"
fi
if [ -n "$real_python_dir" ]; then
    export UV_PYTHON_INSTALL_DIR="$real_python_dir"
fi

"$@"
