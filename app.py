"""
================================================================
 Dialogue TTS Studio — Percakapan 2 Orang -> 1 File Audio
 (Streamlit + OpenAI TTS API)
================================================================
Fitur:
  - Naskah percakapan 2 pembicara (format: "A: ..." / "B: ...")
  - Voice berbeda untuk tiap pembicara (multi-voice)
  - Setiap baris di-generate lalu digabung jadi satu file audio
    dengan jeda singkat antar baris (pakai pydub)
  - Preview tiap baris (opsional) + preview gabungan sebelum download
  - Progress bar per baris saat proses generate
  - Download hasil akhir (MP3), nama file: conversation_[timestamp].mp3
  - Riwayat percakapan yang sudah dibuat, bisa didownload ulang
  - Error handling: naskah kosong, format baris salah, API key invalid, dst.

Jalankan:
    streamlit run app.py

Catatan deployment (Streamlit Cloud):
    Tambahkan file packages.txt berisi "ffmpeg" di root project,
    karena pydub butuh ffmpeg untuk menggabungkan audio MP3.
================================================================
"""

import io
import re
from datetime import datetime

import streamlit as st
from openai import OpenAI, AuthenticationError, APIError, APIConnectionError

try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False

try:
    from mutagen.mp3 import MP3
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False


# ================================================================
# 1. KONFIGURASI HALAMAN & CSS
# ================================================================
st.set_page_config(page_title="Dialogue TTS Studio", page_icon="🗣️", layout="centered")

