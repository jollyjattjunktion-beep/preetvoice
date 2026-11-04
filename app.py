from __future__ import annotations

import streamlit as st
import soundfile as sf
import numpy as np

from voice_engine import decode_audio, encode_wav, enhance

st.set_page_config(page_title="PreetVoice", page_icon="🎙️", layout="centered")
st.title("🎙️ PreetVoice")
st.caption("Local speech enhancement for Hindi / Hinglish cricket commentary")

st.info(
    "This first version enhances an existing recording. It does not clone or convert a speaker's voice. "
    "The reference upload is optional and is only available for side-by-side listening."
)

with st.sidebar:
    st.header("Enhancement controls")
    clarity = st.slider("Speech clarity", 0, 100, 35, help="Gentle presence and rumble control.")
    warmth = st.slider("Warmth", 0, 100, 15, help="Very subtle harmonic warmth; keep this low.")
    compression = st.slider("Compression", 0, 100, 25, help="Reduces large volume swings.")
    target_lufs = st.slider("Target loudness (approx.)", -24.0, -12.0, -16.0, 0.5)
    st.caption("Loudness is an RMS-based approximation, not a certified LUFS measurement.")

st.subheader("1. Upload commentary audio")
source_file = st.file_uploader(
    "Choose the TTS commentary recording",
    type=["wav", "flac", "ogg", "mp3", "m4a", "aac"],
    key="source",
)

st.subheader("2. Optional reference recording")
reference_file = st.file_uploader(
    "Upload a reference only if you want to compare the sound",
    type=["wav", "flac", "ogg", "mp3", "m4a", "aac"],
    key="reference",
)

if reference_file is not None:
    try:
        ref_audio, ref_sr = decode_audio(reference_file.getvalue(), reference_file.name)
        st.audio(reference_file.getvalue())
        st.caption(f"Reference loaded for listening only: {len(ref_audio) / ref_sr:.1f} seconds at {ref_sr} Hz.")
    except Exception as exc:
        st.error(str(exc))

if source_file is not None:
    try:
        original, sr = decode_audio(source_file.getvalue(), source_file.name)
        st.success(f"Loaded {len(original) / sr:.2f} seconds · {sr} Hz · {original.shape[1]} channel(s)")
        st.audio(source_file.getvalue())

        if st.button("✨ Enhance commentary", type="primary", use_container_width=True):
            with st.spinner("Processing locally on your CPU..."):
                processed = enhance(
                    original,
                    sr,
                    clarity=clarity,
                    warmth=warmth,
                    compression=compression,
                    target_lufs=target_lufs,
                )
                output_bytes = encode_wav(processed, sr)
                st.session_state["preetvoice_output"] = output_bytes
                st.session_state["preetvoice_name"] = source_file.name.rsplit(".", 1)[0] + "_preetvoice.wav"

        if st.session_state.get("preetvoice_output"):
            st.subheader("3. Compare result")
            st.audio(st.session_state["preetvoice_output"], format="audio/wav")
            st.download_button(
                "⬇️ Download enhanced WAV",
                data=st.session_state["preetvoice_output"],
                file_name=st.session_state.get("preetvoice_name", "preetvoice_enhanced.wav"),
                mime="audio/wav",
                use_container_width=True,
            )
            st.caption("Tip: Compare at the same playback volume. Avoid judging loudness alone as improved quality.")
    except Exception as exc:
        st.error(f"Audio could not be processed: {exc}")

st.divider()
st.caption("PreetVoice · First local prototype · Your files are processed in this app session.")
