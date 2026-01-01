import asyncio
import os
import re
import time
import trafilatura
from google import genai
from google.genai import types
from duckduckgo_search import DDGS
from PyPDF2 import PdfReader
from tqdm import tqdm
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo, Update
from telegram.ext import CommandHandler, MessageHandler, CallbackQueryHandler, filters, ApplicationBuilder, ContextTypes
from youtube_transcript_api import YouTubeTranscriptApi

# --- КОНФИГУРАЦИЯ ---
telegram_token = os.environ.get("TELEGRAM_TOKEN", "xxx")
model_name = os.environ.get("LLM_MODEL", "gemini-flash-lite-latest")
lang = os.environ.get("TS_LANG", "Russian")
ddg_region = os.environ.get("DDG_REGION", "wt-wt")
chunk_size = int(os.environ.get("CHUNK_SIZE", 100000))
allowed_users = os.environ.get("ALLOWED_USERS", "")
google_api_key = os.environ.get("GOOGLE_API_KEY", "")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "")

client = None
if google_api_key:
    client = genai.Client(api_key=google_api_key)


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def list_available_models():
    if not client: return
    print("--- Checking available Gemini models ---")
    try:
        for m in client.models.list():
            if "flash" in m.name:
                print(f"Found: {m.name}")
    except Exception as e:
        print(f"Error listing models: {e}")
    print("----------------------------------------")


def split_user_input(text):
    paragraphs = text.split('\n')
    paragraphs = [paragraph.strip() for paragraph in paragraphs if paragraph.strip()]
    return paragraphs


def scrape_text_from_url(url):
    try:
        downloaded = trafilatura.fetch_url(url)
        text = trafilatura.extract(downloaded, include_formatting=True)
        if text is None: return []
        return [text]
    except Exception as e:
        print(f"Error scraping: {e}")
        return []


async def search_results(keywords):
    try:
        with DDGS() as ddgs:
            results = [r for r in ddgs.text(keywords, region=ddg_region, safesearch='off', max_results=3)]
        return results
    except Exception as e:
        print(f"DDG Error: {e}")
        return []


# --- ЛОГИКА САММАРИЗАЦИИ ТЕКСТА ---

def summarize(text_array):
    def create_chunks(paragraphs):
        chunks = []
        chunk = ''
        for paragraph in paragraphs:
            if len(chunk) + len(paragraph) < chunk_size:
                chunk += paragraph + ' '
            else:
                chunks.append(chunk.strip())
                chunk = paragraph + ' '
        if chunk:
            chunks.append(chunk.strip())
        return chunks

    try:
        if isinstance(text_array, list) and len(text_array) == 1 and len(text_array[0]) < chunk_size:
            text_chunks = text_array
        else:
            flat_text = "\n".join(text_array)
            if len(flat_text) < chunk_size:
                text_chunks = [flat_text]
            else:
                text_chunks = create_chunks(text_array)

        summaries = []
        system_instruction = (
            "You are an expert in creating summaries. "
            f"Respond in {lang}. Do not translate technical terms."
        )

        for i, chunk in enumerate(tqdm(text_chunks, desc="Summarizing Text")):
            if not chunk.strip(): continue
            prompt = f"Summarize this section:\n{chunk}"
            result = call_gemini_with_retry(prompt, system_instruction)
            if result: summaries.append(result)
            if i < len(text_chunks) - 1: time.sleep(2)

        if not summaries: return "Ошибка получения ответа."
        if len(summaries) == 1: return summaries[0]

        summary = ' '.join(summaries)
        final_prompt = f"Combine these points into a final bulleted summary in {lang}:\n{summary}"
        return call_gemini_with_retry(final_prompt, system_instruction)

    except Exception as e:
        print(f"Error in summarize: {e}")
        return f"Error: {e}"


# --- АУДИО ---

def summarize_audio(file_bytes, mime_type):
    """Отправляет аудио напрямую в Gemini"""
    if not client: return "API Key Error"

    system_instruction = (
        "You are an expert listener and summarizer. "
        "Listen to the audio and create a concise bulleted summary of the key points. "
        f"Respond in {lang}."
    )

    try:
        prompt = "Summarize this audio."

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.3
        )

        response = client.models.generate_content(
            model=model_name,
            contents=[
                types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                prompt
            ],
            config=config
        )

        if response.text:
            return response.text.strip()
        return "Модель вернула пустой ответ."

    except Exception as e:
        if "429" in str(e): return "Превышены лимиты API (429)."
        print(f"Audio Error: {e}")
        return f"Ошибка обработки аудио: {e}"


def call_gemini_with_retry(prompt, system_instruction, retries=3):
    for attempt in range(retries):
        res = call_gemini_api(prompt, system_instruction)
        if res == "429":
            time.sleep((attempt + 1) * 5)
            continue
        return res
    return "Error: Quota exceeded."


def call_gemini_api(prompt, system_instruction=None):
    if not client: return "API Key Error"
    try:
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.3
        )
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=config
        )
        if response.text: return response.text.strip()
        return ""
    except Exception as e:
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e): return "429"
        print(f"Gemini API Error: {e}")
        return ""


# --- YOUTUBE И PDF ---
def extract_youtube_transcript(youtube_url):
    try:
        video_id_match = re.search(r"(?<=v=)[^&]+|(?<=youtu.be/)[^?|\n]+", youtube_url)
        video_id = video_id_match.group(0) if video_id_match else None
        if video_id is None: return "no transcript"
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        transcript = transcript_list.find_transcript(['en', 'ru', 'ja', 'ko', 'de', 'fr'])
        transcript_text = ' '.join([item['text'] for item in transcript.fetch()])
        return transcript_text
    except Exception as e:
        print(f"Error transcript: {e}")
        return "no transcript"


