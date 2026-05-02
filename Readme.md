# Dokumentasi Arsitektur & Fungsi Bot Telegram (Aily)

Dokumen ini memuat penjelasan mengenai arsitektur sistem, alur logika, dan detail fungsionalitas dari setiap komponen dalam proyek Bot Telegram Aily yang terintegrasi dengan web E-Class kampus.

# Apa itu AILY 
  Aily adalah BOT telegram yang dibuat oleh Kiya sebagai asisten pribadi untuk membantu mengakses eclass tanpa perlu secara langsung masuk ke website eclass.uldw.ac.id.
---

## 🛠️ 1. Persiapan & Setup (Setup & Installation)

### Langkah 1: Membuat Virtual Environment
Sangat disarankan untuk menggunakan *virtual environment* agar dependensi (library) terisolasi dan tidak bentrok dengan proyek lain.

**Untuk Windows:**
```cmd
python -m venv venv
venv\Scripts\activate
```

**Untuk macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### Langkah 2: Install Dependensi
Setelah virtual environment aktif (ditandai dengan tulisan `(venv)` di terminal), install semua pustaka yang dibutuhkan:
```bash
pip install -r requirements.txt
```

### Langkah 3: Konfigurasi File `.env`
Sistem ini menggunakan *Environment Variables* untuk merahasiakan kunci API dan kata sandi. Buat file bernama `.env` (tanpa nama depan, hanya ekstensi) di root direktori proyek Anda. 

Isi file `.env` tersebut dengan format berikut:
```env
# Token Bot Telegram (Didapatkan dari BotFather di Telegram)
TELEGRAM_TOKEN=your_telegram_bot_token_here

# API Key untuk Google Gemini AI (Didapatkan dari Google AI Studio)
GEMINI_API_KEY=your_gemini_api_key_here

# Kredensial Database MongoDB (Untuk menyimpan log chat & data user)
DB_USERNAME=your_mongodb_username
DB_PASSWORD=your_mongodb_password

# Konfigurasi n8n (Opsional, khusus jika Anda memakai webhook eksternal n8n)
N8N_MATAKULIAH_WEBHOOK_URL=https://your-n8n-url.com/webhook/matakuliah
N8N_WEBHOOK_SECRET=your_webhook_secret_here

# Pengaturan batas waktu Scraper (dalam detik)
REQUEST_TIMEOUT_SECONDS=60

# Kunci Enkripsi untuk Password E-Class (Fernet Key)
# Digunakan untuk mengenkripsi password akun e-class yang disimpan ke DB
# Buat key baru dengan menjalankan perintah python ini di terminal:
# python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ECLASS_CREDENTIAL_KEY=your_generated_fernet_key_here
```

---

## ▶️ 2. Menjalankan Aplikasi

Aplikasi ini menggunakan struktur *monolith*, di mana API FastAPI dan Bot Telegram berjalan bersamaan dalam satu proses.

Untuk menjalankan sistem secara penuh, pastikan virtual environment sudah aktif, lalu jalankan:
```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Jika Anda hanya ingin menjalankan dan mengetes *API scraper* (tanpa bot Telegram menyala):
```bash
python request_handler.py
```

---

## 🔄 3. Alur Kerja (Flow) Program

Berikut adalah alur bagaimana sistem memproses pesan atau interaksi dari pengguna:

```mermaid
graph TD
    User([Telegram User]) -->|Kirim Pesan / Perintah| Bot[Main Bot - FastAPI]
    Bot -->|Cek Sesi / DB| DB[(MongoDB)]
    
    Bot -->|Jika Pesan Umum| Gemini[Google Gemini AI]
    Gemini -->|Balasan AI| Bot
    
    Bot -->|Jika Perintah E-Class / /login /materi| API[Scraper API - Internal FastAPI]
    API <-->|Request Web Scraping| EClass[Web E-Class Kampus]
    API -->|Data JSON / Dokumen| Bot
    Bot -->|Kirim Balasan| User
