from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
import tempfile
import inspect

import numpy as np
import soundfile as sf
import streamlit as st

APP_DIR = Path(__file__).resolve().parent
PROFILE_DIR = APP_DIR / "voice_profiles"
PROFILE_PATH = PROFILE_DIR / "preetvoice_reference.wav"
REFERENCE_SECONDS = 10

st.set_page_config(page_title="PreetVoice Natural Clone", page_icon="🎙️", layout="centered")
st.title("🎙️ PreetVoice — Natural Voice Profile")
st.caption("Reference-based Hindi / Hinglish cricket commentary")

st.warning(
    "Only use a voice you own or have permission to clone. Generated audio is synthetic; "
    "do not present it as an actual live human broadcast."
)

st.info(
    "This creates a reusable local voice profile from your reference recording. "
    "It does not fine-tune model weights: Chatterbox uses the reference clip at generation time. "
    "The app detects the installed Chatterbox API: the published PyPI 0.1.7 package uses multilingual V2; "
    "a newer source installation with the t3_model selector can use V3. "
    "Your original audio-enhancement app remains separate."
)

@st.cache_resource(show_spinner="Loading Chatterbox Multilingual Hindi model…")
def load_model():
    import torch
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    device = "cuda" if torch.cuda.is_available() else "cpu"
    loader = ChatterboxMultilingualTTS.from_pretrained

    # The published PyPI 0.1.7 package exposes only the V2 multilingual
    # loader; newer upstream source exposes the optional t3_model selector.
    # Detect the installed API instead of passing an unsupported keyword.
    if "t3_model" in inspect.signature(loader).parameters:
        return loader(device=device, t3_model="v3")
    return loader(device=device)

def read_reference(uploaded) -> tuple[np.ndarray, int]:
    raw, sr = sf.read(BytesIO(uploaded.getvalue()), dtype="float32", always_2d=True)
    if raw.size == 0:
        raise ValueError("The uploaded reference recording is empty.")
    mono = np.mean(raw, axis=1)
    if len(mono) < int(sr * 5):
        raise ValueError("Use at least 5 seconds of clear speech for the reference.")
    if not np.all(np.isfinite(mono)):
        raise ValueError("Reference audio contains invalid samples.")
    return mono.astype(np.float32), int(sr)

def make_reference_clip(audio: np.ndarray, sr: int, start_seconds: float) -> bytes:
    start = max(0, int(start_seconds * sr))
    end = min(len(audio), start + int(REFERENCE_SECONDS * sr))
    clip = audio[start:end]
    if len(clip) < int(5 * sr):
        raise ValueError("Selected reference segment is shorter than 5 seconds.")
    peak = float(np.max(np.abs(clip)))
    if peak > 0.98:
        clip = clip * (0.98 / peak)
    out = BytesIO()
    sf.write(out, clip, sr, format="WAV", subtype="PCM_16")
    return out.getvalue()

def write_temp_reference(clip_bytes: bytes) -> str:
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    temp.write(clip_bytes)
    temp.close()
    return temp.name

def split_text(text: str, max_chars: int = 180) -> list[tuple[str, str]]:
    """Split by sentence/line boundaries and label human-like pause lengths."""
    pieces = re.split(r"(?<=[.!?।!?])\s+|\n+", text.strip())
    chunks: list[tuple[str, str]] = []
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        while len(piece) > max_chars:
            cut = max(piece.rfind(" ", 0, max_chars), piece.rfind(",", 0, max_chars))
            if cut < 65:
                cut = max_chars
            chunks.append((piece[:cut].strip(), "comma"))
            piece = piece[cut:].strip()
        if not piece:
            continue
        if piece.endswith(("!", "!!")):
            pause = "excited"
        elif piece.endswith("?"):
            pause = "question"
        elif piece.endswith((".", "।")):
            pause = "sentence"
        elif piece.endswith(","):
            pause = "comma"
        else:
            pause = "line"
        chunks.append((piece, pause))
    return chunks

