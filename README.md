# 🎙️ Multi-Voice TTS Studio

Aplikasi Text-to-Speech (TTS) multi-voice berbasis **Streamlit** + **OpenAI TTS API**,
dengan fitur download audio yang lengkap: preview, format pilihan, history, dan bulk-download (ZIP).

---

## ✨ Fitur

**Multi-voice**
- 11 pilihan voice (alloy, echo, fable, onyx, nova, shimmer, coral, sage, verse, ballad, ash) lengkap dengan deskripsi singkat.
- Preview sample suara sebelum generate teks penuh.

**Download**
- Format MP3 atau WAV.
- Nama file otomatis: `tts_[timestamp]_[voice_name].mp3`
- Preview audio (player) sebelum download.
- Progress bar saat proses generate.
- Download berulang kali tanpa perlu generate ulang (audio tersimpan di `session_state` selama sesi berjalan).
- History semua audio yang pernah dibuat, masing-masing punya tombol download sendiri.
- Download semua riwayat sekaligus sebagai **ZIP**.
- Ukuran file ditampilkan setelah generate; durasi ditampilkan sebelum download.
- Kompresi otomatis (opsional, butuh `pydub` + `ffmpeg`) jika file > 5 MB.

**Lainnya**
- Character counter (maks 4096 karakter, sesuai batas API).
- Speed control (0.5x–2.0x).
- Desain responsif untuk layar mobile.
- Error handling: teks kosong, API key tidak valid, kegagalan koneksi, file terlalu besar — masing-masing dengan pesan jelas + tombol retry.

---

## 📁 Struktur Project

```
tts_app/
├── app.py                     # Aplikasi utama
├── requirements.txt           # Dependencies Python
├── .streamlit/
│   └── secrets.toml           # Template API key (JANGAN commit versi berisi key asli)
├── README.md
└── .gitignore
```

---

## 🚀 Menjalankan Secara Lokal

1. **Clone / salin folder project ini**, lalu masuk ke direktorinya:
   ```bash
   cd tts_app
   ```

2. **Buat virtual environment** (opsional tapi disarankan):
   ```bash
   python -m venv venv
   source venv/bin/activate      # Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Isi API Key** di `.streamlit/secrets.toml`:
   ```toml
   OPENAI_API_KEY = "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxx"
   ```
   Dapatkan API key dari https://platform.openai.com/api-keys

5. **Jalankan aplikasi**:
   ```bash
   streamlit run app.py
   ```

6. Buka browser ke `http://localhost:8501`.

> Jika belum sempat mengisi `secrets.toml`, aplikasi juga menyediakan input API Key manual di sidebar (khusus untuk testing lokal, tidak disarankan untuk deployment publik).

---

## ☁️ Deploy ke Streamlit Community Cloud

1. Push project ini ke repository GitHub (public atau private).
   - **Pastikan** `.streamlit/secrets.toml` yang berisi API key **asli** TIDAK ikut ter-push (lihat bagian `.gitignore` di bawah).
2. Buka https://share.streamlit.io/ → **New app** → pilih repo dan branch Anda → `app.py` sebagai entry point.
3. Di halaman **App settings → Secrets**, tempelkan isi berikut (ganti dengan key asli Anda):
   ```toml
   OPENAI_API_KEY = "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxx"
   ```
4. Klik **Deploy**. Aplikasi akan otomatis punya URL publik (`https://<nama-app>.streamlit.app`).
5. **Auto-deploy**: setiap kali Anda push perubahan ke branch yang di-deploy, Streamlit Cloud akan otomatis rebuild & redeploy aplikasi.

---

## 🔍 Cara Kerja Fitur Download (Penjelasan Teknis)

1. **Generate audio** — teks dikirim ke `client.audio.speech.create(...)`, dan `response.content`
   berisi bytes mentah audio (MP3 atau WAV, tergantung `response_format`).
2. **Simpan ke `st.session_state.history`** — ini kunci supaya download bisa dilakukan
   berkali-kali tanpa generate ulang. Streamlit me-rerun seluruh script setiap ada
   interaksi (termasuk klik tombol download), jadi tanpa `session_state`, audio yang
   baru saja dibuat akan "hilang" dan API akan terpanggil ulang secara tidak sengaja.
   Dengan menyimpan bytes-nya di memori sesi, `st.download_button` bisa dipanggil
   berkali-kali dari data yang sama.
3. **Nama file unik** — dibuat dari kombinasi timestamp (`%Y%m%d_%H%M%S`) dan nama voice,
   sehingga setiap file punya nama berbeda meski voice sama.
4. **Durasi audio** — dihitung dari bytes MP3 memakai `mutagen` (pure Python, tanpa
   perlu ffmpeg) sebelum tombol download muncul, supaya pengguna tahu berapa lama
   audio yang akan mereka download.
5. **ZIP semua riwayat** — dibuat secara *in-memory* memakai `zipfile.ZipFile` +
   `io.BytesIO`, tanpa menulis file sementara ke disk — penting untuk deployment
   di Streamlit Cloud yang filesystem-nya bersifat sementara (*ephemeral*).
6. **Kompresi otomatis** — hanya aktif jika file > 5 MB **dan** `pydub` + `ffmpeg`
   tersedia di environment; jika tidak, aplikasi tetap berjalan dan hanya menampilkan
   peringatan ukuran file.

---

## 💡 Tips Optimasi

- **Batasi panjang teks per request** (idealnya < 2000 karakter) agar waktu generate
  lebih cepat dan ukuran file tetap kecil — pecah teks panjang menjadi beberapa
  bagian jika perlu.
- **Gunakan format MP3** untuk ukuran file jauh lebih kecil dibanding WAV (WAV tidak
  terkompresi, bisa 5–10x lebih besar untuk durasi yang sama).
- **Model `tts-1`** lebih cepat & lebih murah untuk draft/testing; gunakan
  `tts-1-hd` atau `gpt-4o-mini-tts` untuk hasil akhir yang lebih halus.
- **Cache preview voice** (`st.session_state.voice_previews`) mencegah pemanggilan
  API berulang untuk sample yang sama — hemat kuota & biaya.
- Untuk trafik tinggi di production, pertimbangkan menambahkan **rate limiting**
  sederhana (misalnya cooldown antar generate per user) agar biaya API terkendali.

---

## ⚠️ Error Handling

| Kondisi                          | Perilaku Aplikasi                                              |
|-----------------------------------|------------------------------------------------------------------|
| Teks kosong                       | Peringatan (`st.warning`), proses generate dibatalkan.          |
| API key kosong                    | Pesan error jelas, meminta isi API key di sidebar / secrets.    |
| API key tidak valid               | `AuthenticationError` ditangkap, pesan error spesifik.          |
| Gagal koneksi / error API lain    | Pesan error + tombol **Coba Lagi**.                             |
| File audio > 5 MB                 | Kompresi otomatis (jika `pydub`+ffmpeg ada) atau peringatan.    |

---

## 📦 requirements.txt

```
streamlit>=1.37.0
openai>=1.40.0
mutagen>=1.47.0
pydub>=0.25.1   # opsional, untuk kompresi otomatis (butuh ffmpeg di sistem)
```