st.markdown(
    """
    <style>
    .tts-title {
        font-size: clamp(1.4rem, 4vw, 2.1rem);
        font-weight: 800;
        background: linear-gradient(90deg, #7F5AF0, #2CB67D);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .tts-subtitle { color: #9AA0A6; margin-bottom: 1rem; }
    div.stButton > button {
        width: 100%; border-radius: 12px; border: none;
        padding: 0.7rem 1.1rem; font-weight: 700;
        background: linear-gradient(90deg, #7F5AF0, #6246EA); color: white;
        box-shadow: 0 4px 14px rgba(127, 90, 240, 0.35);
    }
    div.stButton > button:hover { transform: translateY(-2px); }
    div.stDownloadButton > button {
        width: 100%; border-radius: 12px; border: 2px solid #2CB67D;
        padding: 0.7rem 1.1rem; font-weight: 700;
        background: linear-gradient(90deg, #2CB67D, #16A085); color: white;
        box-shadow: 0 4px 14px rgba(44, 182, 125, 0.35);
    }
    div.stDownloadButton > button:hover { transform: translateY(-2px); }
    .meta-pill {
        display: inline-block; padding: 0.3rem 0.8rem; margin: 0.15rem 0.25rem 0.15rem 0;
        border-radius: 999px; background: rgba(127, 90, 240, 0.12);
        color: #7F5AF0; font-weight: 600; font-size: 0.8rem;
    }
    .line-a { border-left: 4px solid #7F5AF0; padding-left: 0.6rem; margin-bottom: 0.35rem; }
    .line-b { border-left: 4px solid #2CB67D; padding-left: 0.6rem; margin-bottom: 0.35rem; }
    @media (max-width: 640px) {
        .tts-title { font-size: 1.3rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="tts-title">🗣️ Dialogue TTS Studio</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="tts-subtitle">Ubah naskah percakapan 2 orang menjadi satu file audio '
    'dengan voice berbeda untuk tiap pembicara.</div>',
    unsafe_allow_html=True,
)

if not PYDUB_AVAILABLE:
    st.error(
        "⚠️ Library `pydub` tidak ditemukan. Aplikasi ini butuh `pydub` + `ffmpeg` "
        "untuk menggabungkan audio tiap baris menjadi satu file. "
        "Install dengan `pip install pydub` dan pastikan `ffmpeg` terpasang di sistem "
        "(untuk Streamlit Cloud, tambahkan `ffmpeg` di file `packages.txt`)."
    )
    st.stop()


# ================================================================
# 2. DATA VOICE
# ================================================================
VOICES = {
    "alloy":   "Netral & seimbang",
    "echo":    "Tenang & jernih",
    "fable":   "Hangat, gaya bercerita",
    "onyx":    "Dalam & tegas",
    "nova":    "Ringan & energik",
    "shimmer": "Lembut & ramah",
    "coral":   "Ekspresif & hangat",
    "sage":    "Kalem & meyakinkan",
    "verse":   "Dinamis & ekspresif",
    "ballad":  "Lembut & melodius",
    "ash":     "Jelas & profesional",
}

DEFAULT_SCRIPT = """A: Halo, apa kabar hari ini?
B: Baik banget! Kamu lagi ngapain?
A: Lagi coba bikin aplikasi text-to-speech buat percakapan dua orang.
B: Wah keren, jadi satu file audio langsung ya?
A: Betul, tinggal generate terus bisa langsung didownload."""


# ================================================================
# 3. SESSION STATE
# ================================================================
if "history" not in st.session_state:
    st.session_state.history = []
if "last_error" not in st.session_state:
    st.session_state.last_error = None


def get_api_key() -> str:
    key = st.secrets.get("OPENAI_API_KEY", "") if hasattr(st, "secrets") else ""
    if not key:
        key = st.session_state.get("manual_api_key", "")
    return key


def parse_script(script: str):
    """
    Parse naskah menjadi list of (speaker, text).
    Format yang diterima per baris: 'A: teks...' atau 'B: teks...'
    (case-insensitive, boleh pakai nama lain asal konsisten dengan 2 label).
    Return: (lines, errors)
    """
    lines = []
    errors = []
    pattern = re.compile(r"^\s*([A-Za-z0-9_]+)\s*:\s*(.+)$")

    for i, raw_line in enumerate(script.splitlines(), start=1):
        if not raw_line.strip():
            continue
        match = pattern.match(raw_line)
        if not match:
            errors.append(f"Baris {i}: format tidak dikenali -> \"{raw_line.strip()}\"")
            continue
        speaker, text = match.group(1).strip(), match.group(2).strip()
        lines.append((speaker, text))

    # Validasi: hanya boleh maksimal 2 label pembicara berbeda
    speakers_found = sorted(set(s for s, _ in lines), key=lambda s: s.lower())
    if len(speakers_found) > 2:
        errors.append(
            f"Ditemukan {len(speakers_found)} label pembicara berbeda: {speakers_found}. "
            "Aplikasi ini hanya mendukung maksimal 2 pembicara."
        )

    return lines, errors, speakers_found


def call_tts_api(client: OpenAI, model: str, voice: str, text: str, speed: float) -> bytes:
    response = client.audio.speech.create(
        model=model, voice=voice, input=text, speed=speed, response_format="mp3",
    )
    return response.content


def build_filename() -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"conversation_{ts}.mp3"


# ================================================================
# 4. SIDEBAR — KONFIGURASI VOICE PER PEMBICARA
# ================================================================
with st.sidebar:
    st.header("⚙️ Konfigurasi")

    secret_key = st.secrets.get("OPENAI_API_KEY", "") if hasattr(st, "secrets") else ""
    if secret_key:
        st.success("API Key ditemukan di st.secrets ✅")
    else:
        st.text_input(
            "OpenAI API Key", type="password", key="manual_api_key",
            help="Sebaiknya simpan di .streamlit/secrets.toml untuk deployment.",
        )

    model = st.selectbox("Model TTS", options=["gpt-4o-mini-tts", "tts-1", "tts-1-hd"], index=0)
    speed = st.slider("Kecepatan Bicara", 0.5, 2.0, 1.0, 0.05)
    gap_ms = st.slider("Jeda antar baris (ms)", 0, 1500, 350, 50)

    st.markdown("---")
    st.subheader("🗣️ Voice per Pembicara")
    voice_a = st.selectbox(
        "Voice untuk Pembicara A", options=list(VOICES.keys()),
        format_func=lambda v: f"{v} — {VOICES[v]}", index=0,
    )
    voice_b = st.selectbox(
        "Voice untuk Pembicara B", options=list(VOICES.keys()),
        format_func=lambda v: f"{v} — {VOICES[v]}", index=4,
    )

    st.caption(
        "💡 Label pembicara di naskah (mis. 'A' dan 'B') akan dipetakan "
        "berurutan ke voice di atas berdasarkan urutan kemunculan pertama."
    )


# ================================================================
# 5. INPUT NASKAH PERCAKAPAN
# ================================================================
st.subheader("📝 Naskah Percakapan")
st.caption(
    "Tulis setiap baris dengan format `Label: teks`. Gunakan hanya 2 label berbeda "
    "(misalnya `A` dan `B`, atau nama tokoh)."
)

script = st.text_area("Naskah", value=DEFAULT_SCRIPT, height=220)
char_count = len(script)
st.caption(f"{char_count} karakter total")

with st.expander("👀 Preview parsing naskah"):
    parsed_lines, parse_errors, speakers_found = parse_script(script)
    if parse_errors:
        for e in parse_errors:
            st.error(e)
    if parsed_lines:
        for spk, text in parsed_lines:
            css_class = "line-a" if speakers_found and spk == speakers_found[0] else "line-b"
            st.markdown(f'<div class="{css_class}"><b>{spk}:</b> {text}</div>', unsafe_allow_html=True)

generate_clicked = st.button("🎬 Generate Percakapan", use_container_width=True)


# ================================================================
# 6. PROSES GENERATE
# ================================================================
if generate_clicked:
    api_key = get_api_key()
    lines, errors, speakers_found = parse_script(script)

    if not script.strip():
        st.warning("⚠️ Naskah tidak boleh kosong.")
    elif not api_key:
        st.error("⚠️ OpenAI API Key belum diisi. Tambahkan di sidebar atau di st.secrets.")
    elif errors:
        st.error("⚠️ Perbaiki dulu naskah Anda:")
        for e in errors:
            st.write(f"- {e}")
    elif not lines:
        st.warning("⚠️ Tidak ada baris valid yang bisa diproses.")
    else:
        # Petakan label pembicara -> voice, berdasarkan urutan kemunculan pertama
        voice_map = {}
        if len(speakers_found) >= 1:
            voice_map[speakers_found[0]] = voice_a
        if len(speakers_found) >= 2:
            voice_map[speakers_found[1]] = voice_b

        progress_bar = st.progress(0, text="Mempersiapkan...")
        try:
            client = OpenAI(api_key=api_key)
            combined = AudioSegment.silent(duration=0)
            silence_gap = AudioSegment.silent(duration=gap_ms)
            line_previews = []  # simpan bytes tiap baris (opsional, buat expander)

            total = len(lines)
            for idx, (speaker, text) in enumerate(lines):
                pct = int((idx / total) * 90)
                progress_bar.progress(pct, text=f"Generate baris {idx + 1}/{total} ({speaker})...")

                voice_for_line = voice_map.get(speaker, voice_a)
                audio_bytes = call_tts_api(client, model, voice_for_line, text, speed)
                line_previews.append({"speaker": speaker, "text": text, "bytes": audio_bytes})

                segment = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
                combined += segment
                if idx < total - 1:
                    combined += silence_gap

            progress_bar.progress(95, text="Menggabungkan audio...")
            out_buffer = io.BytesIO()
            combined.export(out_buffer, format="mp3")
            final_bytes = out_buffer.getvalue()

            size_kb = len(final_bytes) / 1024
            duration_sec = len(combined) / 1000.0
            filename = build_filename()

            st.session_state.history.insert(0, {
                "id": f"conv_{datetime.now().timestamp()}",
                "filename": filename,
                "bytes": final_bytes,
                "size_kb": size_kb,
                "duration_sec": duration_sec,
                "num_lines": total,
                "speakers": speakers_found,
                "voice_map": voice_map,
                "line_previews": line_previews,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })

            progress_bar.progress(100, text="Selesai!")
            progress_bar.empty()
            st.success(f"✅ Percakapan berhasil dibuat dari {total} baris!")
            st.session_state.last_error = None

        except AuthenticationError:
            progress_bar.empty()
            st.session_state.last_error = "auth"
            st.error("❌ API Key tidak valid atau sudah kadaluarsa.")

        except (APIError, APIConnectionError) as e:
            progress_bar.empty()
            st.session_state.last_error = "api"
            st.error(f"❌ Gagal menghubungi OpenAI API: {e}")

        except Exception as e:
            progress_bar.empty()
            st.session_state.last_error = "general"
            st.error(f"❌ Terjadi kesalahan saat generate audio: {e}")

        if st.session_state.last_error:
            st.button("🔄 Coba Lagi", key="retry_btn")


# ================================================================
# 7. PREVIEW + DOWNLOAD HASIL TERBARU
# ================================================================
if st.session_state.history:
    latest = st.session_state.history[0]

    st.markdown("---")
    st.subheader("🔊 Preview & Download Percakapan Terbaru")

    st.audio(latest["bytes"], format="audio/mp3")

    m, s = divmod(int(latest["duration_sec"]), 60)
    st.markdown(
        f'<span class="meta-pill">⏱️ Durasi: {m}:{s:02d}</span>'
        f'<span class="meta-pill">💬 {latest["num_lines"]} baris</span>'
        f'<span class="meta-pill">🗣️ Pembicara: {", ".join(latest["speakers"])}</span>',
        unsafe_allow_html=True,
    )
    st.info(f"✅ Ukuran file: **{latest['size_kb']:.1f} KB**  |  Nama file: `{latest['filename']}`")

    st.download_button(
        label="⬇️ Download Percakapan (MP3)",
        data=latest["bytes"],
        file_name=latest["filename"],
        mime="audio/mp3",
        use_container_width=True,
        key=f"download_latest_{latest['id']}",
    )

    with st.expander("🔍 Dengarkan per baris (opsional)"):
        for i, line in enumerate(latest["line_previews"]):
            st.caption(f"**{line['speaker']}:** {line['text']}")
            st.audio(line["bytes"], format="audio/mp3")


# ================================================================
# 8. HISTORY PERCAKAPAN
# ================================================================
if st.session_state.history:
    st.markdown("---")
    st.subheader("🕘 Riwayat Percakapan")
    st.caption("Semua percakapan yang sudah dibuat pada sesi ini bisa didownload ulang tanpa generate ulang.")

    for idx, item in enumerate(st.session_state.history):
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"**{item['filename']}**")
            m, s = divmod(int(item["duration_sec"]), 60)
            st.caption(
                f"💬 {item['num_lines']} baris • ⏱️ {m}:{s:02d} • "
                f"💾 {item['size_kb']:.1f} KB • 🕐 {item['timestamp']}"
            )
        with col2:
            st.download_button(
                label="⬇️ Download",
                data=item["bytes"],
                file_name=item["filename"],
                mime="audio/mp3",
                use_container_width=True,
                key=f"download_history_{item['id']}_{idx}",
            )

    if st.button("🗑️ Bersihkan Riwayat", key="clear_history"):
        st.session_state.history = []
        st.rerun()


# ================================================================
# 9. FOOTER
# ================================================================
st.markdown("---")
st.caption(
    "Dibuat dengan Streamlit + OpenAI TTS API + pydub. "
    "Setiap baris naskah digenerate terpisah lalu digabung jadi satu file audio."
)