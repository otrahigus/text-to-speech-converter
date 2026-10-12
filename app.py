"""
================================================================
 Dialogue TTS Studio (GRATIS) — Percakapan 2 Orang -> 1 File Audio
================================================================
Mesin suara (semua gratis, tanpa API key):
  1. edge-tts  (utama)  : voice neural Microsoft Edge, banyak pilihan voice
  2. gTTS      (cadangan): dipakai otomatis jika edge-tts gagal/ditolak
                           (misalnya error 403 dari IP server cloud)

Perbaikan di versi ini:
  - Retry 3x untuk edge-tts + fallback otomatis ke gTTS
  - Kegagalan ambil daftar voice tidak lagi ter-cache
  - Default Bahasa Inggris (naskah, filter en-US, voice Guy & Aria)
  - Detail error ditampilkan agar mudah didiagnosis

Jalankan lokal:   streamlit run app.py
Deploy Cloud    : butuh packages.txt berisi "ffmpeg"
================================================================
"""

import io
import re
import time
import asyncio
import traceback
from datetime import datetime

import streamlit as st

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False

try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False

try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False


# ================================================================
# 1. HALAMAN & CSS
# ================================================================
st.set_page_config(page_title="Dialogue TTS Studio (Gratis)", page_icon="🗣️", layout="centered")

