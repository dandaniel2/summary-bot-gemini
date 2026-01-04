# 🤖 Summary Gemini Bot

![Python](https://img.shields.io/badge/python-3.11-blue.svg)
![Docker](https://img.shields.io/badge/docker-ready-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

An advanced Telegram bot powered by **Google Gemini** models. It generates concise summaries for text, articles, PDFs, YouTube videos, images, and audio files.

This bot uses the official **Google Custom Search API** for the "Explore Similar" feature, ensuring stable results without IP bans.

## ✨ Features

- **📝 Text & Links:** Summarizes long texts and articles sent directly to the chat.
- **📺 YouTube:** Fetches transcripts (auto/manual) and summarizes videos.
- **📄 PDF:** Extracts text from uploaded PDF files and summarizes them.
- **🖼 Images (OCR):** Analyzes images and summarizes text within them.
- **🎤 Audio & Voice:** Summarizes voice messages and audio files (MP3, WAV, M4A, OGG) directly via Gemini's multimodal capabilities.
- **🔎 Explore Similar:** Performs a Google Search to find related articles using **Google Custom Search API**.
- **📱 Mini App:** Supports a Web Interface (Telegram Mini App) for convenient text input.

## 🛠 Prerequisites

Before running the bot, you need to obtain the following keys:

### 1. Telegram Bot Token
*   Talk to [BotFather](https://t.me/BotFather) on Telegram to create a bot and get the `TELEGRAM_TOKEN`.

### 2. Google Gemini API Key
*   Get your free API key at [Google AI Studio](https://aistudio.google.com/).
*   This key is used for the `GOOGLE_API_KEY` variable.

### 3. Google Custom Search ID (For "Explore Similar")
This allows the bot to search the web without getting blocked.
1.  Go to **[Google Cloud Console](https://console.cloud.google.com/apis/library/customsearch.googleapis.com)** and **Enable** the "Custom Search API" for your project.
    *   *Note:* Ensure your API Key restrictions allow "Custom Search API".
2.  Go to **[Programmable Search Engine](https://programmablesearchengine.google.com/controlpanel/create)**.
3.  Click **Add**.
4.  **Name:** Anything (e.g., BotSearch).
5.  **What to search:** Select **"Search the entire web"**.
6.  Click **Create** and copy the **Search engine ID** (looks like `012345:abcdefg`).
7.  This ID is used for the `GOOGLE_CSE_ID` variable.

## 🚀 Installation & Usage

### Option 1: Docker (Recommended)

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/dandaniel2/summary-bot-gemini.git
    cd summary-bot-gemini
    ```

2.  **Build the image:**
    ```bash
    docker build -t my-gemini-bot .
    ```

3.  **Run the container:**
    *(Replace the placeholders with your actual keys)*
    ```bash
    docker run -d \
      --name gemini-summary-bot \
      --network host \
      --restart always \
      -e TELEGRAM_TOKEN="your_telegram_token" \
      -e GOOGLE_API_KEY="your_google_api_key" \
      -e GOOGLE_CSE_ID="your_search_engine_id" \
      -e LLM_MODEL="gemini-flash-latest" \
      -e TS_LANG="Russian" \
      -e ALLOWED_USERS="12345678,87654321" \
      my-gemini-bot
    ```

### Option 2: Docker Compose

1.  Create a `.env` file in the project root:
    ```ini
    TELEGRAM_TOKEN=your_token
    GOOGLE_API_KEY=your_key
    GOOGLE_CSE_ID=your_cse_id
    LLM_MODEL=gemini-flash-latest
    TS_LANG=Russian
    ALLOWED_USERS=12345678
    WEBAPP_URL=https://dandaniel2.github.io/summary-bot-gemini/
    ```

2.  Run with Compose:
    ```bash
    docker-compose up -d --build
    ```

## ⚙️ Configuration Variables

| Variable | Description | Default |
| :--- | :--- | :--- |
| `TELEGRAM_TOKEN` | **Required.** Your Telegram Bot API token. | - |
| `GOOGLE_API_KEY` | **Required.** Your Google Gemini API key. | - |
| `GOOGLE_CSE_ID` | **Required.** Google Programmable Search Engine ID (CX). | - |
| `LLM_MODEL` | The Gemini model version. Recommended: `gemini-flash-latest` or `gemini-1.5-flash`. | `gemini-flash-lite-latest` |
| `TS_LANG` | The target language for the summary (e.g., `Russian`, `English`). | `Russian` |
| `ALLOWED_USERS` | Comma-separated list of Telegram User IDs allowed to use the bot. | (Open to all if empty) |
| `WEBAPP_URL` | URL to your hosted Web App (index.html) for the Mini App button. | (Optional) |
| `CHUNK_SIZE` | Max characters per chunk. Gemini has a large context window, so we use a high value. | `100000` |

## 📱 Mini App Setup (Optional)

To enable the "Input Text" button under the keyboard:
1.  The `docs/index.html` file is ready to use.
2.  Set the `WEBAPP_URL` environment variable to your GitHub Pages URL (e.g., `https://username.github.io/repo/`).
3.  Restart the bot.

## 📜 License

MIT License
