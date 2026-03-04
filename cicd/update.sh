#!/bin/bash

# --- SETTINGS ---
PROJECT_DIR="$HOME/summary-bot-gemini"
ADMIN_ID="6552990229"
# -----------------

echo "========================================"
echo "Starting Update Process: $(date)"

cd "$PROJECT_DIR" || exit

# Load environment variables
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Function to send Telegram notifications
send_telegram() {
    # Replace spaces with %20 for URL encoding and handle newlines
    MSG=$(echo -e "$1" | sed 's/ /%20/g')
    curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_TOKEN/sendMessage" \
        -d chat_id="$ADMIN_ID" \
        -d text="$1" \
        -d parse_mode="Markdown" > /dev/null
}

# 0. Save current commit ID for potential rollback
PREV_COMMIT=$(git rev-parse HEAD)

# 1. Pull updates from GitHub
echo "Pulling from GitHub..."
git_output=$(git pull origin master 2>&1)
git_status=$?

if [ $git_status -ne 0 ]; then
    echo "Git Pull Failed!"
    send_telegram "⚠️ **Update Error (Git Pull Failed)** Failed to pull code from GitHub.\`$git_output\`"
    exit 1
fi

if [[ "$git_output" == *"Already up to date"* ]]; then
    echo "No changes detected."
    exit 0
fi

# 2. Build new Docker image
echo "Building new Docker image..."
docker compose build

if [ $? -ne 0 ]; then
    echo "Docker Build Failed!"
    # ROLLBACK
    git reset --hard "$PREV_COMMIT"
    send_telegram "❌ **Build Failed** Docker build failed. Rolled back to previous stable commit."
    exit 1
fi

# 3. Test for errors using pyflakes
echo "Testing code integrity..."
# Capture output of pyflakes to send it to Telegram if it fails
test_output=$(docker compose run --rm --no-deps --entrypoint "python -m pyflakes main.py" bot 2>&1)
test_status=$?

if [ $test_status -eq 0 ]; then
    echo "Code Integrity Check Passed!"
    
    # 4. Restart the service
    echo "Restarting Service..."
    docker compose up -d
    
    echo "Update Completed!"
    send_telegram "✅ **Bot updated successfully!**New version is now live."
else
    echo "Syntax Error Detected!"
    
    # !!! ROLLBACK !!!
    echo "Performing rollback to $PREV_COMMIT..."
    git reset --hard "$PREV_COMMIT"
    
    # Send detailed error report to Telegram
    send_telegram "🚫 **Update Aborted (Syntax Error)** Errors detected:\`\`\`$test_output\`\`\` Files have been rolled back to the last working version."
fi