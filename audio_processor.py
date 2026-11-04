"""CPU-friendly speech enhancement DSP. No voice cloning or speaker conversion."""
from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfiltfilt


def _as_float_audio(audio: np.ndarray) -> np.ndarray:
    x = np.asarray(audio, dtype=np.float32)
    if x.ndim == 1:
        x = x[:, None]
    if x.ndim != 2 or x.shape[0] < 2:
        raise ValueError("Audio must contain at least two samples.")
    if not np.all(np.isfinite(x)):
        raise ValueError("Audio contains invalid numeric values.")
    return np.clip(x, -1.0, 1.0)


def _filter(audio: np.ndarray, sr: int, kind: str, cutoff, order: int = 2) -> np.ndarray:
    nyquist = sr / 2.0
    if isinstance(cutoff, tuple):
        wn = [max(1.0, cutoff[0]) / nyquist, min(nyquist * 0.98, cutoff[1]) / nyquist]
    else:
        wn = min(max(cutoff / nyquist, 0.001), 0.98)
    sos = butter(order, wn, btype=kind, output="sos")
    # Short clips may be shorter than filtfilt's padding requirement.
    if audio.shape[0] < 24:
        return audio
    return sosfiltfilt(sos, audio, axis=0).astype(np.float32)


def _compress(audio: np.ndarray, amount: float, sr: int) -> np.ndarray:
    """Gentle peak-envelope compressor; amount is 0..100."""
    if amount <= 0:
        return audio
    x = audio.copy()
    mono = np.mean(np.abs(x), axis=1)
    attack = max(1.0, np.exp(-1.0 / (0.008 * sr)))
    release = max(1.0, np.exp(-1.0 / (0.120 * sr)))
    env = np.zeros_like(mono)
    for i, sample in enumerate(mono):
        coeff = attack if sample > (env[i - 1] if i else 0.0) else release
        env[i] = coeff * (env[i - 1] if i else 0.0) + (1.0 - coeff) * sample
    threshold = 10 ** (-18.0 / 20.0)
    ratio = 1.0 + (amount / 100.0) * 2.0
    safe_env = np.maximum(env, 1e-6)
    level_db = 20.0 * np.log10(safe_env)
    over_db = np.maximum(level_db - (-18.0), 0.0)
    gain_db = -over_db * (1.0 - 1.0 / ratio)
    gain = (10 ** (gain_db / 20.0))[:, None]
    return x * gain


def _soft_warmth(audio: np.ndarray, amount: float) -> np.ndarray:
    if amount <= 0:
        return audio
    drive = 1.0 + amount / 250.0
    saturated = np.tanh(audio * drive) / np.tanh(drive)
    mix = amount / 100.0 * 0.18
    return (audio * (1.0 - mix) + saturated * mix).astype(np.float32)


def _peak_limit(audio: np.ndarray, ceiling_db: float = -1.5) -> np.ndarray:
    ceiling = 10 ** (ceiling_db / 20.0)
    peak = float(np.max(np.abs(audio)))
    if peak > ceiling:
        audio = audio * (ceiling / peak)
    return audio.astype(np.float32)


def process_speech(
    audio: np.ndarray,
    sample_rate: int,
    clarity: int = 35,
    warmth: int = 15,
    compression: int = 25,
    target_lufs: float = -16.0,
) -> np.ndarray:
    """Enhance speech while preserving timing and pitch."""
    if sample_rate < 8000 or sample_rate > 192000:
        raise ValueError("Sample rate must be between 8 kHz and 192 kHz.")
    clarity = int(np.clip(clarity, 0, 100))
    warmth = int(np.clip(warmth, 0, 100))
    compression = int(np.clip(compression, 0, 100))
    x = _as_float_audio(audio)

    # Remove rumble and inaudible high-frequency noise; clarity is deliberately gentle.
    x = _filter(x, sample_rate, "highpass", 65 + clarity * 0.25, order=2)
    x = _filter(x, sample_rate, "lowpass", 16000 - clarity * 10, order=2)

    # A very subtle presence lift through parallel high-pass blend.
    if clarity:
        presence = _filter(x, sample_rate, "highpass", 1800, order=2)
        x = x + presence * (clarity / 100.0) * 0.10

    x = _compress(x, compression, sample_rate)
    x = _soft_warmth(x, warmth)

    # RMS-based loudness approximation. This is not a standards-compliant LUFS meter.
    rms = float(np.sqrt(np.mean(np.square(x)) + 1e-12))
    target_rms = 10 ** ((target_lufs - 3.0) / 20.0)
    if rms > 1e-5:
        x *= min(target_rms / rms, 8.0)

    return _peak_limit(x, -1.5)
