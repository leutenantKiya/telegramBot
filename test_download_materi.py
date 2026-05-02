"""
Test script: Login -> Get Materi MH1073 -> Download salah satu file
Menguji alur lengkap download materi seperti yang dilakukan bot Telegram.
"""
import sys
import os

# Ensure proper encoding for Windows console
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv()

from handle_db import get_eclass_credentials, CredentialStorageError
from routes.login import login as eclass_login
from routes.materi import get_materi
from main import download_eclass_file_sync

# Step 1: Ambil credential dari database (terenkripsi)
print("=" * 60)
print("STEP 1: Mengambil credential dari database...")
print("=" * 60)

# Cari user_id yang tersimpan di database
from pymongo import MongoClient

USERNAME = os.getenv("DB_USERNAME")
PASSWORD = os.getenv("DB_PASSWORD")
uri = f"mongodb://{USERNAME}:{PASSWORD}@localhost:27017/?authSource=admin"
mongo_client = MongoClient(uri)
db = mongo_client['user']
collection = db['user_log']

# Cari user yang punya eclass_credentials
user_with_creds = collection.find_one(
    {"eclass_credentials": {"$exists": True}},
    {"user_id": 1, "eclass_credentials.nim": 1, "prefered_name": 1}
)

if not user_with_creds:
    print("[GAGAL] Tidak ada user yang punya eclass credentials di database.")
    print("Silakan /login dulu di bot Telegram.")
    sys.exit(1)

user_id = user_with_creds["user_id"]
nim = user_with_creds.get("eclass_credentials", {}).get("nim", "?")
name = user_with_creds.get("prefered_name", "Unknown")
print(f"  User ditemukan: {name} (Telegram ID: {user_id}, NIM: {nim})")

# Decrypt password dan ambil credentials
try:
    credentials = get_eclass_credentials(user_id)
except CredentialStorageError as e:
    print(f"[GAGAL] Credential storage error: {e}")
    sys.exit(1)

if not credentials:
    print("[GAGAL] Tidak bisa decrypt credentials.")
    sys.exit(1)

print(f"  Credentials berhasil didecrypt untuk NIM: {credentials['id']}")

# Step 2: Login ke eclass untuk mendapatkan cookies
print()
print("=" * 60)
print("STEP 2: Login ke eclass...")
print("=" * 60)

login_result = eclass_login({
    "id": credentials["id"],
    "password": credentials["password"]
})

if not isinstance(login_result, dict) or not login_result.get("success"):
    error_msg = login_result.get("error", "Unknown error") if isinstance(login_result, dict) else str(login_result)
    print(f"[GAGAL] Login failed: {error_msg}")
    sys.exit(1)

cookies = login_result.get("data", {}).get("cookies", {})
login_msg = login_result.get("data", {}).get("message", "")
print(f"  {login_msg}")
print(f"  Cookies diterima: {list(cookies.keys())}")

# Step 3: Ambil daftar materi MH1073
print()
print("=" * 60)
print("STEP 3: Mengambil daftar materi MH1073...")
print("=" * 60)

materi_result = get_materi("MH1073", {"cookies": cookies})

if not isinstance(materi_result, dict) or not materi_result.get("success"):
    error_msg = materi_result.get("error", "Unknown error") if isinstance(materi_result, dict) else str(materi_result)
    print(f"[GAGAL] Get materi failed: {error_msg}")
    sys.exit(1)

materi_list = materi_result.get("data", [])
print(f"  Ditemukan {len(materi_list)} materi:")

downloadable = []
for i, m in enumerate(materi_list):
    icon = "[DL]" if m.get("is_download") else "[LINK]"
    print(f"  {i+1}. {icon} {m['title']} ({m.get('type', '?')}) -> {m['link']}")
    if m.get("is_download"):
        downloadable.append(m)

if not downloadable:
    print()
    print("[INFO] Tidak ada materi yang bisa didownload (semuanya link external).")
    sys.exit(0)

# Step 4: Download file pertama yang bisa didownload
print()
print("=" * 60)
print(f"STEP 4: Mencoba download: {downloadable[0]['title']}...")
print("=" * 60)

target = downloadable[0]
try:
    filename, file_bytes = download_eclass_file_sync(
        link=target["link"],
        cookies=cookies,
        title=target["title"],
        referer=target.get("referer"),
        alt_links=target.get("alt_links")
    )
    
    # Simpan file
    output_path = os.path.join(os.path.dirname(__file__), f"test_{filename}")
    with open(output_path, "wb") as f:
        f.write(file_bytes)
    
    size_kb = len(file_bytes) / 1024
    print(f"  [OK] Download berhasil!")
    print(f"  Filename : {filename}")
    print(f"  Size     : {size_kb:.1f} KB")
    print(f"  Saved to : {output_path}")
    
    # Verifikasi header file
    header = file_bytes[:10]
    if header.startswith(b"%PDF"):
        print(f"  Format   : Valid PDF file")
    elif header.startswith(b"PK"):
        print(f"  Format   : ZIP-based file (docx/pptx/xlsx)")
    else:
        print(f"  Header   : {header}")

except Exception as e:
    print(f"  [GAGAL] Download error: {e}")
    import traceback
    traceback.print_exc()

print()
print("=" * 60)
print("TEST SELESAI")
print("=" * 60)
