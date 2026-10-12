"""
================================================================
 Dialogue TTS Studio (GRATIS) — Percakapan 2 Orang -> 1 File Audio
================================================================
Mesin suara (semua gratis, tanpa API key):
  1. Kokoro  (LOKAL, default) : jalan di server aplikasi sendiri, tidak
                                 bisa "ditolak" pihak luar. Punya voice
                                 PRIA dan WANITA (Inggris US/UK).
  2. edge-tts (online)        : voice Microsoft Edge. Sering ditolak
                                 (403) dari IP server cloud, jadi hanya
                                 opsional.
  3. Auto                     : coba edge-tts dulu, kalau ditolak otomatis
                                 pakai Kokoro.

Catatan:
  - Pertama kali dipakai, Kokoro mengunduh file model (~115 MB) sekali.
    Setelah itu tersimpan di cache server.
  - Deploy Streamlit Cloud: packages.txt harus berisi "ffmpeg".
================================================================
"""

import io
import re
import time
import wave
import asyncio
import tempfile
import traceback
import urllib.request
from pathlib import Path
from datetime import datetime

import numpy as np
import streamlit as st

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False

try:
    from kokoro_onnx import Kokoro
    KOKORO_AVAILABLE = True
except ImportError:
    KOKORO_AVAILABLE = False

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
    'dengan voice pria/wanita yang berbeda untuk tiap pembicara.</div>',
    unsafe_allow_html=True,
)

if not PYDUB_AVAILABLE:
    st.error(
        "⚠️ Library `pydub` tidak ditemukan. Install `pydub` dan pastikan `ffmpeg` terpasang "
        "(Streamlit Cloud: tambahkan `ffmpeg` di `packages.txt`)."
    )
    st.stop()

if not KOKORO_AVAILABLE and not EDGE_TTS_AVAILABLE:
    st.error("⚠️ Tidak ada mesin TTS terpasang. Install: `pip install kokoro-onnx edge-tts`")
    st.stop()


# ================================================================
# 2. KOKORO (LOKAL) — unduh model, load, sintesis
# ================================================================
# File rilis resmi kokoro-onnx (tag model-files-v1.0). int8 = paling kecil (~88 MB).
# Ganti ke "kokoro-v1.0.fp16.onnx" (~169 MB) atau "kokoro-v1.0.onnx" (~310 MB)
# kalau ingin kualitas sedikit lebih tinggi dan server kuat.
KOKORO_BASE_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
KOKORO_MODEL_FILE = "kokoro-v1.0.int8.onnx"
KOKORO_VOICES_FILE = "voices-v1.0.bin"

# Voice Inggris pilihan (nama sesuai daftar voice Kokoro).
KOKORO_VOICES = {
    "am_michael": "🇺🇸 Pria — Michael",
    "am_adam":    "🇺🇸 Pria — Adam",
    "am_eric":    "🇺🇸 Pria — Eric",
    "am_liam":    "🇺🇸 Pria — Liam",
    "am_onyx":    "🇺🇸 Pria — Onyx",
    "bm_george":  "🇬🇧 Pria — George",
    "bm_lewis":   "🇬🇧 Pria — Lewis",
    "af_heart":   "🇺🇸 Wanita — Heart",
    "af_bella":   "🇺🇸 Wanita — Bella",
    "af_nicole":  "🇺🇸 Wanita — Nicole",
    "af_sarah":   "🇺🇸 Wanita — Sarah",
    "af_sky":     "🇺🇸 Wanita — Sky",
    "bf_emma":    "🇬🇧 Wanita — Emma",
    "bf_isabella": "🇬🇧 Wanita — Isabella",
}


def kokoro_lang(voice: str) -> str:
    """Prefix 'b' = British English, selain itu American English."""
    return "en-gb" if voice.startswith("b") else "en-us"


def _download(url: str, dest: Path):
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=120) as resp, open(tmp, "wb") as f:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
    tmp.replace(dest)


@st.cache_resource(show_spinner=False)
def load_kokoro():
    """Unduh model sekali (jika belum ada) lalu load. Di-cache selama server hidup."""
    model_dir = Path(tempfile.gettempdir()) / "kokoro_models"
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / KOKORO_MODEL_FILE
    voices_path = model_dir / KOKORO_VOICES_FILE

    if not model_path.exists():
        _download(f"{KOKORO_BASE_URL}/{KOKORO_MODEL_FILE}", model_path)
    if not voices_path.exists():
        _download(f"{KOKORO_BASE_URL}/{KOKORO_VOICES_FILE}", voices_path)

    return Kokoro(str(model_path), str(voices_path))


