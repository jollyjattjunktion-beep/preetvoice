from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
import tempfile

import numpy as np
import soundfile as sf
import streamlit as st

st.set_page_config(page_title="PreetVoice Natural Clone", page_icon="🎙️", layout="centered")
st.title("🎙️ PreetVoice — Natural Voice Clone")
st.caption("Reference-based Hindi voice cloning and expressive cricket commentary")

st.warning(
    "Use only a voice you own or have permission to clone. Generated speech is synthetic; "
    "disclose that where listeners could mistake it for a live human broadcast."
)

st.info(
    "This is a separate experimental engine. It does not change the original audio-enhancement app. "
    "The first run downloads the Chatterbox Multilingual V3 model. CPU generation can be slow."
)

@st.cache_resource(show_spinner="Loading Chatterbox Multilingual V3 on CPU…")
def load_model():
    import torch
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    device = "cuda" if torch.cuda.is_available() else "cpu"
    return ChatterboxMultilingualTTS.from_pretrained(device=device, t3_model="v3")

def prepare_reference(uploaded) -> str:
    raw, sr = sf.read(BytesIO(uploaded.getvalue()), dtype="float32", always_2d=True)
    mono = np.mean(raw, axis=1)
    if len(mono) < int(sr * 3):
        raise ValueError("Reference audio should be at least 3 seconds long.")
    # Keep a clean, manageable prompt. Chatterbox can condition on a short reference clip.
    max_samples = int(sr * 18)
    mono = mono[:max_samples]
    peak = float(np.max(np.abs(mono)))
    if peak > 0:
        mono = mono / max(peak, 1.0)
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    temp.close()
    sf.write(temp.name, mono, sr, subtype="PCM_16")
    return temp.name

def split_text(text: str, max_chars: int = 260) -> list[tuple[str, str]]:
    """Return speech chunks paired with punctuation-based pause duration."""
    text = text.strip()
    if not text:
        return []
    pieces = re.split(r"(?<=[.!?।])\s+|\n+", text)
    chunks: list[tuple[str, str]] = []
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        while len(piece) > max_chars:
            cut = max(piece.rfind(" ", 0, max_chars), piece.rfind(",", 0, max_chars))
            if cut < 80:
                cut = max_chars
            chunks.append((piece[:cut].strip(), "comma"))
            piece = piece[cut:].strip()
        if piece:
            if piece.endswith((".", "!", "?", "।")):
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
    audio_parts: list[np.ndarray] = []
    sample_rate = int(model.sr)
    for index, (chunk, pause_kind) in enumerate(parts, start=1):
        st.write(f"Generating phrase {index} of {len(parts)}…")
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
        audio_parts.append(segment)
        pause_seconds = {"comma": 0.22, "sentence": 0.48, "line": 0.32}.get(pause_kind, 0.32)
        if index < len(parts):
            audio_parts.append(np.zeros(int(sample_rate * pause_seconds * pause_scale), dtype=np.float32))
    if not audio_parts:
        raise RuntimeError("The model did not return audio.")
    result = np.concatenate(audio_parts)
    peak = float(np.max(np.abs(result))) if result.size else 0.0
    if peak > 0.99:
        result = result * (0.99 / peak)
    return result, sample_rate

with st.sidebar:
    st.header("Commentary delivery")
    preset = st.selectbox(
        "Delivery preset",
        ["Normal commentary", "Boundary excitement", "Wicket drama", "Pre-match analysis"],
    )
    preset_values = {
        "Normal commentary": (0.50, 0.50, 0.35, 1.0),
        "Boundary excitement": (0.78, 0.30, 0.78, 0.85),
        "Wicket drama": (0.88, 0.28, 0.82, 0.90),
        "Pre-match analysis": (0.42, 0.55, 0.30, 1.15),
    }
    default_exag, default_cfg, default_temp, default_pause = preset_values[preset]
    exaggeration = st.slider("Expressiveness", 0.25, 1.20, float(default_exag), 0.05)
    cfg_weight = st.slider("Pacing guidance", 0.0, 1.0, float(default_cfg), 0.05)
    temperature = st.slider("Voice variation", 0.20, 1.50, float(default_temp), 0.05)
    pause_scale = st.slider("Natural pause length", 0.5, 1.8, float(default_pause), 0.05)
    st.caption("Higher expressiveness can also make speech faster. Tune pacing and pauses together.")

reference = st.file_uploader(
    "1. Upload your reference voice (WAV recommended)",
    type=["wav", "flac", "ogg"],
)
reference_language = st.selectbox(
    "Reference recording language",
    ["Hindi", "English", "Other / mixed"],
    help="If the reference is not Hindi, use a lower pacing-guidance value (around 0.0–0.2) to reduce accent transfer.",
)

language_id = "hi"
text = st.text_area(
    "2. Enter commentary text",
    height=180,
    placeholder="Aur ye ball daali... batsman ne zor daar shot maara... seedha boundary ke paar! Kya zabardast chhakka hai!",
    help="Hindi in Devanagari is the safest starting point. Roman Hinglish is experimental; test names and English cricket terms carefully.",
)

st.caption("Tip: Use commas and full stops to guide phrasing. The app also inserts short pauses between phrases.")

if st.button("🎤 Generate cloned commentary", type="primary", use_container_width=True):
    if reference is None:
        st.error("Upload your reference voice first.")
    elif not text.strip():
        st.error("Enter commentary text first.")
    else:
        ref_path = None
        try:
            with st.spinner("Preparing reference audio…"):
                ref_path = prepare_reference(reference)
            model = load_model()
            with st.spinner("Generating expressive cloned speech on your CPU…"):
                audio, sr = generate_commentary(
                    model=model,
                    text=text,
                    reference_path=ref_path,
                    language_id=language_id,
                    exaggeration=exaggeration,
                    temperature=temperature,
                    cfg_weight=cfg_weight,
                    pause_scale=pause_scale,
                )
            output = BytesIO()
            sf.write(output, audio, sr, format="WAV", subtype="PCM_16")
            output_bytes = output.getvalue()
            st.success(f"Generated {len(audio) / sr:.1f} seconds of speech at {sr} Hz.")
            st.audio(output_bytes, format="audio/wav")
            st.download_button(
                "⬇️ Download cloned commentary WAV",
                data=output_bytes,
                file_name="preetvoice_natural_clone.wav",
                mime="audio/wav",
                use_container_width=True,
            )
        except Exception as exc:
            st.error(f"Voice generation failed: {exc}")
            st.info(
                "Check the PowerShell traceback. On Windows, if a dependency fails to install, "
                "use the separate Python 3.11 environment described in README.md."
            )
        finally:
            if ref_path:
                try:
                    Path(ref_path).unlink(missing_ok=True)
                except OSError:
                    pass

st.divider()
st.caption(
    "PreetVoice V2 experimental clone · Reference audio is used locally for voice conditioning. "
    "No voice model is trained or uploaded by this app."
)
