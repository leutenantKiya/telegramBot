from openai import AsyncOpenAI
import asyncio
import os
import json
import requests
import io
import re
from urllib.parse import urljoin, unquote
from bs4 import BeautifulSoup as bs
# https://medium.com/@hitorunajp/asynchronous-context-managers-f1c33d38c9e3
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from handle_db import (
    save_user,
    getName,
    saveChatLog,
    validate_user,
    save_eclass_credentials,
    get_eclass_credentials,
    save_materi_cache,
    get_materi_cache,
    init_db,
    CredentialStorageError
)
from config import Config
from routes import login_bp, matakuliah_bp, presensi_bp, materi_bp
from routes.login import login as eclass_login
from routes.matakuliah import get_matakuliah
from routes.materi import get_materi
from routes.presensi import presensi as submit_presensi


from fastapi import FastAPI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    ApplicationBuilder, 
    MessageHandler, 
    CommandHandler, 
    CallbackQueryHandler,
    filters, 
    ContextTypes, 
    ConversationHandler
)

import socket
import sys

# Force IPv4 ONLY on Windows to prevent httpx.ConnectError on broken IPv6 networks
# On Linux/Docker (HF Spaces), IPv6 works fine and this patch causes ConnectTimeout
if sys.platform == 'win32':
    old_getaddrinfo = socket.getaddrinfo
    def new_getaddrinfo(*args, **kwargs):
        responses = old_getaddrinfo(*args, **kwargs)
        return [response for response in responses if response[0] == socket.AF_INET]
    socket.getaddrinfo = new_getaddrinfo

load_dotenv()

GET_NAME = 0
GET_LOGIN = 1
client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPEN_ROUTER_KEY"),
    timeout=60.0,
    max_retries=2,
)
# Store user sessions
user_sessions = {}

def get_user_id(update: Update):
    return str(update.effective_user.id)

def get_telegram_api_urls():
    proxy_url = (os.getenv("TELEGRAM_PROXY_URL") or "").strip().rstrip("/")
    if not proxy_url:
        return None, None

    proxy_url = re.sub(r"/(?:file/)?bot$", "", proxy_url)
    return f"{proxy_url}/bot", f"{proxy_url}/file/bot"

# set session
def set_eclass_session(user_id, id_user, cookies):
    user_sessions[user_id] = {
        'cookies': cookies,
        'user_id': id_user
    }
    return cookies

# get cookie and create session
def login_with_eclass_credentials(user_id, id_user, password):
    data = eclass_login({
        "id": id_user,
        "password": password
    })

    if isinstance(data, dict) and data.get('success'):
        response_data = data.get('data', {})
        cookies = response_data.get('cookies', {})
        set_eclass_session(user_id, id_user, cookies)
        return cookies, None

    error_msg = data.get('error', 'Login failed') if isinstance(data, dict) else 'Login failed'
    return None, error_msg

# try find user if they have ever login
async def get_or_restore_eclass_cookies(user_id, reply_target=None, force=False):
    # try to find if session still valid
    session = user_sessions.get(user_id, {})
    if session.get('cookies') and not force:
        return session['cookies']
    if force:
        user_sessions.pop(user_id, None)

    try:
        credentials = get_eclass_credentials(user_id)
    except CredentialStorageError as e:
        print(f"E-class credential storage unavailable: {e}")
        credentials = None

    if not credentials:
        if reply_target:
            await reply_target.reply_text("Juragan, panjenengan dereng login. Monggo /login rumiyin nggih.")
        return None

    cookies, error_msg = login_with_eclass_credentials(
        user_id,
        credentials["id"],
        credentials["password"]
    )
    if cookies:
        return cookies

    if reply_target:
        await reply_target.reply_text(f"Login otomatis gagal: {error_msg}. Monggo /login malih nggih.")
    return None

# handle if session error occur
def is_eclass_session_error(message):
    text = str(message or "").lower()
    return any(term in text for term in ["sesi login", "kadaluarsa", "invalid cookie", "invalid cookies"])