def samples_to_wav_bytes(samples, sample_rate: int) -> bytes:
    """Ubah array float (-1..1) dari Kokoro menjadi bytes WAV 16-bit mono."""
    arr = np.asarray(samples, dtype=np.float32).reshape(-1)
    pcm = (np.clip(arr, -1.0, 1.0) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sample_rate))
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def synth_kokoro(text: str, voice: str, rate_pct: int):
    kokoro = load_kokoro()
    speed = max(0.5, min(2.0, 1.0 + rate_pct / 100.0))
    samples, sample_rate = kokoro.create(text, voice=voice, speed=speed, lang=kokoro_lang(voice))
    return samples_to_wav_bytes(samples, sample_rate), "wav"


# ================================================================
# 3. EDGE-TTS (ONLINE, OPSIONAL)
# ================================================================
FALLBACK_EDGE_VOICES = {
    "en-US-GuyNeural":     "en-US — Male",
    "en-US-AriaNeural":    "en-US — Female",
    "en-US-JennyNeural":   "en-US — Female",
    "en-GB-RyanNeural":    "en-GB — Male",
    "en-GB-SoniaNeural":   "en-GB — Female",
    "en-AU-WilliamNeural": "en-AU — Male",
    "en-AU-NatashaNeural": "en-AU — Female",
}


async def _edge_async(text, voice, rate_pct):
    rate_str = f"{'+' if rate_pct >= 0 else ''}{rate_pct}%"
    communicate = edge_tts.Communicate(text, voice, rate=rate_str)
    buf = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.extend(chunk["data"])
    return bytes(buf)


def synth_edge(text, voice, rate_pct, timeout=25):
    data = asyncio.run(asyncio.wait_for(_edge_async(text, voice, rate_pct), timeout))
    if not data:
        raise RuntimeError("edge-tts mengembalikan audio kosong")
    return data, "mp3"


# ================================================================
# 4. STATE & HELPER
# ================================================================
if "history" not in st.session_state:
    st.session_state.history = []

DEFAULT_SCRIPT = """A: Hi, how are you today?
B: I'm doing great, thanks! How about you?
A: Pretty good. I'm testing a text-to-speech app for two-person conversations.
B: That sounds useful. Does it create a single audio file?
A: Yes, and you can download it right after it's generated."""


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


def build_filename():
    return f"conversation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"


def pick_index(options, preferred, fallback_index=0):
    keys = list(options.keys())
    return keys.index(preferred) if preferred in keys else min(fallback_index, len(keys) - 1)


# ================================================================
# 5. SIDEBAR
# ================================================================
ENGINE_OPTIONS = []
if KOKORO_AVAILABLE:
    ENGINE_OPTIONS.append("Kokoro (lokal, paling stabil)")
if EDGE_TTS_AVAILABLE:
    ENGINE_OPTIONS.append("edge-tts (online)")
if KOKORO_AVAILABLE and EDGE_TTS_AVAILABLE:
    ENGINE_OPTIONS.append("Auto (edge-tts, jika ditolak → Kokoro)")

with st.sidebar:
    st.header("⚙️ Konfigurasi")
    st.success("Gratis — tidak perlu API key ✅")

    engine_choice = st.radio("Mesin suara", ENGINE_OPTIONS, index=0)
    use_kokoro_voices = engine_choice.startswith(("Kokoro", "Auto"))
    use_edge_voices = engine_choice.startswith(("edge", "Auto"))

    rate_pct = st.slider("Kecepatan Bicara (%)", -50, 50, 0, 5, help="0% = normal.")
    gap_ms = st.slider("Jeda antar baris (ms)", 0, 1500, 350, 50)

    st.markdown("---")
    kokoro_voice_a, kokoro_voice_b = "am_michael", "af_heart"
    if use_kokoro_voices:
        st.subheader("🗣️ Voice Kokoro")
        kokoro_voice_a = st.selectbox(
            "Pembicara A", list(KOKORO_VOICES.keys()),
            index=pick_index(KOKORO_VOICES, "am_michael"),
            format_func=lambda v: f"{KOKORO_VOICES[v]} ({v})", key="kv_a",
        )
        kokoro_voice_b = st.selectbox(
            "Pembicara B", list(KOKORO_VOICES.keys()),
            index=pick_index(KOKORO_VOICES, "af_heart"),
            format_func=lambda v: f"{KOKORO_VOICES[v]} ({v})", key="kv_b",
        )

    edge_voice_a, edge_voice_b = "en-US-GuyNeural", "en-US-AriaNeural"
    if use_edge_voices:
        st.subheader("🗣️ Voice edge-tts")
        edge_voice_a = st.selectbox(
            "Pembicara A", list(FALLBACK_EDGE_VOICES.keys()),
            index=pick_index(FALLBACK_EDGE_VOICES, "en-US-GuyNeural"),
            format_func=lambda v: f"{v} — {FALLBACK_EDGE_VOICES[v]}", key="ev_a",
        )
        edge_voice_b = st.selectbox(
            "Pembicara B", list(FALLBACK_EDGE_VOICES.keys()),
            index=pick_index(FALLBACK_EDGE_VOICES, "en-US-AriaNeural", 1),
            format_func=lambda v: f"{v} — {FALLBACK_EDGE_VOICES[v]}", key="ev_b",
        )

    st.caption("Label pembicara pertama di naskah memakai voice A, label kedua memakai voice B.")


