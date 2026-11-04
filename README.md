# Local Transcript Studio

A macOS app for transcribing audio and video locally with faster-whisper. Edit the transcript, save a project, and export it as text, Word, or PDF. There is no transcription API fee or API key requirement.

## Features

- Audio and video upload, with audio extraction through FFmpeg.
- Language selection or automatic detection, including English, Portuguese, Nepali, Hindi, and Spanish.
- Four quality presets, optional vocabulary hints, and an editable transcript.
- Local projects, timestamped output, and TXT, DOCX, and PDF exports.
- A settings page to inspect and remove downloaded models.

Supported formats: MP3, WAV, M4A, AAC, FLAC, OGG, MP4, MOV, MKV, and WEBM.

## Setup

Requires macOS, Python 3.12, FFmpeg, and enough disk space for the selected model. On a Mac with Homebrew:

```sh
brew install python@3.12 ffmpeg
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Start the desktop window from the project directory:

```sh
python desktop_launcher.py
```

To build and install the macOS app in `~/Applications`, run `./scripts/build_macos_app.command`. The build replaces an existing app with the same name and creates a shared runtime in `~/Library/Application Support/Local Transcript Studio`.

## Using the app

Choose a recording, select its spoken language and quality, then click **Transcribe**. Review and edit the result before saving a project or exporting. Exports go to `~/Downloads/Local Transcript Studio Exports`.

Balanced uses the small model; higher-quality models need more space and processing time. The first use of a model downloads it from Hugging Face. Subsequent transcription runs locally. Settings shows cached models and lets you remove them.

## Limitations

Accuracy depends on the recording, language, and model. Select the spoken language when known and review important names and terms. Automatic detection can be wrong. Speaker names are manually applied; the app does not identify speakers automatically. Long files can take considerable time and memory, and the upload limit is 2 GB. The app relies on a local Python installation and FFmpeg; it is not a self-contained distributable.

The notes feature extracts text heuristically and should be checked against the recording. Timestamped exports use the original transcription segments, so edits in the main editor are not reflected in those segments.