def get_content_disposition_filename(content_disposition):
    if not content_disposition:
        return None

    match = re.search(r"filename\*=([^;]+)", content_disposition, re.IGNORECASE)
    if match:
        value = match.group(1).strip().strip('"')
        if "''" in value:
            value = value.split("''", 1)[1]
        return unquote(value).strip()

    match = re.search(r'filename="?([^";]+)"?', content_disposition, re.IGNORECASE)
    return match.group(1).strip() if match else None

def guess_materi_filename(link, title, content_type, content_disposition):
    filename = get_content_disposition_filename(content_disposition)
    if not filename:
        url_name = link.rstrip("/").split("/")[-1]
        filename = url_name if "." in url_name else title

    filename = re.sub(r'[\\/*?:"<>|]', "", filename).strip() or "materi"
    if "." in filename:
        return filename

    content_type = (content_type or "").lower()
    if "pdf" in content_type:
        return filename + ".pdf"
    if "word" in content_type or "wordprocessingml" in content_type:
        return filename + ".docx"
    if "powerpoint" in content_type or "presentationml" in content_type:
        return filename + ".pptx"
    if "excel" in content_type or "spreadsheetml" in content_type:
        return filename + ".xlsx"
    if "zip" in content_type:
        return filename + ".zip"
    return filename + ".bin"

def is_html_download_response(response):
    content_type = response.headers.get("content-type", "").lower()
    if "text/html" in content_type:
        return True
    prefix = response.content[:300].lstrip().lower()
    return prefix.startswith(b"<!doctype html") or prefix.startswith(b"<html")

def get_download_attempt_summary(attempts):
    if not attempts:
        return "no attempts"
    parts = []
    for attempt in attempts[-6:]:
        parts.append(
            f"{attempt['method']} {attempt['status']} {attempt['content_type'] or '-'} {attempt['size']}B"
        )
    return " | ".join(parts)

def extract_download_links_from_html(html, base_url):
    soup = bs(html or "", "html.parser")
    candidates = []
    for tag in soup.find_all(["a", "iframe", "embed"], href=True):
        candidates.append(tag.get("href"))
    for tag in soup.find_all(["iframe", "embed", "source"], src=True):
        candidates.append(tag.get("src"))
    candidates.extend(re.findall(r"""(?:href|src)\s*=\s*["']([^"']+)["']""", html or "", re.IGNORECASE))
    candidates.extend(re.findall(r"""(?:window\.location(?:\.href)?|location\.href)\s*=\s*["']([^"']+)["']""", html or "", re.IGNORECASE))

    filtered = []
    for candidate in candidates:
        if not candidate:
            continue
        candidate = candidate.strip()
        lowered = candidate.lower()
        if lowered.startswith("#") or "javascript:" in lowered or "cdn-cgi" in lowered:
            continue
        if any(term in lowered for term in ["download", "materi", "file", "lampiran"]):
            full_candidate = urljoin(base_url, candidate)
            if full_candidate not in filtered:
                filtered.append(full_candidate)
    return filtered

def request_download_url(session, url, headers, attempts):
    # Coba GET dulu (sesuai browser behavior), hanya fallback ke POST jika GET gagal
    for method in ("GET", "POST"):
        print(f"  [download] {method} {url}")
        response = getattr(session, method.lower())(
            url,
            headers=headers,
            timeout=120,
            allow_redirects=True,
            stream=False
        )
        attempts.append({
            "method": method,
            "url": response.url,
            "status": response.status_code,
            "content_type": response.headers.get("content-type", ""),
            "size": len(response.content)
        })
        print(f"  [download] -> {response.status_code} {response.headers.get('content-type', '')} {len(response.content)}B")
        if response.ok and response.content and not is_html_download_response(response):
            return response
    return response