# ================================================================
# 6. INPUT NASKAH
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
# 7. GENERATE
# ================================================================
def decide_engine(first_text: str):
    """
    Tentukan mesin yang dipakai untuk SELURUH percakapan (supaya suara konsisten).
    Return: (engine_name, note_or_None)
    """
    if engine_choice.startswith("Kokoro"):
        return "kokoro", None
    if engine_choice.startswith("edge"):
        return "edge", None
    # Auto: tes edge-tts dengan baris pertama
    try:
        synth_edge(first_text, edge_voice_a, rate_pct, timeout=20)
        return "edge", None
    except Exception as e:
        return "kokoro", f"edge-tts ditolak/gagal ({type(e).__name__}: {e}) — memakai Kokoro."


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
        progress_bar = st.progress(0, text="Mempersiapkan...")
        try:
            engine, note = decide_engine(lines[0][1])

            if engine == "kokoro":
                if not KOKORO_AVAILABLE:
                    raise RuntimeError("Library kokoro-onnx belum terpasang (cek requirements.txt).")
                progress_bar.progress(3, text="Memuat model Kokoro (unduhan ~115 MB hanya sekali)...")
                load_kokoro()
                voices = {0: kokoro_voice_a, 1: kokoro_voice_b}
            else:
                voices = {0: edge_voice_a, 1: edge_voice_b}

            combined = AudioSegment.silent(duration=0)
            silence_gap = AudioSegment.silent(duration=gap_ms)
            line_previews = []

            total = len(lines)
            for idx, (speaker, text) in enumerate(lines):
                progress_bar.progress(
                    5 + int(idx / total * 85),
                    text=f"Generate baris {idx + 1}/{total} ({speaker})...",
                )
                voice = voices[speakers_found.index(speaker)]

                if engine == "kokoro":
                    data, fmt = synth_kokoro(text, voice, rate_pct)
                else:
                    last_err = None
                    for attempt in range(3):
                        try:
                            data, fmt = synth_edge(text, voice, rate_pct)
                            break
                        except Exception as e:
                            last_err = e
                            time.sleep(attempt + 1)
                    else:
                        raise RuntimeError(f"edge-tts gagal pada baris {idx + 1}: {last_err}")

                line_previews.append({"speaker": speaker, "text": text, "bytes": data, "fmt": fmt})
                combined += AudioSegment.from_file(io.BytesIO(data), format=fmt)
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
                "engine": "Kokoro (lokal)" if engine == "kokoro" else "edge-tts",
                "voices": [voices[i] for i in range(len(speakers_found))],
                "line_previews": line_previews,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })

            progress_bar.empty()
            st.success(f"✅ Percakapan berhasil dibuat dari {total} baris!")
            if note:
                st.info(f"ℹ️ {note}")

        except Exception as e:
            progress_bar.empty()
            st.error(
                f"❌ Gagal generate audio: {e}\n\n"
                "Jika memakai Kokoro untuk pertama kali, pastikan server bisa mengunduh file dari GitHub, "
                "lalu klik Generate lagi."
            )
            with st.expander("Detail teknis (untuk debugging)"):
                st.code(traceback.format_exc())


# ================================================================
# 8. PREVIEW & DOWNLOAD TERBARU
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
        f'<span class="meta-pill">🎙️ {latest["engine"]}</span>'
        f'<span class="meta-pill">🗣️ {" + ".join(latest["voices"])}</span>',
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
            st.audio(line["bytes"], format=f"audio/{'wav' if line['fmt'] == 'wav' else 'mp3'}")


# ================================================================
# 9. RIWAYAT
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
st.caption("Dibuat dengan Streamlit + Kokoro (lokal) / edge-tts + pydub. AI-assisted.")