def retrieve_yt_transcript_from_url(youtube_url):
    output = extract_youtube_transcript(youtube_url)
    if output == 'no transcript': raise ValueError("No transcript found.")
    return [output]


# --- ОБРАБОТЧИКИ TELEGRAM ---

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = f"Привет! Я использую модель {model_name}.\n\nЯ умею работать с:\n📝 Текстом и ссылками\n📺 YouTube видео\n📄 PDF документами\n🎤 **Голосовыми сообщениями**\n🎵 **Аудиофайлами (MP3, WAV, M4A)**"
    if WEBAPP_URL:
        kb = [[KeyboardButton(text="📱 Открыть Mini App", web_app=WebAppInfo(url=WEBAPP_URL))]]
        markup = ReplyKeyboardMarkup(kb, resize_keyboard=True)
        await update.message.reply_text(msg, reply_markup=markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(msg, parse_mode="Markdown")


async def handle_summarize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if allowed_users and str(chat_id) not in allowed_users.split(','):
        await update.message.reply_text("Access denied.")
        return
    await process_request(update.message.text, chat_id, update, context)


async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if allowed_users and str(chat_id) not in allowed_users.split(','): return
    data = update.effective_message.web_app_data.data
    await process_request(data, chat_id, update, context, from_webapp=True)


async def handle_audio_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if allowed_users and str(chat_id) not in allowed_users.split(','):
        await update.message.reply_text("Access denied.")
        return

    message = update.message

    if message.voice:
        file_obj = message.voice
        file_name = "voice.ogg"
        mime_type = "audio/ogg"
    elif message.audio:
        file_obj = message.audio
        file_name = file_obj.file_name or "audio.mp3"
        mime_type = file_obj.mime_type or "audio/mpeg"
    else:
        return

    if file_obj.file_size > 20 * 1024 * 1024:
        await update.message.reply_text(
            "⚠️ Файл слишком большой (>20MB). Telegram API не позволяет ботам скачивать такие файлы.")
        return

    await context.bot.send_chat_action(chat_id=chat_id, action="UPLOAD_VOICE")
    await update.message.reply_text("🎧 Слушаю и анализирую аудио... Это может занять время.")

    try:
        new_file = await context.bot.get_file(file_obj.file_id)
        file_byte_array = await new_file.download_as_bytearray()

        loop = asyncio.get_running_loop()
        summary = await loop.run_in_executor(None, summarize_audio, file_byte_array, mime_type)

        await update.message.reply_text(
            f"🎤 **Саммари аудио:**\n\n{summary}",
            reply_markup=get_inline_keyboard_buttons(),
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Audio Handler Error: {e}")
        await update.message.reply_text(f"Ошибка обработки аудио: {e}")


async def process_request(user_input, chat_id, update, context, from_webapp=False):
    try:
        text_array = process_user_input(user_input)
        if not text_array:
            msg = "Не удалось распознать ссылку или текст пустой."
            await context.bot.send_message(chat_id=chat_id, text=msg)
            return

        await context.bot.send_chat_action(chat_id=chat_id, action="TYPING")
        loop = asyncio.get_running_loop()
        summary = await loop.run_in_executor(None, summarize, text_array)
        prefix = "📱 **Результат из Web App:**\n\n" if from_webapp else ""
        await context.bot.send_message(chat_id=chat_id, text=f"{prefix}{summary}",
                                       reply_markup=get_inline_keyboard_buttons(),
                                       parse_mode="Markdown" if from_webapp else None)
    except Exception as e:
        print(f"Processing Error: {e}")
        await context.bot.send_message(chat_id=chat_id, text=f"Ошибка: {e}")


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    file_path = f"{update.message.document.file_unique_id}.pdf"
    file = await context.bot.get_file(update.message.document)
    await file.download_to_drive(file_path)
    text_array = []
    try:
        reader = PdfReader(file_path)
        for page in reader.pages:
            t = page.extract_text()
            if t: text_array.append(t)
    except Exception as e:
        print(f"PDF Error: {e}")
    await context.bot.send_chat_action(chat_id=chat_id, action="TYPING")
    loop = asyncio.get_running_loop()
    summary = await loop.run_in_executor(None, summarize, text_array)
    await update.message.reply_text(summary, reply_markup=get_inline_keyboard_buttons())
    if os.path.exists(file_path): os.remove(file_path)


async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "explore_similar":
        clean_text = query.message.text.replace("📱 **Результат из Web App:**", "")
        clean_text = clean_text.replace("🎤 **Саммари аудио:**", "")
        prompt = f"{clean_text}\nGive 3 search keywords."
        keywords = call_gemini_api(prompt)
        results = await search_results(keywords)
        links = "\n".join([f"{r['title']} - {r['href']}" for r in results]) if results else "Ничего не найдено"
        await query.message.reply_text(links)


def process_user_input(user_input):
    if re.match(r"https?://(www\.|m\.)?(youtube\.com|youtu\.be)/", user_input):
        return retrieve_yt_transcript_from_url(user_input)
    elif re.match(r"https?://", user_input):
        return scrape_text_from_url(user_input)
    return split_user_input(user_input)


def get_inline_keyboard_buttons():
    return InlineKeyboardMarkup([[InlineKeyboardButton("Explore Similar", callback_data="explore_similar")]])


def main():
    # list_available_models()
    app = ApplicationBuilder().token(telegram_token).build()

    app.add_handler(CommandHandler('start', handle_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_summarize))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_file))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))

    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_audio_message))

    app.add_handler(CallbackQueryHandler(handle_button_click))

    print("Bot is polling...")
    app.run_polling()


if __name__ == '__main__':
    main()