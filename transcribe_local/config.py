from __future__ import annotations

from dataclasses import dataclass


SUPPORTED_EXTENSIONS = {
    "mp3",
    "wav",
    "m4a",
    "aac",
    "flac",
    "ogg",
    "mp4",
    "mov",
    "mkv",
    "webm",
}

VIDEO_EXTENSIONS = {"mp4", "mov", "mkv", "webm"}

LANGUAGES = {
    "Auto-detect": None,
    "English": "en",
    "Portuguese": "pt",
    "Nepali": "ne",
    "Hindi": "hi",
    "Spanish": "es",
    "French": "fr",
    "German": "de",
    "Italian": "it",
    "Arabic": "ar",
    "Chinese": "zh",
    "Japanese": "ja",
    "Korean": "ko",
    "Russian": "ru",
    "Bengali": "bn",
    "Urdu": "ur",
    "Gujarati": "gu",
    "Marathi": "mr",
    "Tamil": "ta",
    "Telugu": "te",
}

MODEL_OPTIONS = {
    "Tiny - fastest, lowest accuracy": "tiny",
    "Base - fast, light": "base",
    "Small - recommended starter": "small",
    "Medium - more accurate, slower": "medium",
    "Large v3 - best accuracy, slowest": "large-v3",
}

DEFAULT_MAX_FILE_MB = 2048


@dataclass(frozen=True)
class FileDetails:
    name: str
    extension: str
    size_bytes: int
    duration_seconds: float | None
    is_video: bool
