#!/bin/bash
# Daily Company Crawler - Automated Execution Script
# This script runs the company crawler and logs the output

# Project directory
PROJECT_DIR="/home/rlwrld/projects/scouting_program/scouting_bot"
cd "$PROJECT_DIR" || exit 1

# Create logs directory if it doesn't exist
LOGS_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOGS_DIR"

# Log file with timestamp
LOG_FILE="$LOGS_DIR/crawler_$(date +\%Y-\%m-\%d).log"

# Export Slack webhook URL (set this to your actual webhook URL)
# You can also set this in ~/.bashrc for persistence
export SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL:-}"

# Check if webhook URL is set
if [ -z "$SLACK_WEBHOOK_URL" ]; then
    echo "[ERROR] SLACK_WEBHOOK_URL is not set!" | tee -a "$LOG_FILE"
    echo "Please set it by running:" | tee -a "$LOG_FILE"
    echo "  export SLACK_WEBHOOK_URL='your-webhook-url'" | tee -a "$LOG_FILE"
    exit 1
fi

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

# Check if there are any changes in the data directory
if git diff --quiet data/ && git diff --cached --quiet data/; then
    echo "✅ No changes detected in data/" | tee -a "$LOG_FILE"
else
    echo "📝 Changes detected! Committing and pushing..." | tee -a "$LOG_FILE"

    # Add changes
    git add data/

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
