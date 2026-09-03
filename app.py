"""
================================================================
 Dialogue TTS Studio (GRATIS) — Percakapan 2 Orang -> 1 File Audio
 Menggunakan edge-tts (Microsoft Edge Text-to-Speech)
================================================================
Kenapa ganti dari OpenAI ke edge-tts?
  - edge-tts memakai layanan suara Microsoft Edge yang bisa diakses
    gratis lewat library Python `edge-tts`, TANPA API key dan
    TANPA biaya per karakter (tidak ada tagihan seperti OpenAI API).
  - Kualitas suaranya adalah voice neural (bukan robotic), dan
    tersedia banyak pilihan voice/bahasa termasuk Bahasa Indonesia.
  - Butuh koneksi internet saat generate (karena tetap memanggil
    layanan online Microsoft), tapi tidak butuh akun/API key/billing.

Fitur (sama seperti versi sebelumnya, hanya mesin TTS-nya yang beda):
  - Naskah percakapan 2 pembicara (format: "A: ..." / "B: ...")
  - Voice berbeda untuk tiap pembicara (bisa filter per bahasa)
  - Setiap baris digenerate lalu digabung jadi satu file audio
    dengan jeda singkat antar baris (pakai pydub)
  - Preview tiap baris (opsional) + preview gabungan sebelum download
  - Progress bar per baris saat proses generate
  - Download hasil akhir (MP3): conversation_[timestamp].mp3
  - Riwayat percakapan yang sudah dibuat, bisa didownload ulang

Install:
    pip install streamlit edge-tts pydub mutagen

Jalankan:
    streamlit run app.py

Catatan deployment (Streamlit Cloud):
    Tambahkan file packages.txt berisi "ffmpeg" di root project,
    karena pydub butuh ffmpeg untuk menggabungkan audio MP3.
================================================================
"""

import io
import re
import asyncio
from datetime import datetime

import streamlit as st

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False

try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False


