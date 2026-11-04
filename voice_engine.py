"""Audio I/O and enhancement orchestration for PreetVoice."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import numpy as np
import soundfile as sf
from pydub import AudioSegment

from audio_processor import process_speech

SUPPORTED_EXTENSIONS = {"wav", "flac", "ogg", "mp3", "m4a", "aac"}


def decode_audio(data: bytes, filename: str) -> tuple[np.ndarray, int]:
    suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported audio format: .{suffix or 'unknown'}")
    try:
        segment = AudioSegment.from_file(BytesIO(data), format=suffix)
        segment = segment.set_sample_width(4)
        sr = segment.frame_rate
        channels = segment.channels
        raw = np.array(segment.get_array_of_samples(), dtype=np.float32)
        audio = raw.reshape((-1, channels)) / float(2 ** 31)
        return audio, sr
    except Exception as exc:
        raise ValueError(
            "Could not decode this file. For MP3/M4A, install FFmpeg and add it to PATH. "
            f"Decoder detail: {exc}"
        ) from exc


def encode_wav(audio: np.ndarray, sample_rate: int) -> bytes:
    buffer = BytesIO()
    sf.write(buffer, audio, sample_rate, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


def enhance(
    audio: np.ndarray,
    sample_rate: int,
    clarity: int = 35,
    warmth: int = 15,
    compression: int = 25,
    target_lufs: float = -16.0,
) -> np.ndarray:
    return process_speech(
        audio,
        sample_rate,
        clarity=clarity,
        warmth=warmth,
        compression=compression,
        target_lufs=target_lufs,
    )
