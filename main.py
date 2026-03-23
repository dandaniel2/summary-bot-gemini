import asyncio
import os
import re
import time
import urllib.parse
import requests
import trafilatura
from datetime import datetime
from google import genai
from google.genai import types
from PyPDF2 import PdfReader
from tqdm import tqdm
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, MessageHandler, CallbackQueryHandler, filters, ApplicationBuilder, ContextTypes
from youtube_transcript_api import YouTubeTranscriptApi

# --- CONFIGURATION ---
telegram_token = os.environ.get("TELEGRAM_TOKEN", "xxx")
model_name = os.environ.get("LLM_MODEL", "gemini-flash-latest") 
lang = os.environ.get("TS_LANG", "Russian") 
chunk_size = int(os.environ.get("CHUNK_SIZE", 100000))
allowed_users = os.environ.get("ALLOWED_USERS", "")
google_api_key = os.environ.get("GOOGLE_API_KEY", "")
google_cse_id = os.environ.get("GOOGLE_CSE_ID", "")

client = None
if google_api_key:
    client = genai.Client(api_key=google_api_key)

# --- HELPER FUNCTIONS ---

def print_available_models():
    if not client: return
    print("\n🔍 CHECKING AVAILABLE MODELS...")
    try:
        count = 0
        for m in client.models.list():
            if ("gemini" in m.name or "gemma" in m.name) and "vision" not in m.name:
                print(f" • {m.name}")
                count += 1
        print(f"✅ Total: {count}\n👉 Selected: {model_name}\n")
    except Exception as e:
        print(f"❌ Error listing models: {e}")

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

# --- ПОИСК ЧЕРЕЗ GOOGLE API ---
async def search_results(keywords):
    if not google_cse_id:
        print("❌ Ошибка: Не задан GOOGLE_CSE_ID")
        return []
    
    print(f"🔎 Google Searching: {keywords}")
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        'key': google_api_key,
        'cx': google_cse_id,
        'q': keywords,
        'num': 3
    }
    
    try:
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, lambda: requests.get(url, params=params))
        data = response.json()
        
        if 'error' in data:
            err_msg = data['error']['message']
            print(f"⚠️ Google API Error: {err_msg}")
            return []
            
        results = []
        if 'items' in data:
            for item in data['items']:
                results.append({
                    'title': item.get('title'),
                    'href': item.get('link')
                })
        return results
        
    except Exception as e:
        print(f"Search Request Failed: {e}")
        return []

# --- GENERATION ---

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
        if chunk: chunks.append(chunk.strip())
        return chunks

    try:
        if isinstance(text_array, list) and len(text_array) == 1 and len(text_array[0]) < chunk_size:
            text_chunks = text_array
        else:
            flat_text = "\n".join(text_array)
            if len(flat_text) < chunk_size: text_chunks = [flat_text]
            else: text_chunks = create_chunks(text_array)

        summaries = []
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        system_instruction = (
            f"You are an expert content analyst. Respond in {lang}. "
            f"Current date and time: {current_time}. "
            "Analyze the content and provide the appropriate output based on its type (educational, news, or other): "
            "- Educational/lecture: extract ALL specific rules, definitions, formulas, exceptions, and examples as a structured numbered list. Do NOT summarize or describe what the lecture is about. "
            "- News: provide a concise factual summary covering who, what, when, where, why. "
            "- Other: provide a clear, concise summary of the main points. "
            "IMPORTANT: Write in PLAIN TEXT ONLY. Do NOT use Markdown formatting. "
            "Do NOT use bold (**), italics (*), headers (#), or links []. "
            "Do NOT use LaTeX or dollar signs ($). "
            "Do NOT start your response with introductory labels like 'Type of content:', 'Summary:', or 'Краткое описание основного содержания:'."
        )
        for i, chunk in enumerate(tqdm(text_chunks, desc="Summarizing")):
            if not chunk.strip(): continue
            prompt = (
                f"Analyze the following content. First identify its type (educational, news, or other), "
                f"then provide the appropriate structured output as instructed:\n{chunk}"
            )
            result = call_gemini_with_retry(prompt, system_instruction)
            if result: summaries.append(result)
            if i < len(text_chunks) - 1: time.sleep(2)

        if not summaries: return "Ошибка: пустой ответ."
        if len(summaries) == 1: return summaries[0]
        
        summary = ' '.join(summaries)
        final_prompt = f"Combine these points into a final summary in {lang}:\n{summary}"
        return call_gemini_with_retry(final_prompt, system_instruction)

    except Exception as e:
        print(f"Summarize Error: {e}")
        return f"Error: {e}"

