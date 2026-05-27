#!/bin/bash
# Daily Company Crawler - Automated Execution Script
# This script runs the company crawler and logs the output

# Add Claude CLI to PATH
export PATH="$HOME/.local/bin:$PATH"

# Project directory
PROJECT_DIR="/home/rlwrld/projects/scouting_bot"
cd "$PROJECT_DIR" || exit 1

# Create logs directory if it doesn't exist
LOGS_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOGS_DIR"

# Log file with timestamp
LOG_FILE="$LOGS_DIR/crawler_$(date +\%Y-\%m-\%d).log"

# Slack credentials are loaded from .env file by daily_crawler.py

# Log start time
echo "" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"
echo "Daily Crawler Started: $(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# Activate virtual environment and run crawler
source "$PROJECT_DIR/.venv/bin/activate"

# Run the daily crawler
python3 "$PROJECT_DIR/daily_crawler.py" 2>&1 | tee -a "$LOG_FILE"

# Log end time
echo "" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"
echo "Daily Crawler Completed: $(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# Deactivate virtual environment
deactivate

# Auto-commit and push if there are changes
echo "" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"
echo "Checking for data changes..." | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# Check if there are any changes in the data directory.
# NOTE: `git diff` ignores untracked files, so new daily snapshots / a brand-new
# company's data would never trigger a commit. `git status --porcelain` catches
# modified, staged AND untracked files.
if [ -z "$(git status --porcelain data/)" ]; then
    echo "✅ No changes detected in data/" | tee -a "$LOG_FILE"
else
    echo "📝 Changes detected! Committing and pushing..." | tee -a "$LOG_FILE"

    # Stage all changes including new (untracked) files
    git add -A data/

    # Commit with timestamp
    COMMIT_MSG="Auto-update company data - $(date '+%Y-%m-%d %H:%M:%S KST')

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

    git commit -m "$COMMIT_MSG" 2>&1 | tee -a "$LOG_FILE"

    # Push to remote
    if git push origin main 2>&1 | tee -a "$LOG_FILE"; then
        echo "✅ Successfully pushed to GitHub!" | tee -a "$LOG_FILE"
    else
        echo "❌ Failed to push to GitHub" | tee -a "$LOG_FILE"
    fi
fi

echo "" | tee -a "$LOG_FILE"

# Keep only last 30 days of logs
find "$LOGS_DIR" -name "crawler_*.log" -mtime +30 -delete

exit 0