def download_eclass_file_sync(link, cookies, title, referer=None, alt_links=None):
    if not link:
        raise ValueError("Link materi kosong")

    cookies_dict = cookies if isinstance(cookies, dict) else {"ukdw_session": cookies}
    session = Config.create_session()
    session.cookies.update(cookies_dict)

    full_link = urljoin(Config.BASE_URL + "/", link)
    full_referer = urljoin(Config.BASE_URL + "/", referer) if referer else Config.MATERI_URL

    # Headers lengkap yang menyerupai browser asli (dari network intercept)
    # Tanpa header ini, Cloudflare / eclass bisa menolak request
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": full_referer,
        "Origin": Config.BASE_URL,
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-User": "?1",
        "Sec-Fetch-Dest": "document",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Ch-Ua": '"Not-A.Brand";v="24", "Chromium";v="146"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
    }
    attempts = []

    # Visit the referer page first to establish session context (like a browser would)
    if referer:
        session.get(full_referer, headers=headers, timeout=60, allow_redirects=True)

    response = request_download_url(session, full_link, headers, attempts)
    candidate_links = [urljoin(Config.BASE_URL + "/", candidate) for candidate in (alt_links or [])]

    if is_html_download_response(response):
        candidate_links.extend(extract_download_links_from_html(response.text, response.url))

    seen_links = {full_link}
    for candidate_link in candidate_links:
        if not candidate_link or candidate_link in seen_links:
            continue
        seen_links.add(candidate_link)
        candidate_headers = headers | {"Referer": response.url or full_referer}
        candidate_response = request_download_url(session, candidate_link, candidate_headers, attempts)
        if candidate_response.ok and candidate_response.content and not is_html_download_response(candidate_response):
            response = candidate_response
            break

    if not response.ok:
        raise RuntimeError(f"Download failed. Attempts: {get_download_attempt_summary(attempts)}")
    if is_html_download_response(response):
        preview = response.text[:300].replace("\n", " ").strip()
        if "login" in response.url.lower() or "do_login" in response.text.lower():
            raise RuntimeError("Sesi login e-class sampun kadaluarsa. Monggo /login malih.")
        raise RuntimeError(f"Server returned HTML instead of file. Attempts: {get_download_attempt_summary(attempts)} Preview: {preview}")
    if not response.content:
        raise RuntimeError(f"File kosong saking server. Attempts: {get_download_attempt_summary(attempts)}")

    filename = guess_materi_filename(
        full_link,
        title,
        response.headers.get("content-type", ""),
        response.headers.get("content-disposition", "")
    )
    return filename, response.content

# format matkul
def format_matakuliah_text(courses, count=None):
    if not courses:
        return "No matakuliah found."

    count = count if count is not None else len(courses)
    result_text = f"Your Matakuliah List ({count} courses)\n\n"

    for course in courses:
        if not isinstance(course, dict):
            result_text += f"- {course}\n\n"
            continue

        matkul = course.get('matkul') or course.get('nama') or 'N/A'
        course_id = course.get('id') or course.get('kode') or 'N/A'
        sks = course.get('sks', 'N/A')
        kelas = course.get('kelas', 'N/A')
        ruang = course.get('ruang', 'N/A')
        jadwal = course.get('jadwal')
        pengampu = course.get('pengampu')

        result_text += f"- {matkul}\n"
        result_text += f"  Code: {course_id} | SKS: {sks} | Kelas: {kelas}\n"
        result_text += f"  Ruang: {ruang}\n"

        if jadwal:
            if isinstance(jadwal, list):
                jadwal = ", ".join(jadwal)
            result_text += f"  Jadwal: {jadwal}\n"

        if pengampu:
            if isinstance(pengampu, list):
                pengampu = ", ".join(pengampu)
            result_text += f"  Pengampu: {pengampu}\n"

        result_text += "\n"

    return result_text