```

**Penjelasan Tahapan:**
1. **Inisialisasi Sistem (`main.py`):** Aplikasi berjalan melalui server Uvicorn. FastAPI akan me-*load* rute-rute API scraper (di folder `routes/`). Bersamaan dengan itu, *lifespan* FastAPI akan menyalakan bot Telegram di latar belakang (`asyncio.create_task`).
2. **Penerimaan Pesan:** Saat user Telegram menekan `/start` atau mengirim pesan, Telegram Bot menangkapnya. Modul `handle_db.py` akan otomatis menyimpan/memperbarui data profil Telegram pengguna ke MongoDB.
3. **Pemrosesan Perintah (Routing):**
   - **Perintah E-Class (`/login`, `/matakuliah`, `/materi [ID]`, `masuk [ID]`):** Bot akan memeriksa *cookies* sesi user di memori (`user_sessions`). Setelah itu, bot akan secara internal memanggil router API FastAPI. Router ini meniru aksi *browser* (Web Scraping) menggunakan token/cookie untuk mengambil jadwal, materi, atau menekan tombol presensi pada web E-Class kampus.
   - **Tombol Unduh Materi (`handle_materi_callback`):** Ketika tombol unduh ditekan, bot me-*request* langsung file ke web E-Class dan mengirimkan balasan berupa dokumen Telegram ke pengguna.
   - **Pesan Biasa (Obrolan):** Jika teks bukan perintah sistem, pesannya diteruskan ke **Google Gemini AI**. AI ini sudah diprogram (melalui *system prompt*) dengan persona **Asisten Jawa Krama Inggil**, sehingga merespons dengan sopan berbahasa Jawa.
4. **Respons Akhir:** Bot mengembalikan hasil (berupa teks daftar matakuliah, file materi, atau teks percakapan) ke pengguna. Jika panjang pesan melebihi limit Telegram (4000 karakter), bot akan membaginya menjadi beberapa pesan berurutan.

---

## 📂 4. Penjelasan Fungsi Berdasarkan File

### 1. Interaksi Database (`handle_db.py`)
Berfungsi menghubungkan bot dengan MongoDB menggunakan pustaka `pymongo`. Mengatur manajemen data pengguna dan rekam jejak.
- **`save_user()`**: Menyimpan profil dasar pengguna (ID, username, first name) saat pertama kali interaksi.
- **`getName()`**: Membaca nama panggilan khusus (*preferred name*) dari database untuk panggilan yang lebih personal.
- **`saveChatLog()`**: Mencatat riwayat *chat* antara user dan bot (Gemini) untuk konteks AI atau keperluan audit.
- **`validate_user()`**: Mengunci akses agar hanya pengguna yang terdaftar/valid yang bisa memakai fitur API kampus.

### 2. Logika Utama Bot Telegram (`main.py`)
File eksekutor dan pengontrol utama bot Telegram.
- **Manajemen Sesi:** `/login` akan menyimpan *cookies* akses di memori (dictionary `user_sessions`) selama aplikasi berjalan.
- **Handler Akademik:** Memproses perintah-perintah kuliah seperti `/matakuliah` (jadwal kelas), `/materi` (modul/tugas), dan presensi teks `masuk [ID]`.
- **Integrasi Gemini AI:** Fungsi `gemini_instruction` mendefinisikan persona, dan `handle_telegram_message` mengelola tanya-jawab bebas *user* ke Gemini.

### 3. Backend Scraper API (`request_handler.py` & `routes/`)
Pusat logika API web-scraping E-Class. `request_handler.py` mengatur server API independen.
- **Folder `routes/` (seperti `login.py`, `matakuliah.py`, `materi.py`):** Berisi logika `BeautifulSoup` dan `requests` untuk me-*request* HTML E-Class, mengambil token CSRF (atau parameter tersembunyi lainnya), melakukan submit form, dan mengembalikan datanya ke bot dalam format terstruktur (JSON).

---

> [!TIP]
> **Catatan Pengembangan:** Mengingat `user_sessions` dan `materi_cache` masih disimpan di dalam RAM lokal server, sesi login pengguna akan hilang saat bot dimatikan (*restart*). Jika ingin data login bertahan lebih lama tanpa perlu user login ulang setiap bot restart, pertimbangkan memindahkan mekanisme penyimpanan cookie E-Class ke database MongoDB.