def analyze_media(file_bytes, mime_type, prompt_text="Summarize this."):
    if not client: return "API Key Error"

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    system_instruction = (
        f"You are an expert content analyst. Analyze the provided media. Respond in {lang}. "
        f"Current date and time: {current_time}. "
        "Analyze the content and provide the appropriate output based on its type (educational, news, or other): "
        "- Educational/lecture: extract ALL specific rules, definitions, formulas, exceptions, and examples as a structured numbered list. Do NOT summarize or describe what the lecture is about. "
        "- News: provide a concise factual summary covering who, what, when, where, why. "
        "- Other: provide a clear, concise summary of the main points. "
        "IMPORTANT: Write in PLAIN TEXT ONLY. Do NOT use Markdown formatting. "
        "Do NOT use bold (**), italics (*), headers (#), or links []. "
        "Do NOT use LaTeX or dollar signs ($). "
        "Do NOT start your response with introductory labels like 'Type of content:', 'Summary:', or 'Краткое описание основного содержания:'."
    )
    try:
        config = types.GenerateContentConfig(system_instruction=system_instruction, temperature=0.3)
        response = client.models.generate_content(
            model=model_name,
            contents=[types.Part.from_bytes(data=file_bytes, mime_type=mime_type), prompt_text],
            config=config
        )
        if response.text: return response.text.strip()
        return "Модель вернула пустой ответ."
    except Exception as e:
        if "429" in str(e): return "Превышены лимиты API (429)."
        print(f"Media Error: {e}")
        return f"Ошибка обработки медиа: {e}"

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
        config = types.GenerateContentConfig(system_instruction=system_instruction, temperature=0.3)
        response = client.models.generate_content(
            model=model_name, contents=prompt, config=config
        )
        if response.text: return response.text.strip()
        return ""
    except Exception as e:
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e): return "429"
        print(f"Gemini API Error: {e}")
        return ""

# --- YOUTUBE & FILES ---

def extract_youtube_transcript(youtube_url):
    try:
        video_id_match = re.search(r"(?<=v=)[^&]+|(?<=youtu.be/)[^?|\n]+", youtube_url)
        video_id = video_id_match.group(0) if video_id_match else None
        if video_id is None: return "no transcript"
        
        api = YouTubeTranscriptApi()
        
        try:
            snippet = api.fetch(video_id, languages=['ru'])
            if hasattr(snippet, 'to_raw_data'):
                raw_data = snippet.to_raw_data()
                transcript_text = ' '.join([item['text'] for item in raw_data])
                print(f"Debug - Got Russian transcript via to_raw_data, length: {len(transcript_text)}")
                return transcript_text
            elif hasattr(snippet, 'snippets'):
                transcript_text = ' '.join([item['text'] for item in snippet.snippets])
                print(f"Debug - Got Russian transcript via snippets, length: {len(transcript_text)}")
                return transcript_text
        except Exception as e1:
            print(f"Debug - Russian fetch: {type(e1).__name__}: {str(e1)[:50]}")
        
        try:
            snippet = api.fetch(video_id, languages=['en'])
            if hasattr(snippet, 'to_raw_data'):
                raw_data = snippet.to_raw_data()
                transcript_text = ' '.join([item['text'] for item in raw_data])
                print(f"Debug - Got English transcript via to_raw_data, length: {len(transcript_text)}")
                return transcript_text
            elif hasattr(snippet, 'snippets'):
                transcript_text = ' '.join([item['text'] for item in snippet.snippets])
                print(f"Debug - Got English transcript via snippets, length: {len(transcript_text)}")
                return transcript_text
        except Exception as e2:
            print(f"Debug - English fetch: {type(e2).__name__}")
        
        try:
            snippet = api.fetch(video_id)
            if hasattr(snippet, 'to_raw_data'):
                raw_data = snippet.to_raw_data()
                transcript_text = ' '.join([item['text'] for item in raw_data])
                print(f"Debug - Got default transcript via to_raw_data, length: {len(transcript_text)}")
                return transcript_text
            elif hasattr(snippet, 'snippets'):
                transcript_text = ' '.join([item['text'] for item in snippet.snippets])
                print(f"Debug - Got default transcript via snippets, length: {len(transcript_text)}")
                return transcript_text
        except Exception as e3:
            print(f"Debug - Default fetch: {type(e3).__name__}")
        
        print("Debug - Could not find any transcript")
        return "no transcript"
            
    except Exception as e:
        print(f"Error transcript: {e}")
        return "no transcript"