def parse_matakuliah_response(data):
    if isinstance(data, str):
        # data = '[{"json": {"success": true, "data": [{"nama": "PBO", "kelas": "TI0082"}]}}]'
        stripped_data = data.strip()
        if not stripped_data:
            return None, "Response matakuliah kosong."
        if stripped_data.startswith("{") or stripped_data.startswith("["):
            print(data)
            try:
                # ata = [{"json": {"success": True, "data": [{"nama": "PBO", "kelas": "TI0082"}]}}]
                return parse_matakuliah_response(json.loads(stripped_data))
            except json.JSONDecodeError:
                pass
        return data, None

    if isinstance(data, list):
        print(data)
        if not data:
            return "No matakuliah found.", None
        if all(isinstance(item, dict) and 'json' in item for item in data):
            json_items = [item['json'] for item in data]
            if len(json_items) == 1:
                return parse_matakuliah_response(json_items[0])
            return parse_matakuliah_response(json_items)
        first_item = data[0]
        if isinstance(first_item, dict) and 'json' in first_item:
            return parse_matakuliah_response(first_item['json'])
        wrapper_keys = {'text', 'message', 'reply', 'success', 'body', 'data', 'error'}
        if len(data) == 1 and isinstance(first_item, dict) and wrapper_keys.intersection(first_item):
            return parse_matakuliah_response(first_item)
        return format_matakuliah_text(data), None

    if not isinstance(data, dict):
        return None, "Unexpected response format from matakuliah service."

    for key in ('text', 'message', 'reply'):
        if data.get(key):
            return str(data[key]), None

    if data.get('success') is False:
        return None, data.get('error') or data.get('message') or 'Failed to fetch matakuliah'

    json_payload = data.get('json')
    if isinstance(json_payload, (dict, list, str)):
        return parse_matakuliah_response(json_payload)

    body = data.get('body')
    if isinstance(body, (dict, list, str)):
        return parse_matakuliah_response(body)

    courses = data.get('matakuliah')
    if courses is None:
        courses = data.get('courses')
    if isinstance(courses, list):
        return format_matakuliah_text(courses, data.get('count') or data.get('total')), None

    payload = data.get('data')
    if isinstance(payload, list):
        return format_matakuliah_text(payload, data.get('total') or data.get('count')), None
    if isinstance(payload, (dict, str)):
        return parse_matakuliah_response(payload)

    return None, "Unexpected response format from matakuliah service."

def request_matakuliah(cookies):
    data = get_matakuliah({"cookies": cookies})
    return data.get("success", False), data

async def reply_text(update: Update, text):
    if len(text) > 4000:
        for i in range(0, len(text), 4000):
            await update.message.reply_text(text[i:i+4000])
    else:
        await update.message.reply_text(text)

def instruction(user_name):
    displayed_name = user_name if user_name else "Juragan"
    return f"""
    Sampeyan adalah asisten virtual berjiwa Jawa tulen yang sangat sopan (andhap asor) dan ramah.
    Berbicaralah selayaknya orang Jawa yang sangat sopan (menggunakan bahasa Indonesia dengan logat medok, diselingi kosa kata bahasa Jawa Krama Inggil/Alus untuk menunjukkan rasa hormat).
    Sebut diri sampeyan 'Kulo' atau 'Dalem', dan panggil user dengan sebutan '{displayed_name}', 'Mas', 'Mbak', atau 'Juragan'.

    PENTING:
    Nama user adalah {displayed_name}. Nalika user takon nganggo bahasa indonesia, bales nganggo bahasa indonesia.
    Jika ditanya tentang apapun, jawablah dengan pengetahuan yang sampeyan miliki. Jangan membatasi diri.
    Sampeyan memiliki pengetahuan luas tentang dunia modern, termasuk software engineering, programming (Python, MQTT, dll), dan teknologi.
    JANGAN menolak untuk menjawab pertanyaan tentang teknologi modern. Sebaliknya, jelaskan dengan perumpamaan kearifan lokal Jawa jika cocok, tetapi SELALU berikan jawaban teknis yang paling tepat dan akurat.
    """

