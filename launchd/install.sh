#!/bin/bash
# Installs the Costco launchd agent on macOS.
# Renders the plist template with this repo's absolute path, copies it into
# ~/Library/LaunchAgents/, and loads it. Safe to re-run (unloads first).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="$REPO_DIR/launchd/com.gold-app.costco.plist.template"
TARGET_DIR="$HOME/Library/LaunchAgents"
TARGET="$TARGET_DIR/com.gold-app.costco.plist"

if [[ ! -f "$TEMPLATE" ]]; then
  echo "Template missing: $TEMPLATE" >&2
  exit 1
fi

mkdir -p "$TARGET_DIR"
mkdir -p "$REPO_DIR/logs"

echo "Rendering plist -> $TARGET (repo=$REPO_DIR)"
sed "s|__REPO_PATH__|$REPO_DIR|g" "$TEMPLATE" > "$TARGET"

if launchctl list | grep -q com.gold-app.costco; then
  echo "Unloading previous agent..."
  launchctl unload "$TARGET" 2>/dev/null || true
fi

echo "Loading agent..."
launchctl load "$TARGET"

echo ""
echo "Done. The agent will:"
echo "  - run once immediately"
echo "  - then every 30 min while your Mac is awake"
echo ""
echo "Watch the first run:   tail -f $REPO_DIR/logs/costco.out.log"
echo "Errors:                tail -f $REPO_DIR/logs/costco.err.log"
echo "Uninstall:             launchctl unload $TARGET && rm $TARGET"
