# 🤖 Summary Gemini Bot

![Python](https://img.shields.io/badge/python-3.11-blue.svg)
![Docker](https://img.shields.io/badge/docker-ready-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

An advanced Telegram bot powered by **Google Gemini** models. It generates concise summaries for text, articles, PDFs, YouTube videos, and even audio files.

This is a fork of [summary-gpt-bot](https://github.com/tpai/summary-gpt-bot) migrating from OpenAI to Google Gemini, with added support for audio processing and Telegram Mini Apps.

## ✨ Features

- **📝 Text:** Summarizes long texts sent directly to the chat.
- **🔗 URLs:** Scrapes and summarizes web pages and articles.
- **📺 YouTube:** Fetches transcripts and summarizes videos (Video ID or URL).
- **📄 PDF:** Extracts text from uploaded PDF files and summarizes them.
- **🎤 Audio & Voice:** Summarizes voice messages and audio files (MP3, WAV, M4A, OGG) directly via Gemini's multimodal capabilities.
- **📱 Mini App:** Supports a Web Interface (Telegram Mini App) for easier input.
- **🔎 Explore:** Provides "Explore Similar" search results via DuckDuckGo.

## 🚀 Installation & Usage

Since this is a custom version, you need to build the Docker image yourself.

### 1. Clone the repository
```bash
git clone https://github.com/dandaniel2/summary-bot-gemini.git
cd summary-bot-gemini
```

### 2. Build the Docker Image
```bash
docker build -t my-gemini-bot .
```

### 3. Run the Container

```bash
docker run -d \
  --name gemini-summary-bot \
  --restart always \
  -e TELEGRAM_TOKEN="YOUR_TELEGRAM_BOT_TOKEN" \
  -e GOOGLE_API_KEY="YOUR_GOOGLE_AI_STUDIO_KEY" \
  -e LLM_MODEL="gemini-flash-lite-latest" \
  -e TS_LANG="English" \
  -e ALLOWED_USERS="12345678,87654321" \
  my-gemini-bot
```

### Alternative: Run with Docker Compose[[1](https://www.google.com/url?sa=E&q=https%3A%2F%2Fgithub.com%2Fdandaniel2%2Fsummary-gemini-bot)]
1. Create a `.env` file with your keys:
   ```bash
   TELEGRAM_TOKEN=your_token
   GOOGLE_API_KEY=your_key
2. Run:
   ```bash
   docker-compose up -d --build

## ⚙️ Configuration Variables

You can customize the bot's behavior using these environment variables:

| Variable | Description | Default |
| :--- | :--- | :--- |
| `TELEGRAM_TOKEN` | **Required.** Your Telegram Bot API token (get from @BotFather). | - |
| `GOOGLE_API_KEY` | **Required.** Your Google Gemini API key (get from [Google AI Studio](https://aistudio.google.com/)). | - |
| `LLM_MODEL` | The Gemini model version to use. Recommended: `gemini-flash-lite-latest` or `gemini-1.5-flash`. | `gemini-flash-lite-latest` |
| `TS_LANG` | The target language for the summary (e.g., `Russian`, `English`, `Spanish`). | `Russian` |
| `ALLOWED_USERS` | Comma-separated list of Telegram User IDs allowed to use the bot. | (Open to all if empty) |
| `CHUNK_SIZE` | Max characters per chunk. Gemini has a large context window, so we use a high value. | `100000` |
| `WEBAPP_URL` | URL to your hosted Web App (HTML page) for the Mini App button. | (Optional) |
| `DDG_REGION` | DuckDuckGo search region (e.g., `wt-wt`, `us-en`, `ru-ru`). | `wt-wt` |

## 📱 Setting up the Mini App (Optional)

To enable the "Open Mini App" button:
1. Host the `index.html` file (e.g., on GitHub Pages).
2. Set the `WEBAPP_URL` environment variable to your hosted URL.
3. Configure the Menu Button in @BotFather pointing to that URL.

## 🛠 Local Development

If you want to run it without Docker:

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Set environment variables (export or .env).
3. Run the bot:
   ```bash
   python main.py
   ```

## 📜 License

MIT License
