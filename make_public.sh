#!/usr/bin/env bash
# make_public.sh — Build a public, GUI-only copy of this repo.
#
# Produces a clean tree that keeps the GitHub Actions CI working (the GUI
# fbs build) while stripping everything that should stay private:
#   - vial-qmk - ryzen/   (proprietary firmware source)
#   - public-stubs/       (firmware stubs, irrelevant without the firmware)
#   - *.pdf               (third-party copyrighted manuals)
#   - root-level *.md      internal planning/analysis docs + CLAUDE.md
#                          (README.md is kept; sub-directory READMEs are kept)
#
# Usage:
#   ./make_public.sh [target_dir]
#       Build the cleaned tree (default: ../vial-gui-public) and init a fresh
#       single-commit git repo in it.
#
#   ./make_public.sh [target_dir] --push <git-remote-url> [branch]
#       Also add the remote and push (branch default: main). Run this from a
#       machine that has push access (e.g. `gh auth` configured) — it cannot
#       be done from the sandboxed Claude environment.
#
# Examples:
#   ./make_public.sh
#   ./make_public.sh ../vial-gui-public --push git@github.com:curltonkeyboards/vial-gui-public.git
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$SCRIPT_DIR"
TARGET_DIR="${1:-$SCRIPT_DIR/../vial-gui-public}"

PUSH_URL=""
PUSH_BRANCH="main"
if [ "${2:-}" = "--push" ]; then
    PUSH_URL="${3:?--push requires a git remote URL}"
    PUSH_BRANCH="${4:-main}"
fi

echo "=== make_public ==="
echo "Source: $SOURCE_DIR"
echo "Target: $TARGET_DIR"
echo ""

# Fresh target
rm -rf "$TARGET_DIR"
mkdir -p "$TARGET_DIR"

# Copy everything except the private/large/irrelevant pieces.
# tar is used (rather than rsync/cp) for portability and to handle the
# space in the "vial-qmk - ryzen" directory name cleanly.
echo "[1/3] Copying GUI tree (excluding private content)..."
( cd "$SOURCE_DIR" && tar \
    --exclude='./.git' \
    --exclude='./vial-qmk - ryzen' \
    --exclude='./public-stubs' \
    --exclude='*.pdf' \
    -cf - . ) | ( cd "$TARGET_DIR" && tar -xf - )

# Strip root-level internal docs (keep the public README; keep sub-dir READMEs).
echo "[2/3] Removing root-level internal docs (keeping README.md)..."
find "$TARGET_DIR" -maxdepth 1 -type f -name '*.md' ! -name 'README.md' -delete

# Initialize a clean, single-commit git history (no private history leaks).
echo "[3/3] Initializing fresh git repo..."
cd "$TARGET_DIR"
git init -q -b main
git add -A
git -c commit.gpgsign=false \
    -c user.name="${GIT_AUTHOR_NAME:-public}" \
    -c user.email="${GIT_AUTHOR_EMAIL:-public@example.com}" \
    commit -q -m "Public GUI release (firmware/docs/PDFs stripped)"

echo ""
echo "Done. Public tree: $TARGET_DIR"
du -sh --exclude=.git "$TARGET_DIR" 2>/dev/null | awk '{print "Size (no .git): "$1}'

if [ -n "$PUSH_URL" ]; then
    echo ""
    echo "Pushing to $PUSH_URL ($PUSH_BRANCH)..."
    git remote add origin "$PUSH_URL"
    git push -u origin "main:$PUSH_BRANCH"
    echo "Pushed."
else
    echo ""
    echo "Not pushed. To publish (from a machine with push access):"
    echo "  gh repo create curltonkeyboards/vial-gui-public --public --source \"$TARGET_DIR\" --push"
    echo "  # or, against an existing empty repo:"
    echo "  cd \"$TARGET_DIR\" && git remote add origin <url> && git push -u origin main"
fi
