# PreetVoice

A local, CPU-friendly audio enhancement workbench for making AI-generated Hindi/Hinglish cricket commentary sound clearer, warmer, and less harsh.

## What this first version does

- Accepts an existing speech recording (WAV, MP3, FLAC, OGG, or M4A where supported by FFmpeg).
- Applies gentle speech-focused filtering, controlled compression, optional warmth, and loudness normalization.
- Lets you compare the original and processed audio before downloading.
- Runs locally on Windows and does not require a paid API or NVIDIA GPU.

**Important:** This is an audio enhancement tool, not a voice-cloning or voice-conversion system. The optional reference recording is for listening comparison only; it is not used to imitate or identify a speaker. Audio processing cannot add genuinely human breathing, emotion, or natural prosody that was not present in the original performance. For the best result, generate the TTS with expressive pauses and varied delivery first, then enhance it here.

## Requirements

- Windows 10/11
- Python 3.10 or 3.11
- 4 GB RAM minimum; 16 GB recommended
- FFmpeg installed and available on PATH for MP3/M4A decoding

## Install

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks activation, run:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## Run

```powershell
streamlit run app.py
```

Open the local URL shown in the terminal (normally http://localhost:8501).

## Suggested starting settings for cricket commentary

- Speech clarity: 35%
- Warmth: 15%
- Compression: 25%
- Output loudness: -16 LUFS (starting point; adjust for your production chain)

Avoid heavy reverb, extreme bass boost, or aggressive compression. These often make synthetic speech sound more artificial.

## Project structure

- `app.py` — Streamlit user interface
- `voice_engine.py` — audio loading, processing orchestration, and export
- `audio_processor.py` — CPU-based DSP operations
- `config.yaml` — default processing values

## Privacy

Processing happens locally. Uploaded audio is held in the app's memory for the current session and is not automatically uploaded to a third-party service. Do not commit private recordings, API keys, or generated audio to GitHub.

## Roadmap

1. A/B audio enhancement testing.
2. Presets for normal commentary, excitement, and calm analysis.
3. Optional silence and pause analysis without changing the speaker's identity.
4. Batch processing for match scripts.