async def login_eclass(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = get_user_id(update)
    try:
        credentials = get_eclass_credentials(user_id)
    except CredentialStorageError as e:
        print(f"E-class credential storage unavailable: {e}")
        credentials = None

    if credentials:
        cookies, error_msg = login_with_eclass_credentials(
            user_id,
            credentials["id"],
            credentials["password"]
        )
        if cookies:
            await update.message.reply_text(f"✅ Alhamdulillah, kulo sampun login otomatis. Sugeng rawuh, Juragan {credentials['id']}!")
            return ConversationHandler.END
        await update.message.reply_text(f"Login otomatis gagal: {error_msg}. Monggo input ulang NIM kalian Password.")

    await update.message.reply_text("Nyuwun sewu Juragan, monggo masukaken NIM kalian Password dipisah spasi.\nConto: 71241119 password123")
    return GET_LOGIN

async def save_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text
    user_id = get_user_id(update)
    
    try:
        user_data = user_input.split()
        if len(user_data) < 2:
            await update.message.reply_text("Format boten leres, Juragan. Conto: 71241119 password123")
            return GET_LOGIN
            
        id_user = str(user_data[0])
        password = str(user_data[1])
        
        cookies, error_msg = login_with_eclass_credentials(user_id, id_user, password)
        
        if cookies:
            try:
                save_eclass_credentials(user_id, id_user, password)
                await update.message.reply_text(f"✅ Alhamdulillah, sampun saged login. Data e-class sampun kulo simpen aman, Juragan {id_user}.")
            except CredentialStorageError as e:
                print(f"E-class credential storage unavailable: {e}")
                await update.message.reply_text(f"✅ Alhamdulillah, sampun saged login. Auto-login dereng aktif amargi konfigurasi enkripsi dereng siap.")
            except Exception as e:
                print(f"Failed to save e-class credentials: {e}")
                await update.message.reply_text(f"✅ Alhamdulillah, sampun saged login. Nanging data e-class dereng kasimpen.")
        else:
            await update.message.reply_text(f"❌ Login gagal: {error_msg}")
            
        return ConversationHandler.END
    except Exception as e:
        print(e)
        await update.message.reply_text("❌ Login gagal. Monggo dipun cek koneksi panjenengan nggih.")
        return ConversationHandler.END

async def matakuliah_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = get_user_id(update)

    if not validate_user(user_id):
        await update.message.reply_text(
            "Nyuwun pangapunten, panjenengan dereng terdaftar.\nMonggo /start rumiyin kangge mendaftar."
        )
        return

    cookies = await get_or_restore_eclass_cookies(user_id, update.message)
    if not cookies:
        return
    
    await update.message.reply_text("Sabar nggih Juragan, kulo padosi daftar matakuliah panjenengan...")
    
    try:
        ok, data = request_matakuliah(cookies)
        result_text, error_msg = parse_matakuliah_response(data)
        if not ok and is_eclass_session_error(error_msg or result_text):
            cookies = await get_or_restore_eclass_cookies(user_id, update.message, force=True)
            if not cookies:
                return
            ok, data = request_matakuliah(cookies)
            result_text, error_msg = parse_matakuliah_response(data)

        if ok:
            if result_text:
                await reply_text(update, result_text)
            else:
                await update.message.reply_text(f"Wonten kesalahan: {error_msg or 'Response matakuliah kosong.'}")
        else:
            error_details = error_msg or result_text or 'Boten saged nyambung ke server.'
            await update.message.reply_text(f"Wonten kesalahan: {error_details[:1000]}")
            
    except Exception as e:
        print(f"Error fetching matakuliah: {e}")
        await update.message.reply_text("Wonten kesalahan pas mendapatkan matakuliah. Cobi malih nggih Juragan.")


async def materi_list(update: Update, context):
    user_id = get_user_id(update)
    cookies = await get_or_restore_eclass_cookies(user_id, update.message)
    if not cookies:
        return
    
    if not context.args:
        await update.message.reply_text("Nyuwun sewu, monggo masukaken ID kelas. Conto: /materi TI0082")
        return
        
    id_kelas = context.args[0]
    
    await update.message.reply_text(f"Sabar nggih Juragan, kulo padosi materi kelas {id_kelas}...")
    
    try:
        data = get_materi(id_kelas, {"cookies": cookies})
        if isinstance(data, dict) and not data.get("success") and is_eclass_session_error(data.get("error")):
            cookies = await get_or_restore_eclass_cookies(user_id, update.message, force=True)
            if not cookies:
                return
            data = get_materi(id_kelas, {"cookies": cookies})
        
        if isinstance(data, dict) and data.get("success"):
            materi = data.get("data", [])
            if not materi:
                await update.message.reply_text("Nyuwun pangapunten, boten wonten materi ingkang ketemu.")
                return
                
            save_materi_cache(user_id, materi)
            keyboard = []
            print(materi)
            for i, m in enumerate(materi):
                file_type = m.get('type', '')
                print(file_type)
                is_dl = m.get('is_download', False)
                icon = "📄" if is_dl else "🔗"
                btn_text = f"{icon} {m['title']}"
                link = m.get("link")
                if len(btn_text) > 40:
                    btn_text = btn_text[:37] + "..."
                keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"dl_{i}")])
                
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"📚 Materi Kelas {id_kelas} ({len(materi)} item):\n"
                f"📄 = File (langsung terunduh)\n"
                f"🔗 = Link (dibukak di browser)\n\n"
                f"Monggo dipun pilih, Juragan:",
                reply_markup=reply_markup
            )
        else:
            error_msg = data.get('error', 'Unknown error') if isinstance(data, dict) else str(data)
            await update.message.reply_text(f"Gagal mendapatkan materi: {error_msg}")
    except Exception as e:
        await update.message.reply_text(f"Wonten kesalahan: {str(e)}")