st.markdown(
    """
    <style>
    .tts-title {
        font-size: clamp(1.4rem, 4vw, 2.1rem); font-weight: 800;
        background: linear-gradient(90deg, #7F5AF0, #2CB67D);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
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
    @media (max-width: 640px) { .tts-title { font-size: 1.3rem; } }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="tts-title">🗣️ Dialogue TTS Studio</div>', unsafe_allow_html=True)
st.markdown('<span class="free-badge">✅ 100% Gratis — tanpa API key, tanpa billing</span>', unsafe_allow_html=True)
st.markdown(
    '<div class="tts-subtitle">Ubah naskah percakapan 2 orang menjadi satu file audio '
    'dengan voice berbeda untuk tiap pembicara.</div>',
    unsafe_allow_html=True,
)

if not EDGE_TTS_AVAILABLE and not GTTS_AVAILABLE:
    st.error("⚠️ Tidak ada mesin TTS terpasang. Install: `pip install edge-tts gTTS`")
    st.stop()

if not PYDUB_AVAILABLE:
    st.error(
        "⚠️ Library `pydub` tidak ditemukan. Install `pydub` dan pastikan `ffmpeg` terpasang "
        "(Streamlit Cloud: tambahkan `ffmpeg` di `packages.txt`)."
    )
    st.stop()


# ================================================================
# 2. DAFTAR VOICE
# ================================================================
FALLBACK_VOICES = {
    "en-US-GuyNeural":    "en-US — Male",
    "en-US-AriaNeural":   "en-US — Female",
    "en-US-JennyNeural":  "en-US — Female",
    "en-GB-RyanNeural":   "en-GB — Male",
    "en-GB-SoniaNeural":  "en-GB — Female",
    "en-AU-WilliamNeural": "en-AU — Male",
    "en-AU-NatashaNeural": "en-AU — Female",
    "id-ID-ArdiNeural":   "id-ID — Male",
    "id-ID-GadisNeural":  "id-ID — Female",
}

LOCALE_FILTERS = {
    "English - US (en-US)": "en-US",
    "English - UK (en-GB)": "en-GB",
    "English - AU (en-AU)": "en-AU",
    "Indonesia (id-ID)": "id-ID",
    "Semua bahasa": None,
}

DEFAULT_SCRIPT = """A: Hi, how are you today?
B: I'm doing great, thanks! How about you?
A: Pretty good. I'm testing a text-to-speech app for two-person conversations.
B: That sounds useful. Does it create a single audio file?
A: Yes, and you can download it right after it's generated."""

# Aksen gTTS untuk fallback: pembicara A = US, pembicara B = UK
GTTS_ACCENTS = ["com", "co.uk"]


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_voices_raw():
    """Exception TIDAK di-cache oleh Streamlit, jadi kegagalan akan dicoba lagi."""
    voices = asyncio.run(edge_tts.list_voices())
    return {v["ShortName"]: f'{v["Locale"]} — {v["Gender"]}' for v in voices}


def fetch_all_voices():
    if not EDGE_TTS_AVAILABLE:
        return None
    try:
        return _fetch_voices_raw()
    except Exception:
        return None


def get_voice_options(locale_filter, all_voices):
    source = all_voices if all_voices else FALLBACK_VOICES
    if not locale_filter:
        return source
    filtered = {k: v for k, v in source.items() if k.lower().startswith(locale_filter.lower())}
    return filtered if filtered else source


def pick_index(options, preferred, fallback_index=0):
    keys = list(options.keys())
    return keys.index(preferred) if preferred in keys else min(fallback_index, len(keys) - 1)


# ================================================================
# 3. STATE & HELPER
# ================================================================
if "history" not in st.session_state:
    st.session_state.history = []


def parse_script(script: str):
    lines, errors = [], []
    pattern = re.compile(r"^\s*([A-Za-z0-9_]+)\s*:\s*(.+)$")
    for i, raw_line in enumerate(script.splitlines(), start=1):
        if not raw_line.strip():
            continue
        match = pattern.match(raw_line)
        if not match:
            errors.append(f'Baris {i}: format tidak dikenali -> "{raw_line.strip()}"')
            continue
        lines.append((match.group(1).strip(), match.group(2).strip()))

    speakers_found = []
    for s, _ in lines:  # urut kemunculan pertama
        if s not in speakers_found:
            speakers_found.append(s)
    if len(speakers_found) > 2:
        errors.append(
            f"Ditemukan {len(speakers_found)} label pembicara: {speakers_found}. Maksimal 2 pembicara."
        )
    return lines, errors, speakers_found


async def _edge_async(text, voice, rate_pct):
    rate_str = f"{'+' if rate_pct >= 0 else ''}{rate_pct}%"
    communicate = edge_tts.Communicate(text, voice, rate=rate_str)
    buf = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.extend(chunk["data"])
    return bytes(buf)


def synth_edge(text, voice, rate_pct):
    return asyncio.run(_edge_async(text, voice, rate_pct))


def synth_gtts(text, speaker_index, lang="en"):
    buf = io.BytesIO()
    tld = GTTS_ACCENTS[speaker_index % len(GTTS_ACCENTS)]
    gTTS(text=text, lang=lang, tld=tld).write_to_fp(buf)
    return buf.getvalue()


def synthesize_line(text, voice, rate_pct, speaker_index, gtts_lang):
    """
    Coba edge-tts sampai 3x. Jika tetap gagal, pakai gTTS.
    Return: (audio_bytes, engine_name, error_text_or_None)
    """
    last_err = None
    if EDGE_TTS_AVAILABLE:
        for attempt in range(3):
            try:
                data = synth_edge(text, voice, rate_pct)
                if data:
                    return data, "edge-tts", None
                last_err = "edge-tts mengembalikan audio kosong"
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
            time.sleep(1.0 * (attempt + 1))

    if GTTS_AVAILABLE:
        try:
            return synth_gtts(text, speaker_index, gtts_lang), "gTTS", last_err
        except Exception as e:
            last_err = f"{last_err or ''} | gTTS: {type(e).__name__}: {e}"

    raise RuntimeError(last_err or "Semua mesin TTS gagal.")


def build_filename():
    return f"conversation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"


# ================================================================
# 4. SIDEBAR
# ================================================================
with st.sidebar:
    st.header("⚙️ Konfigurasi")
    st.success("Gratis — tidak perlu API key ✅")

    all_voices = fetch_all_voices()
    if all_voices is None:
        st.warning("⚠️ Daftar voice online tidak bisa diambil. Memakai daftar cadangan.")

    rate_pct = st.slider("Kecepatan Bicara (rate %)", -50, 50, 0, 5,
                         help="0% = normal. Hanya berlaku untuk edge-tts.")
    gap_ms = st.slider("Jeda antar baris (ms)", 0, 1500, 350, 50)

    st.markdown("---")
    st.subheader("🗣️ Voice Pembicara A")
    locale_a = st.selectbox("Filter bahasa A", list(LOCALE_FILTERS.keys()), index=0, key="locale_a")
    voices_a = get_voice_options(LOCALE_FILTERS[locale_a], all_voices)
    voice_a = st.selectbox(
        "Voice A", list(voices_a.keys()),
        index=pick_index(voices_a, "en-US-GuyNeural"),
        format_func=lambda v: f"{v} — {voices_a[v]}", key="voice_a",
    )

    st.subheader("🗣️ Voice Pembicara B")
    locale_b = st.selectbox("Filter bahasa B", list(LOCALE_FILTERS.keys()), index=0, key="locale_b")
    voices_b = get_voice_options(LOCALE_FILTERS[locale_b], all_voices)
    voice_b = st.selectbox(
        "Voice B", list(voices_b.keys()),
        index=pick_index(voices_b, "en-US-AriaNeural", 1),
        format_func=lambda v: f"{v} — {voices_b[v]}", key="voice_b",
    )

    gtts_lang = st.selectbox(
        "Bahasa cadangan (gTTS)", ["en", "id"], index=0,
        help="Dipakai hanya jika edge-tts gagal.",
    )
    st.caption("Label pembicara pertama di naskah memakai Voice A, label kedua memakai Voice B.")


# ================================================================
# 5. INPUT NASKAH
# ================================================================
st.subheader("📝 Naskah Percakapan")
st.caption("Format per baris: `Label: teks`. Maksimal 2 label berbeda (mis. `A` dan `B`).")

script = st.text_area("Naskah", value=DEFAULT_SCRIPT, height=220)
st.caption(f"{len(script)} karakter total")

with st.expander("👀 Preview parsing naskah"):
    parsed_lines, parse_errors, speakers_preview = parse_script(script)
    for e in parse_errors:
        st.error(e)
    for spk, text in parsed_lines:
        css = "line-a" if speakers_preview and spk == speakers_preview[0] else "line-b"
        st.markdown(f'<div class="{css}"><b>{spk}:</b> {text}</div>', unsafe_allow_html=True)

generate_clicked = st.button("🎬 Generate Percakapan", use_container_width=True)


# ================================================================
# 6. GENERATE
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
            engines_used = set()
            edge_errors = []

            total = len(lines)
            for idx, (speaker, text) in enumerate(lines):
                progress_bar.progress(int(idx / total * 90),
                                      text=f"Generate baris {idx + 1}/{total} ({speaker})...")

                spk_index = speakers_found.index(speaker)
                data, engine, err = synthesize_line(
                    text, voice_map.get(speaker, voice_a), rate_pct, spk_index, gtts_lang
                )
                engines_used.add(engine)
                if err and engine != "edge-tts":
                    edge_errors.append(err)

                line_previews.append({"speaker": speaker, "text": text, "bytes": data})
                combined += AudioSegment.from_file(io.BytesIO(data), format="mp3")
                if idx < total - 1:
                    combined += silence_gap

            progress_bar.progress(95, text="Menggabungkan audio...")
            out = io.BytesIO()
            combined.export(out, format="mp3")
            final_bytes = out.getvalue()

            st.session_state.history.insert(0, {
                "id": f"conv_{datetime.now().timestamp()}",
                "filename": build_filename(),
                "bytes": final_bytes,
                "size_kb": len(final_bytes) / 1024,
                "duration_sec": len(combined) / 1000.0,
                "num_lines": total,
                "speakers": speakers_found,
                "engines": sorted(engines_used),
                "line_previews": line_previews,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })

            progress_bar.empty()
            st.success(f"✅ Percakapan berhasil dibuat dari {total} baris!")
            if "gTTS" in engines_used:
                st.warning(
                    "ℹ️ edge-tts gagal/ditolak, sebagian atau seluruh audio memakai mesin cadangan gTTS "
                    "(voice lebih sederhana; Pembicara A aksen US, B aksen UK)."
                )
                with st.expander("Detail error edge-tts"):
                    st.code(edge_errors[0] if edge_errors else "-")

        except Exception as e:
            progress_bar.empty()
            st.error(
                f"❌ Gagal generate audio: {e}\n\n"
                "Cek koneksi internet, pilih ulang voice, lalu klik Generate lagi."
            )
            with st.expander("Detail teknis (untuk debugging)"):
                st.code(traceback.format_exc())


# ================================================================
# 7. PREVIEW & DOWNLOAD TERBARU
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
        f'<span class="meta-pill">🎙️ Mesin: {", ".join(latest["engines"])}</span>',
        unsafe_allow_html=True,
    )
    st.info(f"✅ Ukuran file: **{latest['size_kb']:.1f} KB**  |  Nama file: `{latest['filename']}`")

    st.download_button(
        "⬇️ Download Percakapan (MP3)", data=latest["bytes"], file_name=latest["filename"],
        mime="audio/mp3", use_container_width=True, key=f"download_latest_{latest['id']}",
    )

    with st.expander("🔍 Dengarkan per baris (opsional)"):
        for line in latest["line_previews"]:
            st.caption(f"**{line['speaker']}:** {line['text']}")
            st.audio(line["bytes"], format="audio/mp3")


# ================================================================
# 8. RIWAYAT
# ================================================================
if st.session_state.history:
    st.markdown("---")
    st.subheader("🕘 Riwayat Percakapan")
    st.caption("Download ulang kapan saja tanpa generate ulang (selama sesi berjalan).")

    for idx, item in enumerate(st.session_state.history):
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"**{item['filename']}**")
            m, s = divmod(int(item["duration_sec"]), 60)
            st.caption(f"💬 {item['num_lines']} baris • ⏱️ {m}:{s:02d} • "
                       f"💾 {item['size_kb']:.1f} KB • 🕐 {item['timestamp']}")
        with col2:
            st.download_button(
                "⬇️ Download", data=item["bytes"], file_name=item["filename"],
                mime="audio/mp3", use_container_width=True,
                key=f"download_history_{item['id']}_{idx}",
            )

    if st.button("🗑️ Bersihkan Riwayat", key="clear_history"):
        st.session_state.history = []
        st.rerun()

st.markdown("---")
st.caption("Dibuat dengan Streamlit + edge-tts (cadangan: gTTS) + pydub. AI-assisted.")