#!/bin/bash
# Local launchd-driven runner.
# Flow: sync repo -> run Playwright Costco scrape -> commit & push costco.json.
# Safe to run manually or from launchd.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

LOG_PREFIX="[$(date -u +'%Y-%m-%dT%H:%M:%SZ') costco-local]"
echo "$LOG_PREFIX start (repo=$REPO_DIR)"

# --- sync with remote so we don't race GitHub Actions commits
git fetch origin main --quiet
if ! git pull --rebase --autostash origin main; then
  echo "$LOG_PREFIX pull failed — aborting"
  exit 1
fi

# --- activate venv
if [[ -d "$REPO_DIR/.venv" ]]; then
  # shellcheck disable=SC1091
  source "$REPO_DIR/.venv/bin/activate"
else
  echo "$LOG_PREFIX no .venv found. Create it with:"
  echo "  python3 -m venv .venv"
  echo "  .venv/bin/pip install -r requirements-local.txt"
  echo "  .venv/bin/playwright install chromium"
  exit 1
fi

# --- run the fetcher
if ! python -m scripts.fetch_costco_pw; then
  echo "$LOG_PREFIX fetcher failed — no commit"
  exit 1
fi

# --- commit & push if costco.json changed
git add docs/costco.json
if git diff --staged --quiet; then
  echo "$LOG_PREFIX no costco.json changes — skipping commit"
  exit 0
fi

git -c user.name="costco-local-bot" -c user.email="costco-local-bot@users.noreply.github.com" \
  commit -m "chore(costco): refresh at $(date -u +'%Y-%m-%dT%H:%M:%SZ')"

if git push origin main; then
  echo "$LOG_PREFIX pushed successfully"
else
  echo "$LOG_PREFIX push failed — will retry next run"
  exit 1
fi
