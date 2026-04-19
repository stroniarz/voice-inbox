#!/usr/bin/env bash
# Publish tools/voice-inbox/ changes to public repo via git subtree split.
# Run from anywhere inside the monorepo.

set -euo pipefail

REMOTE="voice-inbox-pub"
PREFIX="tools/voice-inbox"
SPLIT_BRANCH="voice-inbox-split"

# Navigate to monorepo root
cd "$(git rev-parse --show-toplevel)"

# Verify remote exists
if ! git remote get-url "$REMOTE" >/dev/null 2>&1; then
  echo "ERROR: remote '$REMOTE' not configured."
  echo "Add it: git remote add $REMOTE https://github.com/stroniarz/voice-inbox.git"
  exit 1
fi

# Ensure no uncommitted changes in the prefix
if ! git diff --quiet -- "$PREFIX" || ! git diff --cached --quiet -- "$PREFIX"; then
  echo "ERROR: uncommitted changes in $PREFIX. Commit them first."
  exit 1
fi

echo "→ Splitting subtree history..."
git subtree split --prefix="$PREFIX" --branch="$SPLIT_BRANCH"

echo "→ Pushing to $REMOTE:main..."
git push "$REMOTE" "$SPLIT_BRANCH:main"

echo "✓ Published. Public repo updated."