def generate_commentary(model, text: str, reference_path: str, language_id: str,
                        exaggeration: float, temperature: float, cfg_weight: float,
                        pause_scale: float) -> tuple[np.ndarray, int]:
    import torch
    parts = split_text(text)
    if not parts:
        raise ValueError("Enter commentary text first.")

    # Model inference is performed phrase by phrase. Pauses are inserted between phrases;
    # this creates breathing room, but does not synthesize inhalation sounds.
    audio_parts: list[np.ndarray] = []
    sample_rate = int(model.sr)
    progress = st.progress(0.0, text="Preparing voice generation…")

    for index, (chunk, pause_kind) in enumerate(parts, start=1):
        progress.progress((index - 1) / len(parts), text=f"Generating phrase {index}/{len(parts)}…")
        with torch.inference_mode():
            wav = model.generate(
                chunk,
                language_id=language_id,
                audio_prompt_path=reference_path,
                exaggeration=exaggeration,
                temperature=temperature,
                cfg_weight=cfg_weight,
            )

        if hasattr(wav, "detach"):
            segment = wav.detach().float().cpu().numpy().squeeze()
        else:
            segment = np.asarray(wav, dtype=np.float32).squeeze()
        segment = np.asarray(segment, dtype=np.float32).reshape(-1)
        if segment.size == 0:
            raise RuntimeError(f"The model returned empty audio for phrase {index}.")
        audio_parts.append(segment)

        pause_seconds = {
            "comma": 0.24,
            "question": 0.58,
            "sentence": 0.52,
            "excited": 0.68,
            "line": 0.42,
        }.get(pause_kind, 0.42)
        if index < len(parts):
            audio_parts.append(
                np.zeros(int(sample_rate * pause_seconds * pause_scale), dtype=np.float32)
            )

    progress.progress(1.0, text="Finishing audio…")
    result = np.concatenate(audio_parts)
    peak = float(np.max(np.abs(result))) if result.size else 0.0
    if peak > 0.99:
        result = result * (0.99 / peak)
    return result, sample_rate

with st.sidebar:
    st.header("Commentary delivery")
    presets = {
        "Normal commentary": (0.50, 0.50, 0.80, 1.00),
        "Boundary excitement": (0.78, 0.30, 0.85, 0.90),
        "Wicket drama": (0.88, 0.28, 0.82, 1.05),
        "Pre-match analysis": (0.42, 0.55, 0.72, 1.15),
    }
    preset = st.selectbox("Delivery preset", list(presets))
    default_exag, default_cfg, default_temp, default_pause = presets[preset]
    exaggeration = st.slider("Expressiveness", 0.25, 1.20, default_exag, 0.05)
    cfg_weight = st.slider("Pacing guidance", 0.0, 1.0, default_cfg, 0.05)
    temperature = st.slider("Voice variation", 0.20, 1.50, default_temp, 0.05)
    pause_scale = st.slider("Breathing-space pauses", 0.5, 1.8, default_pause, 0.05)
    st.caption("These settings shape delivery. Pauses are inserted as silence; no fake inhalation is added.")

saved_profile_exists = PROFILE_PATH.exists()
reference_choice = "Upload / replace voice sample"
if saved_profile_exists:
    reference_choice = st.radio(
        "Voice profile",
        ["Use saved PreetVoice profile", "Upload / replace voice sample"],
    )

uploaded_reference = None
active_reference_path: str | None = None
temporary_reference_path: str | None = None

if reference_choice == "Use saved PreetVoice profile":
    st.success("Saved PreetVoice reference profile found on this PC.")
    st.audio(str(PROFILE_PATH))
    active_reference_path = str(PROFILE_PATH)
