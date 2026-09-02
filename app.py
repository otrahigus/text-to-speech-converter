"""
================================================================
 Multi-Voice TTS Studio — Streamlit + OpenAI TTS API
================================================================
Aplikasi Text-to-Speech dengan:
  - 5+ pilihan voice (multi-voice) + preview sample suara
  - Format download MP3 / WAV
  - Nama file otomatis: tts_[timestamp]_[voice_name].mp3
  - Preview audio sebelum download
  - Progress indicator saat generate
  - History download (bisa download ulang tanpa generate ulang)
  - Download semua riwayat sebagai ZIP
  - Responsive (mobile-friendly) layout
  - Error handling lengkap (teks kosong, API key invalid, gagal, file besar)

Jalankan:
    streamlit run app.py

Struktur project:
    app.py
    requirements.txt
    .streamlit/secrets.toml   (template API key)
    README.md
    .gitignore
================================================================
"""

import io
import zipfile
from datetime import datetime

import streamlit as st
from openai import OpenAI, AuthenticationError, APIError, APIConnectionError

# Import opsional untuk membaca durasi audio & kompresi.
# Dibungkus try/except supaya app tetap jalan walau lib ini belum terinstall.
try:
    from mutagen.mp3 import MP3
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False

try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False


# ================================================================
# 1. KONFIGURASI HALAMAN & CSS (termasuk responsive + tombol custom)
# ================================================================
st.set_page_config(
    page_title="Multi-Voice TTS Studio",
    page_icon="🎙️",
    layout="centered",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    /* ---------- Judul ---------- */
    .tts-title {
        font-size: clamp(1.5rem, 4vw, 2.2rem);
        font-weight: 800;
        background: linear-gradient(90deg, #7F5AF0, #2CB67D);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.1rem;
    }
    .tts-subtitle {
        color: #9AA0A6;
        margin-bottom: 1.2rem;
        font-size: clamp(0.85rem, 2vw, 1rem);
    }

    /* ---------- Tombol utama (Generate) ---------- */
    div.stButton > button {
        width: 100%;
        border-radius: 12px;
        border: none;
        padding: 0.7rem 1.1rem;
        font-weight: 700;
        font-size: 1rem;
        background: linear-gradient(90deg, #7F5AF0, #6246EA);
        color: white;
        transition: all 0.2s ease-in-out;
        box-shadow: 0 4px 14px rgba(127, 90, 240, 0.35);
    }
    div.stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 20px rgba(127, 90, 240, 0.45);
    }

    /* ---------- Tombol Download ---------- */
    div.stDownloadButton > button {
        width: 100%;
        border-radius: 12px;
        border: 2px solid #2CB67D;
        padding: 0.7rem 1.1rem;
        font-weight: 700;
        font-size: 0.95rem;
        background: linear-gradient(90deg, #2CB67D, #16A085);
        color: white;
        transition: all 0.2s ease-in-out;
        box-shadow: 0 4px 14px rgba(44, 182, 125, 0.35);
    }
    div.stDownloadButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 20px rgba(44, 182, 125, 0.5);
        border-color: #ffffff;
    }

    /* ---------- Pill info kecil ---------- */
    .meta-pill {
        display: inline-block;
        padding: 0.3rem 0.8rem;
        margin: 0.15rem 0.25rem 0.15rem 0;
        border-radius: 999px;
        background: rgba(127, 90, 240, 0.12);
        color: #7F5AF0;
        font-weight: 600;
        font-size: 0.8rem;
    }

    /* ---------- Kartu history ---------- */
    .history-card {
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 12px;
        padding: 0.8rem 1rem;
        margin-bottom: 0.6rem;
        background: rgba(255,255,255,0.02);
    }

    /* ---------- Responsive: layar kecil (HP) ---------- */
    @media (max-width: 640px) {
        .tts-title { font-size: 1.4rem; }
        div.stButton > button, div.stDownloadButton > button {
            font-size: 0.9rem;
            padding: 0.6rem 0.8rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="tts-title">🎙️ Multi-Voice TTS Studio</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="tts-subtitle">Ubah teks jadi suara dengan berbagai pilihan voice — '
    'preview, generate, dan download dengan mudah.</div>',
    unsafe_allow_html=True,
)


# ================================================================
# 2. DATA VOICE (multi-voice + deskripsi)
# ================================================================
# Deskripsi di bawah adalah gambaran umum karakter suara untuk membantu
# pengguna memilih, bukan klaim resmi dari OpenAI.
VOICES = {
    "alloy":   "Netral & seimbang — cocok untuk narasi umum.",
    "echo":    "Tenang & jernih — cocok untuk konten edukasi.",
    "fable":   "Hangat & bernuansa cerita — cocok untuk storytelling.",
    "onyx":    "Dalam & tegas — cocok untuk voice-over formal.",
    "nova":    "Ringan & energik — cocok untuk konten promosi/marketing.",
    "shimmer": "Lembut & ramah — cocok untuk asisten virtual.",
    "coral":   "Ekspresif & hangat — cocok untuk konten percakapan.",
    "sage":    "Kalem & meyakinkan — cocok untuk narasi profesional.",
    "verse":   "Dinamis & ekspresif — cocok untuk konten kreatif.",
    "ballad":  "Lembut & melodius — cocok untuk konten emosional.",
    "ash":     "Jelas & profesional — cocok untuk podcast/berita.",
}

SAMPLE_TEXT = "Halo, ini contoh suara saya. Semoga Anda suka!"


# ================================================================
# 3. SESSION STATE
# ================================================================
if "history" not in st.session_state:
    st.session_state.history = []          # list of dict: hasil generate
if "voice_previews" not in st.session_state:
    st.session_state.voice_previews = {}    # cache preview per voice
if "last_error" not in st.session_state:
    st.session_state.last_error = None


def get_api_key() -> str:
    """Ambil API key dari st.secrets, fallback ke input manual di sidebar."""
    key = st.secrets.get("OPENAI_API_KEY", "") if hasattr(st, "secrets") else ""
    if not key:
        key = st.session_state.get("manual_api_key", "")
    return key


def build_filename(voice: str, ext: str) -> str:
    """Nama file otomatis: tts_[timestamp]_[voice_name].ext"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"tts_{ts}_{voice}.{ext}"


def get_audio_duration(audio_bytes: bytes, fmt: str):
    """Coba hitung durasi audio. Return detik (float) atau None jika gagal."""
    if fmt == "mp3" and MUTAGEN_AVAILABLE:
        try:
            return MP3(io.BytesIO(audio_bytes)).info.length
        except Exception:
            return None
    if PYDUB_AVAILABLE:
        try:
            seg = AudioSegment.from_file(io.BytesIO(audio_bytes), format=fmt)
            return len(seg) / 1000.0
        except Exception:
            return None
    return None


def maybe_compress(audio_bytes: bytes, fmt: str, size_kb: float, threshold_kb: float = 5000):
    """
    Kompresi otomatis sederhana jika file terlalu besar (> threshold_kb).
    Hanya berjalan jika pydub + ffmpeg tersedia. Menurunkan bitrate MP3.
    Jika tidak tersedia, kembalikan bytes asli + flag False.
    """
    if size_kb <= threshold_kb:
        return audio_bytes, False
    if not PYDUB_AVAILABLE:
        return audio_bytes, False
    try:
        seg = AudioSegment.from_file(io.BytesIO(audio_bytes), format=fmt)
        out = io.BytesIO()
        seg.export(out, format="mp3", bitrate="64k")
        return out.getvalue(), True
    except Exception:
        return audio_bytes, False


def call_tts_api(client: OpenAI, model: str, voice: str, text: str, speed: float, fmt: str) -> bytes:
    """Wrapper pemanggilan OpenAI TTS API. Format WAV/MP3 didukung langsung oleh API."""
    response = client.audio.speech.create(
        model=model,
        voice=voice,
        input=text,
        speed=speed,
        response_format=fmt,   # "mp3" atau "wav"
    )
    return response.content


# ================================================================
# 4. SIDEBAR — KONFIGURASI
# ================================================================
with st.sidebar:
    st.header("⚙️ Konfigurasi")

    secret_key = st.secrets.get("OPENAI_API_KEY", "") if hasattr(st, "secrets") else ""
    if secret_key:
        st.success("API Key ditemukan di st.secrets ✅")
    else:
        st.text_input(
            "OpenAI API Key",
            type="password",
            key="manual_api_key",
            help="Sebaiknya simpan di .streamlit/secrets.toml untuk deployment. "
                 "Input manual ini hanya untuk testing lokal.",
        )

    model = st.selectbox(
        "Model TTS",
        options=["gpt-4o-mini-tts", "tts-1", "tts-1-hd"],
        index=0,
    )

    audio_format = st.radio("Format Download", options=["mp3", "wav"], horizontal=True)

    speed = st.slider("Kecepatan Bicara (speed)", 0.5, 2.0, 1.0, 0.05)

    st.markdown("---")
    st.caption(
        "💡 Tips: teks maksimal ~4096 karakter per request (batas API). "
        "File MP3 umumnya jauh lebih kecil daripada WAV."
    )


# ================================================================
# 5. PILIH VOICE + PREVIEW SAMPLE (opsional)
# ================================================================
st.subheader("🗣️ Pilih Voice")

voice = st.selectbox(
    "Voice",
    options=list(VOICES.keys()),
    format_func=lambda v: f"{v} — {VOICES[v]}",
)
st.caption(VOICES[voice])

with st.expander("🔊 Preview sample suara (opsional)"):
    st.write("Klik tombol di bawah untuk mendengar contoh singkat dari voice yang dipilih.")
    preview_col1, preview_col2 = st.columns([1, 2])
    with preview_col1:
        preview_clicked = st.button("▶️ Putar Sample", key="preview_btn")
    with preview_col2:
        st.caption(f"Sample text: “{SAMPLE_TEXT}”")

    if preview_clicked:
        api_key = get_api_key()
        if not api_key:
            st.warning("⚠️ Masukkan API Key terlebih dahulu di sidebar.")
        else:
            # Cache preview per voice supaya tidak generate ulang setiap kali dibuka
            if voice not in st.session_state.voice_previews:
                try:
                    with st.spinner(f"Membuat sample suara '{voice}'..."):
                        client = OpenAI(api_key=api_key)
                        preview_bytes = call_tts_api(client, model, voice, SAMPLE_TEXT, 1.0, "mp3")
                        st.session_state.voice_previews[voice] = preview_bytes
                except AuthenticationError:
                    st.error("❌ API Key tidak valid. Periksa kembali API Key Anda.")
                except (APIError, APIConnectionError) as e:
                    st.error(f"❌ Gagal terhubung ke OpenAI API: {e}")
                except Exception as e:
                    st.error(f"❌ Terjadi kesalahan: {e}")

    if voice in st.session_state.voice_previews:
        st.audio(st.session_state.voice_previews[voice], format="audio/mp3")


# ================================================================
# 6. INPUT TEKS + CHARACTER COUNTER
# ================================================================
st.subheader("📝 Teks")

MAX_CHARS = 4096
text_input = st.text_area(
    "Masukkan teks yang ingin diubah menjadi suara",
    placeholder="Contoh: 'Selamat datang di aplikasi Text-to-Speech multi-voice!'",
    height=160,
    max_chars=MAX_CHARS,
)

char_count = len(text_input)
count_color = "red" if char_count >= MAX_CHARS else "gray"
st.markdown(
    f"<span style='color:{count_color};'>{char_count} / {MAX_CHARS} karakter</span>",
    unsafe_allow_html=True,
)

generate_clicked = st.button("🎬 Generate Audio", use_container_width=True)


# ================================================================
# 7. PROSES GENERATE (dengan progress indicator & error handling)
# ================================================================
if generate_clicked:
    api_key = get_api_key()

    # --- Error handling: teks kosong ---
    if not text_input.strip():
        st.warning("⚠️ Teks tidak boleh kosong. Silakan isi teks terlebih dahulu.")

    # --- Error handling: API key kosong ---
    elif not api_key:
        st.error("⚠️ OpenAI API Key belum diisi. Tambahkan di sidebar atau di st.secrets.")

    else:
        progress_bar = st.progress(0, text="Mempersiapkan permintaan...")
        try:
            client = OpenAI(api_key=api_key)

            progress_bar.progress(25, text="Mengirim teks ke OpenAI TTS API...")
            audio_bytes = call_tts_api(client, model, voice, text_input, speed, audio_format)

            progress_bar.progress(65, text="Memproses hasil audio...")

            size_kb = len(audio_bytes) / 1024
            duration_sec = get_audio_duration(audio_bytes, audio_format)

            # --- Error handling: file terlalu besar -> coba kompresi otomatis ---
            compressed_note = None
            if size_kb > 5000:
                progress_bar.progress(80, text="File besar terdeteksi, mencoba kompresi...")
                audio_bytes, was_compressed = maybe_compress(audio_bytes, audio_format, size_kb)
                if was_compressed:
                    size_kb = len(audio_bytes) / 1024
                    compressed_note = "File dikompresi otomatis (bitrate diturunkan ke 64kbps)."
                else:
                    compressed_note = (
                        "File cukup besar. Install 'pydub' + ffmpeg untuk kompresi otomatis."
                    )

            progress_bar.progress(100, text="Selesai!")

            filename = build_filename(voice, "mp3" if audio_format == "mp3" else "wav")

            # Simpan ke history (session_state) -> bisa didownload berkali-kali
            # tanpa generate ulang, karena bytes-nya sudah tersimpan di memori.
            st.session_state.history.insert(0, {
                "id": f"{voice}_{datetime.now().timestamp()}",
                "text_snippet": text_input[:60] + ("..." if len(text_input) > 60 else ""),
                "voice": voice,
                "model": model,
                "format": audio_format,
                "filename": filename,
                "bytes": audio_bytes,
                "size_kb": size_kb,
                "duration_sec": duration_sec,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "note": compressed_note,
            })

            progress_bar.empty()
            st.success("✅ Audio berhasil dibuat dan ditambahkan ke riwayat di bawah!")
            st.session_state.last_error = None

        except AuthenticationError:
            progress_bar.empty()
            st.session_state.last_error = "auth"
            st.error("❌ API Key tidak valid atau sudah kadaluarsa. Periksa kembali API Key Anda.")

        except (APIError, APIConnectionError) as e:
            progress_bar.empty()
            st.session_state.last_error = "api"
            st.error(f"❌ Gagal menghubungi OpenAI API: {e}")

        except Exception as e:
            progress_bar.empty()
            st.session_state.last_error = "general"
            st.error(f"❌ Terjadi kesalahan saat generate audio: {e}")

        # --- Tombol retry jika gagal ---
        if st.session_state.last_error:
            st.button("🔄 Coba Lagi", key="retry_btn")


# ================================================================
# 8. PREVIEW + DOWNLOAD HASIL TERBARU (paling atas history)
# ================================================================
if st.session_state.history:
    latest = st.session_state.history[0]

    st.markdown("---")
    st.subheader("🔊 Preview & Download Terbaru")

    mime = "audio/wav" if latest["format"] == "wav" else "audio/mp3"
    st.audio(latest["bytes"], format=mime)

    # Durasi ditampilkan SEBELUM tombol download
    if latest["duration_sec"] is not None:
        m, s = divmod(int(latest["duration_sec"]), 60)
        st.markdown(
            f'<span class="meta-pill">⏱️ Durasi: {m}:{s:02d}</span>'
            f'<span class="meta-pill">🎙️ Voice: {latest["voice"]}</span>'
            f'<span class="meta-pill">📦 Format: {latest["format"].upper()}</span>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<span class="meta-pill">🎙️ Voice: {latest["voice"]}</span>'
            f'<span class="meta-pill">📦 Format: {latest["format"].upper()}</span>',
            unsafe_allow_html=True,
        )

    # Ukuran file ditampilkan setelah generate
    st.info(f"✅ Ukuran file: **{latest['size_kb']:.1f} KB**  |  Nama file: `{latest['filename']}`")
    if latest.get("note"):
        st.warning(f"ℹ️ {latest['note']}")

    st.download_button(
        label="⬇️ Download Audio",
        data=latest["bytes"],
        file_name=latest["filename"],
        mime=mime,
        use_container_width=True,
        key=f"download_latest_{latest['id']}",
    )


# ================================================================
# 9. HISTORY DOWNLOAD (multi-download tanpa regenerate + ZIP semua)
# ================================================================
if st.session_state.history:
    st.markdown("---")
    st.subheader("🕘 Riwayat Audio")
    st.caption("Semua audio yang sudah dibuat tersimpan di sini selama sesi berjalan. "
               "Anda bisa mendownload ulang kapan saja tanpa generate ulang.")

    # --- Download semua sebagai ZIP ---
    if len(st.session_state.history) > 1:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for item in st.session_state.history:
                zf.writestr(item["filename"], item["bytes"])
        zip_buffer.seek(0)

        st.download_button(
            label=f"📦 Download Semua Riwayat ({len(st.session_state.history)} file) sebagai ZIP",
            data=zip_buffer,
            file_name=f"tts_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
            mime="application/zip",
            use_container_width=True,
            key="download_zip_all",
        )

    # --- Daftar item history, masing-masing dengan tombol download sendiri ---
    for idx, item in enumerate(st.session_state.history):
        with st.container():
            st.markdown('<div class="history-card">', unsafe_allow_html=True)
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{item['filename']}**")
                st.caption(f"“{item['text_snippet']}”")
                dur_str = ""
                if item["duration_sec"] is not None:
                    m, s = divmod(int(item["duration_sec"]), 60)
                    dur_str = f" • ⏱️ {m}:{s:02d}"
                st.caption(
                    f"🎙️ {item['voice']} • 📦 {item['format'].upper()} • "
                    f"💾 {item['size_kb']:.1f} KB{dur_str} • 🕐 {item['timestamp']}"
                )
            with col2:
                mime_i = "audio/wav" if item["format"] == "wav" else "audio/mp3"
                st.download_button(
                    label="⬇️ Download",
                    data=item["bytes"],
                    file_name=item["filename"],
                    mime=mime_i,
                    use_container_width=True,
                    key=f"download_history_{item['id']}_{idx}",
                )
            st.markdown('</div>', unsafe_allow_html=True)

    if st.button("🗑️ Bersihkan Riwayat", key="clear_history"):
        st.session_state.history = []
        st.rerun()


# ================================================================
# 10. FOOTER
# ================================================================
st.markdown("---")
st.caption(
    "Dibuat dengan Streamlit + OpenAI TTS API. "
    "Pastikan API Key memiliki akses ke endpoint `audio.speech`. "
    "Siap deploy ke Streamlit Community Cloud."
)