def retrieve_yt_transcript_from_url(youtube_url):
    output = extract_youtube_transcript(youtube_url)
    if output == 'no transcript': raise ValueError("No transcript found.")
    return [output]

# --- HANDLERS ---

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (f"Привет! Я использую модель {model_name}.\n\n"
           "Я умею анализировать:\nТекст и ссылки\nYouTube\nPDF\nФото\nАудио\nВидео\n\n"
           "Кидай что угодно!")
    await update.message.reply_text(msg)

async def handle_summarize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if allowed_users and str(chat_id) not in allowed_users.split(','):
        await update.message.reply_text("Access denied.")
        return
    await process_request(update.message.text, chat_id, update, context)

async def handle_media_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if allowed_users and str(chat_id) not in allowed_users.split(','):
        await update.message.reply_text("Access denied.")
        return
    message = update.message
    file_obj = None
    mime_type = ""
    prompt = f"Summarize this. Respond in {lang}."
    action = "TYPING"

    if message.photo:
        file_obj = message.photo[-1]
        mime_type = "image/jpeg"
        prompt = f"Analyze this image. If it contains educational or lecture material, extract all specific rules, definitions, formulas, exceptions, and examples. Present them as a structured list. If it is not educational material, describe what is shown. Respond in {lang}."
        action = "UPLOAD_PHOTO"
        await update.message.reply_text("Анализирую фото...")
    elif message.voice:
        file_obj = message.voice
        mime_type = "audio/ogg"
        prompt = (f"Listen to this audio. Analyze its content (educational lecture, news, or other). "
                  f"For educational content list all rules, definitions, formulas, and examples. "
                  f"For news give a concise factual summary. ONLY output the final text. Do NOT output the content type or introductory phrases. Respond in {lang}.")
        action = "UPLOAD_VOICE"
        await update.message.reply_text("Слушаю...")
    elif message.audio:
        file_obj = message.audio
        mime_type = file_obj.mime_type or "audio/mpeg"
        prompt = (f"Listen to this audio. Analyze its content (educational lecture, news, or other). "
                  f"For educational content list all rules, definitions, formulas, and examples. "
                  f"For news give a concise factual summary. ONLY output the final text. Do NOT output the content type or introductory phrases. Respond in {lang}.")
        action = "UPLOAD_VOICE"
        await update.message.reply_text("Анализирую аудио...")
    elif message.video:
        file_obj = message.video
        mime_type = file_obj.mime_type or "video/mp4"
        prompt = (f"Watch this video. Analyze its content (educational lecture, news or other). "
                  f"For educational: list all rules, definitions, formulas, and examples. "
                  f"For news: concise factual summary. For other: describe what is shown. "
                  f"ONLY output the final text. Do NOT output the content type or introductory phrases. Respond in {lang}.")
        action = "UPLOAD_VIDEO"
        await update.message.reply_text("Анализирую видео...")
    elif message.video_note:
        file_obj = message.video_note
        mime_type = "video/mp4"
        prompt = f"Watch this video note and describe or summarize its content. Respond in {lang}."
        action = "UPLOAD_VIDEO"
        await update.message.reply_text("Анализирую видео-сообщение...")

    if not file_obj: return
    if file_obj.file_size > 20 * 1024 * 1024:
        await update.message.reply_text("⚠️ Файл >20MB.")
        return

    await context.bot.send_chat_action(chat_id=chat_id, action=action)
    try:
        new_file = await context.bot.get_file(file_obj.file_id)
        file_bytes = await new_file.download_as_bytearray()
        loop = asyncio.get_running_loop()
        summary = await loop.run_in_executor(None, analyze_media, file_bytes, mime_type, prompt)
        await update.message.reply_text(f"{summary}", reply_markup=get_inline_keyboard_buttons())
    except Exception as e:
        print(f"Media Error: {e}")
        await update.message.reply_text(f"Ошибка: {e}")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    doc = update.message.document
    if doc.mime_type == 'application/pdf':
        await context.bot.send_chat_action(chat_id=chat_id, action="TYPING")
        await update.message.reply_text("Читаю PDF...")
        file_path = f"/tmp/{doc.file_unique_id}.pdf"
        try:
            file = await context.bot.get_file(doc)
            await file.download_to_drive(file_path)
            text_array = []
            reader = PdfReader(file_path)
            for page in reader.pages:
                t = page.extract_text()
                if t: text_array.append(t)
            loop = asyncio.get_running_loop()
            summary = await loop.run_in_executor(None, summarize, text_array)
            await update.message.reply_text(f"**PDF Summary:**\n\n{summary}", reply_markup=get_inline_keyboard_buttons())
        except Exception as e:
            print(f"PDF Error: {e}")
            await update.message.reply_text(f"Ошибка PDF: {e}")
        finally:
            if os.path.exists(file_path): os.remove(file_path)
    elif "image" in doc.mime_type or "audio" in doc.mime_type:
        await update.message.reply_text("Отправьте как Фото/Аудио, а не как Файл.")
    elif "video" in doc.mime_type:
        # await update.message.reply_text("Видео-файл получен как документ.")
        await context.bot.send_chat_action(chat_id=chat_id, action="UPLOAD_VIDEO")
        try:
            file_size = doc.file_size or 0
            if file_size > 20 * 1024 * 1024:
                await update.message.reply_text("⚠️ Файл >20MB.")
                return
            new_file = await context.bot.get_file(doc)
            file_bytes = await new_file.download_as_bytearray()
            mime_type = doc.mime_type or "video/mp4"
            prompt = (f"Watch this video. Analyze its content (educational lecture, news or other). "
                      f"For educational: list all rules, definitions, formulas, and examples. "
                      f"For news: concise factual summary. For other: describe what is shown. "
                      f"ONLY output the final text. Do NOT output the content type or introductory phrases. Respond in {lang}.")
            loop = asyncio.get_running_loop()
            summary = await loop.run_in_executor(None, analyze_media, file_bytes, mime_type, prompt)
            await update.message.reply_text(f"{summary}", reply_markup=get_inline_keyboard_buttons())
        except Exception as e:
            print(f"Video Doc Error: {e}")
            await update.message.reply_text(f"Ошибка видео: {e}")
    else:
        await update.message.reply_text(f"Не поддерживаю {doc.mime_type}.")