# ================================================================
# 1. KONFIGURASI HALAMAN & CSS
# ================================================================
st.set_page_config(page_title="Dialogue TTS Studio (Gratis)", page_icon="🗣️", layout="centered")

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
    .free-badge {
        display: inline-block; padding: 0.25rem 0.7rem; border-radius: 999px;
        background: rgba(44, 182, 125, 0.15); color: #2CB67D; font-weight: 700;
        font-size: 0.75rem; margin-bottom: 0.6rem;
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
st.markdown('<span class="free-badge">✅ 100% Gratis — tanpa API key, tanpa billing (edge-tts)</span>', unsafe_allow_html=True)
st.markdown(
    '<div class="tts-subtitle">Ubah naskah percakapan 2 orang menjadi satu file audio '
    'dengan voice berbeda untuk tiap pembicara.</div>',
    unsafe_allow_html=True,
)

if not EDGE_TTS_AVAILABLE:
    st.error("⚠️ Library `edge-tts` tidak ditemukan. Install dengan: `pip install edge-tts`")
    st.stop()

if not PYDUB_AVAILABLE:
    st.error(
        "⚠️ Library `pydub` tidak ditemukan. Aplikasi ini butuh `pydub` + `ffmpeg` "
        "untuk menggabungkan audio tiap baris menjadi satu file. "
        "Install dengan `pip install pydub` dan pastikan `ffmpeg` terpasang di sistem "
        "(untuk Streamlit Cloud, tambahkan `ffmpeg` di file `packages.txt`)."
    )
    st.stop()


# ================================================================
# 2. DAFTAR VOICE (edge-tts) — kurasi + fallback offline
# ================================================================
# Voice andalan yang stabil tersedia di edge-tts (per pengetahuan saat ini).
# Daftar lengkap & terbaru sebaiknya diambil lewat fetch_all_voices() di bawah,
# karena Microsoft bisa menambah/mengubah voice sewaktu-waktu.
FALLBACK_VOICES = {
    "id-ID-ArdiNeural":   "🇮🇩 Indonesia — Pria",
    "id-ID-GadisNeural":  "🇮🇩 Indonesia — Wanita",
    "en-US-GuyNeural":    "🇺🇸 English (US) — Pria",
    "en-US-AriaNeural":   "🇺🇸 English (US) — Wanita",
    "en-US-JennyNeural":  "🇺🇸 English (US) — Wanita",
    "en-GB-RyanNeural":   "🇬🇧 English (UK) — Pria",
    "en-GB-SoniaNeural":  "🇬🇧 English (UK) — Wanita",
}

LOCALE_FILTERS = {
    "Semua": None,
    "Indonesia (id-ID)": "id-ID",
    "English - US (en-US)": "en-US",
    "English - UK (en-GB)": "en-GB",
    "English - AU (en-AU)": "en-AU",
    "Japanese (ja-JP)": "ja-JP",
    "Korean (ko-KR)": "ko-KR",
    "Mandarin (zh-CN)": "zh-CN",
    "Arabic (ar-SA)": "ar-SA",
    "Spanish (es-ES)": "es-ES",
    "French (fr-FR)": "fr-FR",
    "German (de-DE)": "de-DE",
    "Hindi (hi-IN)": "hi-IN",
}

DEFAULT_SCRIPT = """A: Halo, apa kabar hari ini?
B: Baik banget! Kamu lagi ngapain?
A: Lagi coba bikin aplikasi text-to-speech buat percakapan dua orang, versi gratis.
B: Wah keren, jadi nggak perlu bayar API ya?
A: Betul, pakai edge-tts jadi gratis tapi suaranya tetap natural."""


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_all_voices():
    """
    Ambil daftar lengkap voice dari edge-tts (butuh internet).
    Return: dict {ShortName: "Locale — Gender"} atau None jika gagal.
    Di-cache 1 jam supaya tidak fetch berulang-ulang.
    """
    try:
        voices = asyncio.run(edge_tts.list_voices())
        result = {}
        for v in voices:
            short_name = v["ShortName"]
            locale = v["Locale"]
            gender = v["Gender"]
            result[short_name] = f"{locale} — {gender}"
        return result
    except Exception:
        return None


def get_voice_options(locale_filter: str | None, all_voices: dict | None):
    """Kembalikan dict voice sesuai filter locale, fallback ke daftar statis kalau fetch gagal."""
    source = all_voices if all_voices else FALLBACK_VOICES
    if not locale_filter:
        return source
    filtered = {k: v for k, v in source.items() if k.lower().startswith(locale_filter.lower())}
    return filtered if filtered else source


# ================================================================
# 3. SESSION STATE
# ================================================================
if "history" not in st.session_state:
    st.session_state.history = []
if "last_error" not in st.session_state:
    st.session_state.last_error = None


def parse_script(script: str):
    """Parse naskah menjadi list (speaker, text). Format: 'Label: teks' per baris."""
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

    speakers_found = sorted(set(s for s, _ in lines), key=lambda s: s.lower())
    if len(speakers_found) > 2:
        errors.append(
            f"Ditemukan {len(speakers_found)} label pembicara berbeda: {speakers_found}. "
            "Aplikasi ini hanya mendukung maksimal 2 pembicara."
        )

    return lines, errors, speakers_found


async def _synthesize_async(text: str, voice: str, rate_pct: int) -> bytes:
    """Generate audio (bytes MP3) dari satu baris teks memakai edge-tts."""
    rate_str = f"{'+' if rate_pct >= 0 else ''}{rate_pct}%"
    communicate = edge_tts.Communicate(text, voice, rate=rate_str)
    audio_chunks = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.extend(chunk["data"])
    return bytes(audio_chunks)


def synthesize(text: str, voice: str, rate_pct: int) -> bytes:
    """Wrapper sinkron untuk dipanggil dari kode Streamlit biasa."""
    return asyncio.run(_synthesize_async(text, voice, rate_pct))


def build_filename() -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"conversation_{ts}.mp3"


# ================================================================
# 4. SIDEBAR — KONFIGURASI VOICE PER PEMBICARA (GRATIS, TANPA API KEY)
# ================================================================
with st.sidebar:
    st.header("⚙️ Konfigurasi")
    st.success("Gratis — tidak perlu API key ✅")

    with st.spinner("Memuat daftar voice..."):
        all_voices = fetch_all_voices()
    if all_voices is None:
        st.warning("⚠️ Gagal mengambil daftar voice online. Memakai daftar cadangan (terbatas).")

    rate_pct = st.slider("Kecepatan Bicara (rate %)", -50, 50, 0, 5,
                          help="0% = normal. Negatif = lebih lambat, positif = lebih cepat.")
    gap_ms = st.slider("Jeda antar baris (ms)", 0, 1500, 350, 50)

    st.markdown("---")
    st.subheader("🗣️ Voice Pembicara A")
    locale_a = st.selectbox("Filter bahasa A", options=list(LOCALE_FILTERS.keys()),
                             index=1, key="locale_a")
    voices_a = get_voice_options(LOCALE_FILTERS[locale_a], all_voices)
    voice_a = st.selectbox(
        "Voice A", options=list(voices_a.keys()),
        format_func=lambda v: f"{v} — {voices_a[v]}", key="voice_a",
    )

    st.subheader("🗣️ Voice Pembicara B")
    locale_b = st.selectbox("Filter bahasa B", options=list(LOCALE_FILTERS.keys()),
                             index=1, key="locale_b")
    voices_b = get_voice_options(LOCALE_FILTERS[locale_b], all_voices)
    default_b_index = 1 if len(voices_b) > 1 else 0
    voice_b = st.selectbox(
        "Voice B", options=list(voices_b.keys()),
        format_func=lambda v: f"{v} — {voices_b[v]}", index=default_b_index, key="voice_b",
    )

    st.caption(
        "💡 Label pembicara di naskah (mis. 'A' dan 'B') dipetakan berurutan "
        "ke Voice A dan Voice B berdasarkan urutan kemunculan pertama."
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
    lines, errors, speakers_found = parse_script(script)

    if not script.strip():
        st.warning("⚠️ Naskah tidak boleh kosong.")
    elif errors:
        st.error("⚠️ Perbaiki dulu naskah Anda:")
        for e in errors:
            st.write(f"- {e}")
    elif not lines:
        st.warning("⚠️ Tidak ada baris valid yang bisa diproses.")
    else:
        voice_map = {}
        if len(speakers_found) >= 1:
            voice_map[speakers_found[0]] = voice_a
        if len(speakers_found) >= 2:
            voice_map[speakers_found[1]] = voice_b

        progress_bar = st.progress(0, text="Mempersiapkan...")
        try:
            combined = AudioSegment.silent(duration=0)
            silence_gap = AudioSegment.silent(duration=gap_ms)
            line_previews = []

            total = len(lines)
            for idx, (speaker, text) in enumerate(lines):
                pct = int((idx / total) * 90)
                progress_bar.progress(pct, text=f"Generate baris {idx + 1}/{total} ({speaker})...")

                voice_for_line = voice_map.get(speaker, voice_a)
                audio_bytes = synthesize(text, voice_for_line, rate_pct)

                if not audio_bytes:
                    raise RuntimeError(
                        f"Gagal generate baris {idx + 1} (tidak ada audio dikembalikan). "
                        "Coba lagi atau periksa koneksi internet."
                    )

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
            st.success(f"✅ Percakapan berhasil dibuat dari {total} baris — gratis, tanpa biaya API!")
            st.session_state.last_error = None

        except Exception as e:
            progress_bar.empty()
            st.session_state.last_error = "general"
            st.error(
                f"❌ Terjadi kesalahan saat generate audio: {e}\n\n"
                "Penyebab umum: koneksi internet terputus, atau nama voice tidak valid "
                "(coba pilih ulang voice di sidebar)."
            )
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
    "Dibuat dengan Streamlit + edge-tts (gratis, tanpa API key) + pydub. "
    "Setiap baris naskah digenerate terpisah lalu digabung jadi satu file audio."
)