else:
    uploaded_reference = st.file_uploader(
        "1. Upload the voice you want PreetVoice to reproduce",
        type=["wav", "flac", "ogg"],
        help="Your uploaded 47.87-second file is fine. The app will use a selected 10-second section as the voice reference.",
    )

    selected_clip_bytes = None
    if uploaded_reference is not None:
        try:
            source_audio, source_sr = read_reference(uploaded_reference)
            total_seconds = len(source_audio) / source_sr
            max_start = max(0.0, total_seconds - REFERENCE_SECONDS)
            st.caption(
                f"Reference loaded: {total_seconds:.2f} sec · {source_sr} Hz · mono. "
                f"Chatterbox reference segment: {REFERENCE_SECONDS} sec."
            )
            start_sec = st.slider(
                "Choose the clearest 10-second voice segment",
                min_value=0.0,
                max_value=float(max_start),
                value=0.0,
                step=1.0,
            )
            selected_clip_bytes = make_reference_clip(source_audio, source_sr, start_sec)
            st.audio(selected_clip_bytes, format="audio/wav")
            if st.button("💾 Save this as my PreetVoice profile", use_container_width=True):
                PROFILE_DIR.mkdir(parents=True, exist_ok=True)
                PROFILE_PATH.write_bytes(selected_clip_bytes)
                st.success("Saved locally as voice_profiles/preetvoice_reference.wav.")
                st.rerun()
        except Exception as exc:
            st.error(f"Reference audio problem: {exc}")

st.divider()
st.subheader("2. Enter cricket commentary")
language_label = st.selectbox(
    "Speech language",
    ["Hindi / Hinglish (recommended: Hindi)", "English"],
)
language_id = "hi" if language_label.startswith("Hindi") else "en"
text = st.text_area(
    "Commentary script",
    height=190,
    placeholder=(
        "आज भारत और न्यूज़ीलैंड के बीच ज़बरदस्त मुकाबला होने वाला है।\n"
        "और ये गेंद डाली... बल्लेबाज़ ने शानदार शॉट लगाया... छक्का!\n"
        "क्या कमाल का प्रहार है!"
    ),
    help=(
        "For natural Hindi pronunciation, write Hindi words in Devanagari and keep player names or "
        "English cricket terms in English script. Roman-only Hinglish can be less reliable."
    ),
)

st.caption(
    "Use commas for short pauses, full stops for sentence breaks, and exclamation marks for high-energy moments."
)

if st.button("🎤 Generate my cloned cricket voice", type="primary", use_container_width=True):
    if reference_choice == "Upload / replace voice sample":
        if uploaded_reference is None:
            st.error("Upload your reference voice first.")
        elif selected_clip_bytes is None:
            st.error("Choose a valid reference segment first.")
        else:
            try:
                temporary_reference_path = write_temp_reference(selected_clip_bytes)
                active_reference_path = temporary_reference_path
            except Exception as exc:
                st.error(f"Could not prepare reference audio: {exc}")

    if active_reference_path and text.strip():
        try:
            model = load_model()
            with st.spinner("Generating reference-based cloned speech. CPU generation may be slow…"):
                audio, sr = generate_commentary(
                    model=model,
                    text=text,
                    reference_path=active_reference_path,
                    language_id=language_id,
                    exaggeration=exaggeration,
                    temperature=temperature,
                    cfg_weight=cfg_weight,
                    pause_scale=pause_scale,
                )
            output = BytesIO()
            sf.write(output, audio, sr, format="WAV", subtype="PCM_16")
            output_bytes = output.getvalue()
            st.success(f"Generated {len(audio) / sr:.1f} seconds at {sr} Hz.")
            st.audio(output_bytes, format="audio/wav")
            st.download_button(
                "⬇️ Download cloned commentary WAV",
                data=output_bytes,
                file_name=f"preetvoice_{preset.lower().replace(' ', '_')}.wav",
                mime="audio/wav",
                use_container_width=True,
            )
        except Exception as exc:
            st.error(f"Voice generation failed: {exc}")
            st.info(
                "Check the PowerShell traceback. The clone app uses a separate Python 3.11 environment. "
                "Windows CPU execution is experimental; the upstream project documents Python 3.11 on Debian."
            )
        finally:
            if temporary_reference_path:
                try:
                    Path(temporary_reference_path).unlink(missing_ok=True)
                except OSError:
                    pass
    elif not text.strip():
        st.error("Enter commentary text first.")

st.divider()
st.caption(
    "PreetVoice V2 · Zero-shot voice conditioning using your saved local reference. "
    "No speaker model is fine-tuned or sent to a cloud service by this app."
)
