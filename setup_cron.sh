#!/bin/bash
# Setup cron job for daily company crawler
#
# This script adds a cron job to run the crawler every day at 8:00 AM KST

CRON_SCHEDULE="0 8 * * *"
SCRIPT_PATH="/home/rlwrld/projects/scouting_bot/run_daily_crawler.sh"

# Check if webhook URL is set
if [ -z "$SLACK_WEBHOOK_URL" ]; then
    echo "❌ ERROR: SLACK_WEBHOOK_URL is not set!"
    echo ""
    echo "Please run the following command first:"
    echo "  export SLACK_WEBHOOK_URL='your-webhook-url'"
    echo ""
    echo "To make it permanent, add this line to ~/.bashrc:"
    echo "  echo 'export SLACK_WEBHOOK_URL=\"your-webhook-url\"' >> ~/.bashrc"
    echo "  source ~/.bashrc"
    exit 1
fi

# Create cron entry
CRON_ENTRY="$CRON_SCHEDULE SLACK_WEBHOOK_URL='$SLACK_WEBHOOK_URL' $SCRIPT_PATH"

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -F "$SCRIPT_PATH" >/dev/null; then
    echo "⚠️  Cron job already exists!"
    echo ""
    echo "Current cron jobs:"
    crontab -l | grep -F "$SCRIPT_PATH"
    echo ""
    read -p "Do you want to replace it? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
    # Remove existing entry
    (crontab -l 2>/dev/null | grep -v -F "$SCRIPT_PATH") | crontab -
fi

# Add new cron job
(crontab -l 2>/dev/null; echo "$CRON_ENTRY") | crontab -

echo "✅ Cron job added successfully!"
echo ""
echo "Cron schedule: Every day at 8:00 AM KST"
echo "Script: $SCRIPT_PATH"
echo ""
echo "To view your cron jobs:"
echo "  crontab -l"
echo ""
echo "To edit cron jobs manually:"
echo "  crontab -e"
echo ""
echo "To remove the cron job:"
echo "  crontab -e  # Then delete the line containing '$SCRIPT_PATH'"