async def handle_materi_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    print(f"[callback] >>> CALLBACK RECEIVED: data='{query.data}' from user={query.from_user.id}")
    await query.answer()
    user_id = str(query.from_user.id)
    
    if query.data.startswith("dl_"):
        try:
            index = int(query.data.split("_")[1])
        except ValueError:
            print(f"[callback] Invalid index in '{query.data}'")
            return
            
        print(f"[callback] looking for materi cache for user_id='{user_id}', index={index}")
        cached = get_materi_cache(user_id)
        if not cached or index >= len(cached):
            await query.message.reply_text("Sesi materi sampun kadaluarsa. Monggo panggil /materi malih nggih Juragan.")
            return
            
        m = cached[index]
        link = m['link']
        title = m['title']
        is_download = m.get('is_download', False)
        print(f"[callback] User {user_id} pressed dl_{index}: '{title}' is_download={is_download} link={link}")
        cookies = await get_or_restore_eclass_cookies(user_id, query.message)
        
        if not cookies:
            print(f"[callback] No cookies for user {user_id}, aborting")
            return
        
        # If it's a "Lihat" (view) link or external link, just send the URL
        if not is_download:
            await query.message.reply_text(
                f"🔗 *{title}*\n\n"
                f"Menika link materi, Juragan. Monggo langsung dipun klik:\n{link}",
                parse_mode="Markdown"
            )
            return
            
        await query.message.reply_text(f"Sabar nggih, kulo unduhaken: {title}...")
        
        try:
            import asyncio
            
            # Run blocking request in executor to prevent freezing the bot
            print(f"[callback] Starting download for '{title}'...")
            loop = asyncio.get_running_loop()
            filename, file_bytes = await loop.run_in_executor(
                None,
                lambda: download_eclass_file_sync(link, cookies, title, m.get("referer"), m.get("alt_links"))
            )
            print(f"[callback] Download complete: {filename} ({len(file_bytes)} bytes)")

            # Send as document via BytesIO
            file_obj = io.BytesIO(file_bytes)
            file_obj.name = filename
            
            print(f"[callback] Sending document to Telegram...")
            await query.message.reply_document(
                document=file_obj, 
                filename=filename,
                caption=f"📄 {title}\nUkuran: {len(file_bytes) / 1024:.1f} KB",
                read_timeout=120,
                write_timeout=120,
                connect_timeout=60
            )
            print(f"[callback] Document sent successfully!")
        except Exception as e:
            print(f"[callback] ERROR downloading/sending '{title}': {e}")
            import traceback
            traceback.print_exc()
            await query.message.reply_text(f"❌ Wonten masalah pas ngunduh: {e}")

async def handle_presensi(update: Update, context: ContextTypes.DEFAULT_TYPE, id_kelas: str):
    user_id = get_user_id(update)
    cookies = await get_or_restore_eclass_cookies(user_id, update.message)
    if not cookies:
        return

    await update.message.reply_text(f"Sabar nggih Juragan, kulo cobi presensiken kelas {id_kelas}...")
    
    try:
        data = submit_presensi(id_kelas, {"cookies": cookies})
        if isinstance(data, dict) and not data.get("success") and is_eclass_session_error(data.get("error")):
            cookies = await get_or_restore_eclass_cookies(user_id, update.message, force=True)
            if not cookies:
                return
            data = submit_presensi(id_kelas, {"cookies": cookies})
        
        if isinstance(data, dict) and data.get("success"):
            msg_data = data.get("data", {})
            msg = msg_data.get("message", "Presensi berhasil!")
            details = f"\nSesi: {msg_data.get('sessionTitle', '')}\nWaktu: {msg_data.get('sessionDate', '')} {msg_data.get('sessionTime', '')}"
            await update.message.reply_text(f"✅ {msg}{details}")
        else:
            error_msg = data.get('error', 'Unknown error') if isinstance(data, dict) else str(data)
            await update.message.reply_text(f"❌ Presensi gagal: {error_msg}")
    except Exception as e:
        await update.message.reply_text(f"Wonten kesalahan: {str(e)}")

