#!/bin/bash

# --- SETTINGS ---
PROJECT_DIR="~/summary-bot-gemini"
# Your Telegram ID for update notifications
ADMIN_ID="6552990229"
# -----------------

echo "========================================"
echo "Starting Update Process: $(date)"

# Navigate to project directory and load variables from .env
cd "$PROJECT_DIR" || exit
if [ -f .env ]; then
    # Read .env and export variables to the current script environment
    export $(grep -v '^#' .env | xargs)
fi

# Function to send Telegram notifications via curl
send_telegram() {
    MSG="$1"
    if [ -z "$TELEGRAM_TOKEN" ]; then
        echo "Token not found, skipping notification."
        return
    fi
    
    curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_TOKEN/sendMessage" \
        -d chat_id="$ADMIN_ID" \
        -d text="$MSG" \
        -d parse_mode="Markdown" > /dev/null
}

# 1. Pull updates from GitHub
echo "Pulling from GitHub..."
git_output=$(git pull origin master 2>&1)
git_status=$?

if [ $git_status -ne 0 ]; then
    echo "Git Pull Failed!"
    send_telegram "**Update Error (Git Pull Failed)**%0AFailed to pull code from GitHub.%0A\`$git_output\`"
    exit 1
fi

# Skip build if no changes were detected
if [[ "$git_output" == *"Already up to date"* ]]; then
    echo "No changes detected."
    # send_telegram "No updates found, bot is running latest version."
    exit 0
fi

# 2. Build new Docker image
echo "Building new Docker image..."
docker compose build

if [ $? -ne 0 ]; then
    echo "Docker Build Failed!"
    send_telegram "**Update Error (Build Failed)**%0AFailed to build Docker image. Bot was not updated."
    exit 1
fi

# 3. Test for errors using pyflakes (Catching NameErrors, undefined vars, etc.)
echo "Testing code integrity..."
docker compose run --rm --no-deps --entrypoint "python -m pyflakes main.py" bot

if [ $? -eq 0 ]; then
    echo "Code Integrity Check Passed!"
    
    # 4. Restart the service with new code (CD step)
    echo "Restarting Service..."
    docker compose up -d
    
    echo "Update Completed!"
    send_telegram "**Bot updated successfully!**%0ANew version is now live."
else
    echo "Syntax Error Detected!"
    send_telegram "**Code Error (Syntax Error)**%0ATest failed. Update aborted, old version is still running."
fi
