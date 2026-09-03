# 🗣️ Dialogue TTS Studio (Gratis)

Aplikasi web sederhana untuk mengubah **naskah percakapan 2 orang** menjadi **satu file audio**
yang bisa didengarkan dan didownload — **100% economical**.

> 🤖 **Dibuat dengan bantuan AI** — kode, struktur project, dan dokumentasi di repo ini
> disusun dengan bantuan Claude (Anthropic) melalui percakapan iteratif, lalu disesuaikan
> untuk kebutuhan proyek ini.

---

## 🤔 Aplikasi ini buat apa?

Bayangkan kamu punya naskah dialog seperti ini:

```
A: Hi, how are you today?
B: I'm doing great, thanks! How about you?
A: Pretty good, just testing this new app.
```

Aplikasi ini akan **membaca setiap baris**, mengubahnya jadi suara dengan **voice yang
berbeda untuk A dan B**, lalu **menggabungkan semuanya jadi satu file MP3** yang bisa
kamu putar atau download — seperti percakapan asli antara dua orang.

Cocok untuk: latihan listening bahasa Inggris, membuat konten podcast pendek, dubbing
skrip dialog, prototipe voice-over, dan lain-lain.

---

## ✨ Fitur Utama

| Fitur | Penjelasan |
|---|---|
| 🆓 **Ekonomis 100%** | Pakai [edge-tts](https://github.com/rany2/edge-tts) (layanan suara Microsoft Edge). Tidak perlu API key. |
| 🗣️ **Multi-voice** | Voice A dan Voice B bisa dipilih terpisah, termasuk banyak pilihan Bahasa Inggris (US/UK/AU) dan Bahasa Indonesia. |
| 🎧 **Preview sebelum download** | Dengarkan hasil gabungan, atau dengarkan tiap baris satu-satu. |
| ⬇️ **Download mudah** | Tombol download MP3 dengan nama file otomatis: `conversation_[waktu].mp3`. |
| 🕘 **Riwayat** | Semua percakapan yang sudah dibuat tersimpan selama sesi berjalan, bisa didownload ulang tanpa generate lagi. |
| 📊 **Info file** | Durasi dan ukuran file ditampilkan sebelum kamu download. |
| 🐢 **Atur kecepatan & jeda** | Bisa dipercepat/diperlambat, dan atur jeda hening antar baris supaya terdengar natural. |

---

## 🚀 Cara Pakai (Sudah Online / Sudah Deploy)

1. Buka link aplikasi (misalnya `https://text-to-speech-converter-mec.streamlit.app`).
2. Di **sidebar kiri**:
   - Pilih **filter bahasa** untuk Voice A dan Voice B, misalnya **"English - US (en-US)"**
     untuk percakapan Bahasa Inggris.
   - Pilih voice yang diinginkan (ada tanda pria/wanita di label-nya).
   - Atur kecepatan bicara & jeda antar baris kalau perlu (opsional, default sudah pas).
3. Di kotak **"Naskah Percakapan"**, tulis dialog dengan format:
   ```
   A: teks untuk pembicara A
   B: teks untuk pembicara B
   ```
   *(Hanya boleh 2 label pembicara berbeda dalam satu naskah, misal `A`/`B` atau nama tokoh.)*
4. Buka bagian **"Preview parsing naskah"** untuk memastikan naskah terbaca dengan benar.
5. Klik **🎬 Generate Percakapan**, tunggu progress bar sampai selesai.
6. Dengarkan hasilnya di player, cek durasi & ukuran file, lalu klik **⬇️ Download Percakapan (MP3)**.
7. Semua hasil generate sebelumnya bisa dilihat & didownload ulang di bagian **🕘 Riwayat Percakapan**.

---

## 💻 Cara Pakai di Komputer Sendiri (Lokal)

### 1. Install Python
Pastikan sudah punya Python 3.9 atau lebih baru.

### 2. Install ffmpeg
Aplikasi ini butuh **ffmpeg** untuk menggabungkan audio.

- **Windows**: download dari https://ffmpeg.org/download.html, lalu tambahkan ke PATH.
- **macOS**: `brew install ffmpeg`
- **Ubuntu/Debian**: `sudo apt-get install ffmpeg`

### 3. Install dependencies Python
Di folder project, jalankan:
```bash
pip install -r requirements.txt
```

### 4. Jalankan aplikasi
```bash
streamlit run app.py
```
Browser akan otomatis terbuka ke `http://localhost:8501`.

---

## ☁️ Cara Deploy ke Streamlit Community Cloud (Gratis)

1. Push semua file project ini ke repository **GitHub**.
2. Buka https://share.streamlit.io/ → **New app**.
3. Pilih repository, branch, dan set **Main file path** ke `app.py`.
4. Klik **Deploy** — tunggu beberapa menit sampai proses instalasi selesai.
5. Selesai! Aplikasi bisa diakses lewat URL publik, dan **auto-update** setiap kali
   kamu push perubahan baru ke GitHub.

> ⚠️ **Penting:** file `packages.txt` (isinya `ffmpeg`) **wajib ada** di root repo,
> supaya Streamlit Cloud otomatis meng-install ffmpeg. Tanpa ini, proses penggabungan
> audio akan gagal.

---

## 📁 Struktur File

```
├── app.py              # Kode utama aplikasi
├── requirements.txt    # Daftar library Python yang dibutuhkan
├── packages.txt         # Dependency sistem (ffmpeg) untuk Streamlit Cloud
└── README.md            # Dokumentasi ini
```

---

## 🛠️ Troubleshooting

**"Library edge-tts tidak ditemukan" saat dibuka**
- Pastikan `requirements.txt` di repo GitHub sudah berisi baris `edge-tts>=6.1.0`.
- Di dashboard Streamlit Cloud, buka menu **⋮ → Reboot app** supaya dependency
  di-install ulang dari `requirements.txt` terbaru.
- Kalau masih gagal, cek log deploy (menu ⋮ → Manage app → tab **Logs**) di bagian
  "Installing dependencies" untuk melihat pesan error pastinya.

**"Library pydub tidak ditemukan" atau audio gagal digabung**
- Pastikan `packages.txt` berisi `ffmpeg` dan sudah ter-push ke GitHub.
- Reboot app setelah menambahkan `packages.txt`.

**Generate lama / gagal di tengah jalan**
- edge-tts butuh koneksi internet aktif (memanggil layanan online Microsoft).
  Coba generate ulang, biasanya karena koneksi sempat putus.

**Suara yang keluar bukan Bahasa Inggris**
- Cek lagi filter bahasa di sidebar (Voice A / Voice B) sudah diset ke
  **English - US / UK / AU**, bukan default Indonesia.

---

## ❓ FAQ Singkat

**Q: Apakah benar-benar gratis selamanya?**
A: Ya, selama edge-tts (layanan Microsoft Edge TTS) masih tersedia gratis untuk publik.
Tidak ada API key atau billing yang perlu diisi.

**Q: Bisa lebih dari 2 pembicara?**
A: Versi ini dibatasi maksimal 2 label pembicara per naskah agar sederhana. Bisa
dikembangkan lebih lanjut kalau dibutuhkan lebih banyak pembicara.

**Q: Bisa bahasa lain selain Inggris/Indonesia?**
A: Bisa — edge-tts mendukung banyak bahasa (Jepang, Korea, Mandarin, Spanyol, dst).
Pilih saja lewat filter bahasa di sidebar.

---

## 🙏 Kredit

- Mesin suara: [edge-tts](https://github.com/rany2/edge-tts) (open-source, memanfaatkan
  layanan Microsoft Edge Read Aloud).
- Framework aplikasi: [Streamlit](https://streamlit.io/).
- Penggabungan audio: [pydub](https://github.com/jiaaro/pydub) + [ffmpeg](https://ffmpeg.org/).
- Kode & dokumentasi disusun dengan bantuan **AI (Claude, Anthropic)**.