async def start_naming(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Sugeng rawuh! Kulo asisten virtual panjenengan.\n\n"
        "Nyuwun sewu, asmane panjenengan sinten nggih? (Silakan masukkan nama Anda)"
    )
    await saveChatLog(get_user_id(update), "user started naming", "Bot")
    return GET_NAME

async def save_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = get_user_id(update)
    new_name = update.message.text
    await save_user(update, name=new_name)
    await update.message.reply_text(
        f"Inggih, siap Juragan {new_name}. Asma panjenengan sampun kulo catet.\n\n"
        "Wonten ingkang saged kulo bantu dinten menika?"
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Pendaftaran dibatalaken. Kulo tetep manggil panjenengan Juragan mawon nggih.")
    return ConversationHandler.END

async def author(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = [[
        InlineKeyboardButton("Instagram", url="https://www.instagram.com/gwkiyaco?igsh=MTQ2bnJ2cGJhY3A4Ng=="),
        InlineKeyboardButton("SmartEcoWave", url="https://smartecowave.fti.ukdw.ac.id/")
    ]]
    reply_markup = InlineKeyboardMarkup(key)
    reply_msg = """Nyuwun sewu Juragan, ingkang ngripta (membuat) kulo menika Mas Antonius Kiya Ananda Derron.
                   Mas Kiya menika mahasiswa Teknik Informatika saking Yogyakarta ingkang taksih kuliah.
                   Piyambake nggadhahi cita-cita dados ahli Software Development kalian AI. Salam kenal nggih!"""
    await update.message.reply_text(reply_msg, reply_markup=reply_markup)
    return ConversationHandler.END

async def user_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = get_user_id(update)
    name = getName(user_id)
    await update.message.reply_text(f"Sugeng dinten, Juragan {name}! Mugi-mugi tansah pinaringan berkah.")
    return ConversationHandler.END

async def describe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""
                                    Sugeng rahayu. Kulo niki bot asisten AI panjenengan.
                                    Kulo saged mbantu mangsuli pitakon nopo kemawon babagan teknologi, 
                                    pemrograman, utawi bab-bab sanesipun kanthi seneng ati.
                                    """)
    return ConversationHandler.END 

async def chat_with_bot(update, context, name, user_text):
    chat = await client.chat.completions.create(
            model="openai/gpt-oss-120b:free",
            messages=[
                {"role": "system", "content": instruction(name)},
                {"role": "user", "content": user_text}
            ],
            extra_body={"reasoning": {"enabled": True}}
        )
    return chat

async def handle_telegram_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = get_user_id(update)
    user_text = update.message.text
    
    if user_text.lower().startswith("masuk "):
        parts = user_text.split()
        if len(parts) > 1:
            id_kelas = parts[1]
            await handle_presensi(update, context, id_kelas)
            return

    name = getName(user_id)
    
    await save_user(update, name=None)
    await saveChatLog(user_id, user_text, "User")
    
    try:
        chat = await chat_with_bot(update, context, name, user_text)
        
        response = chat.choices[0].message.content
        
        await saveChatLog(user_id, response, "Bot")
        
        if len(response) > 4000:
            for i in range(0, len(response), 4000):
                await update.message.reply_text(response[i:i+4000])
        else:
            await update.message.reply_text(response)

    except Exception as e:
        print(f"Error in Bot logic: {e}")
        if "timed out" in str(e).lower():
            await update.message.reply_text("Nyuwun pangapunten Juragan, pitakonipun radi dangu anggen kula mikir. Cobi dipun damel langkung ringkes nggih.")
        else:
            await update.message.reply_text("Nyuwun pangapunten, saweg wonten alangan teknis wonten ing sistem kula...")

naming_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start_naming)],
    states={
        GET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_name)],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)

login_handler = ConversationHandler(
    entry_points=[CommandHandler('login', login_eclass)],
    states={
        GET_LOGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_login)],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)

from telegram.request import HTTPXRequest

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Update {update} caused error: {context.error}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize MongoDB indexes safely (won't crash if DB is down)
    init_db()
    
    # Timeout harus besar untuk cloud environments (HF Spaces) + upload file besar
    req = HTTPXRequest(connection_pool_size=8, connect_timeout=60.0, read_timeout=120.0, write_timeout=120.0)
    # Separate request object for long-polling (get_updates needs longer read timeout)
    get_updates_req = HTTPXRequest(connection_pool_size=2, connect_timeout=60.0, read_timeout=300.0, write_timeout=120.0)
    tg_builder = (
        ApplicationBuilder()
        .token(os.getenv("TELEGRAM_TOKEN"))
        .request(req)
        .get_updates_request(get_updates_req)
    )

    telegram_base_url, telegram_base_file_url = get_telegram_api_urls()
    if telegram_base_url:
        print(f"Using Telegram API proxy: {telegram_base_url}")
        tg_builder = tg_builder.base_url(telegram_base_url).base_file_url(telegram_base_file_url)

    tg_app = tg_builder.build()
    
    tg_app.add_error_handler(error_handler)
    commands = [
        BotCommand("start", "set your name"),
        BotCommand("me", "bot will say hi to you"),
        BotCommand("author", "tell you the author of this bot"),
        BotCommand("describe", "tell what Aily can do"),
        BotCommand("login", "login to e-class"),
        BotCommand("matakuliah", "show your matakuliah list"),
        BotCommand("materi", "show materi for a specific class")
    ]
    
    tg_app.add_handler(naming_handler)
    tg_app.add_handler(login_handler)
    tg_app.add_handler(CommandHandler("author", author))
    tg_app.add_handler(CommandHandler("me", user_name))
    tg_app.add_handler(CommandHandler("describe", describe))
    tg_app.add_handler(CommandHandler("matakuliah", matakuliah_list))
    tg_app.add_handler(CommandHandler("materi", materi_list))
    tg_app.add_handler(CallbackQueryHandler(handle_materi_callback))
    tg_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_telegram_message))
    
    # Retry initialization in case of timeout (common in cloud/Docker environments)
    max_retries = 3
    for attempt in range(max_retries):
        try:
            await tg_app.initialize()
            await tg_app.start()
            break
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 5 * (attempt + 1)
                print(f"⚠️ Bot init attempt {attempt+1}/{max_retries} failed: {e}. Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                print(f"❌ Bot initialization failed after {max_retries} attempts: {e}")
                raise
    
    try:
        await tg_app.bot.set_my_commands(commands=commands)
    except Exception as e:
        print(f"Warning: Failed to set bot commands during startup: {e}")
        
    await tg_app.updater.start_polling(
        allowed_updates=["message", "callback_query"]
    )
    
    yield
    
    await tg_app.updater.stop()
    await tg_app.stop()
    await tg_app.shutdown()

app = FastAPI(lifespan=lifespan)
app.include_router(login_bp, prefix="/api/v1/login", tags=["login"])
app.include_router(matakuliah_bp, prefix="/api/v1/matakuliah", tags=["matakuliah"])
app.include_router(presensi_bp, prefix="/api/v1/presensi", tags=["presensi"])
app.include_router(materi_bp, prefix="/api/v1/materi", tags=["materi"])

@app.get("/")
def read_root():
    return {
        "status": "Yamato Systems 'Operational'",
        "framework": "FastAPI",
        "endpoints": {
            "login": "/api/v1/login",
            "matakuliah": "/api/v1/matakuliah",
            "presensi": "/api/v1/presensi/{id}",
            "materi": "/api/v1/materi/{id}"
        }
    }

@app.get("/api/logs")
async def get_logs():
    return {"logs": []}