async def process_request(user_input, chat_id, update, context):
    if len(user_input.strip()) < 30 and not re.match(r"https?://", user_input.strip()):
        await context.bot.send_message(chat_id=chat_id, text="Текст слишком короткий (минимум 30 символов).")
        return

    try:
        text_array = process_user_input(user_input)
        if not text_array:
            msg = "Пустой ввод."
            await context.bot.send_message(chat_id=chat_id, text=msg)
            return
        await context.bot.send_chat_action(chat_id=chat_id, action="TYPING")
        loop = asyncio.get_running_loop()
        summary = await loop.run_in_executor(None, summarize, text_array)
        await context.bot.send_message(chat_id=chat_id, text=f"{summary}", reply_markup=get_inline_keyboard_buttons())
    except Exception as e:
        print(f"Processing Error: {e}")
        await context.bot.send_message(chat_id=chat_id, text=f"Ошибка: {e}")

async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "explore_similar":
        clean_text = query.message.text
        for garbage in ["Результат из Web App:", "Результат:", "PDF Summary:", "Саммари аудио:"]:
            clean_text = clean_text.replace(garbage, "")
        
        prompt = (f"{clean_text}\n"
                  "Generate a SINGLE search query string for Google. "
                  "Return ONLY the keywords separated by spaces. NO quotes.")
        
        keywords = call_gemini_api(prompt).replace('"', '').strip()
        
        results = await search_results(keywords)
        
        if results:
            links = "\n".join([f"{r['title']} - {r['href']}" for r in results])
            await query.message.reply_text(links, disable_web_page_preview=True)
        else:
            encoded = urllib.parse.quote(keywords)
            await query.message.reply_text(
                f"**Авто-поиск недоступен.**\n[Google: {keywords}](https://www.google.com/search?q={encoded})",
                parse_mode="Markdown"
            )

def process_user_input(user_input):
    if re.match(r"https?://(www\.|m\.)?(youtube\.com|youtu\.be)/", user_input):
        return retrieve_yt_transcript_from_url(user_input)
    elif re.match(r"https?://", user_input):
        return scrape_text_from_url(user_input)
    return split_user_input(user_input)

def get_inline_keyboard_buttons():
    return InlineKeyboardMarkup([[InlineKeyboardButton("Explore Similar", callback_data="explore_similar")]])

def main():
    print_available_models()
    app = ApplicationBuilder().token(telegram_token).build()
    app.add_handler(CommandHandler('start', handle_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_summarize))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VOICE | filters.AUDIO | filters.VIDEO | filters.VIDEO_NOTE, handle_media_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CallbackQueryHandler(handle_button_click))
    print("Bot is polling...")
    app.run_polling()

if __name__ == '__main__':
    main()