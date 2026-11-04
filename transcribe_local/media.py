from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from .config import FileDetails, SUPPORTED_EXTENSIONS, VIDEO_EXTENSIONS


class MediaError(RuntimeError):
    """Raised when a media file cannot be inspected or converted."""


def find_media_binary(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found

    for directory in ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"):
        candidate = Path(directory) / name
        if candidate.exists():
            return str(candidate)

    raise MediaError(
        f"{name} is not installed or is not available to the app. "
        "Install ffmpeg with: brew install ffmpeg"
    )


def extension_for(path_or_name: str) -> str:
    return Path(path_or_name).suffix.lower().lstrip(".")


def validate_extension(filename: str) -> str:
    extension = extension_for(filename)
    if extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise MediaError(f"Unsupported file type '.{extension}'. Supported formats: {supported}.")
    return extension


def human_size(size_bytes: int) -> str:
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} GB"


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "Unknown"
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def probe_duration(path: Path) -> float | None:
    try:
        ffprobe = find_media_binary("ffprobe")
    except MediaError:
        return None

    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        payload = json.loads(result.stdout)
        duration = payload.get("format", {}).get("duration")
        return float(duration) if duration is not None else None
    except (FileNotFoundError, subprocess.CalledProcessError, json.JSONDecodeError, ValueError):
        return None


def inspect_media(path: Path, original_name: str) -> FileDetails:
    extension = validate_extension(original_name)
    return FileDetails(
        name=original_name,
        extension=extension,
        size_bytes=path.stat().st_size,
        duration_seconds=probe_duration(path),
        is_video=extension in VIDEO_EXTENSIONS,
    )


def extract_audio(input_path: Path, output_path: Path, *, normalize: bool = False) -> None:
    ffmpeg = find_media_binary("ffmpeg")
    command = [
        ffmpeg,
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
    ]
    if normalize:
        command.extend(["-af", "loudnorm=I=-18:TP=-1.5:LRA=11"])
    command.extend([
        "-c:a",
        "pcm_s16le",
        str(output_path),
    ])
    try:
        subprocess.run(command, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or "ffmpeg could not extract audio from this file."
        raise MediaError(message) from exc


def analyze_audio(path: Path) -> dict[str, str]:
    ffmpeg = find_media_binary("ffmpeg")
    command = [
        ffmpeg,
        "-i",
        str(path),
        "-af",
        "volumedetect",
        "-f",
        "null",
        "-",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        result = exc

    output = f"{getattr(result, 'stdout', '')}\n{getattr(result, 'stderr', '')}"
    mean_match = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?) dB", output)
    max_match = re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?) dB", output)
    mean_volume = float(mean_match.group(1)) if mean_match else None
    max_volume = float(max_match.group(1)) if max_match else None

    issues: list[str] = []
    if mean_volume is not None and mean_volume < -30:
        issues.append("low average volume")
    if max_volume is not None and max_volume < -12:
        issues.append("quiet peaks")

    quality = "Good"
    if issues:
        quality = "Needs attention"
    elif mean_volume is None:
        quality = "Unknown"

    return {
        "quality": quality,
        "mean_volume": f"{mean_volume:.1f} dB" if mean_volume is not None else "Unknown",
        "max_volume": f"{max_volume:.1f} dB" if max_volume is not None else "Unknown",
        "suggestion": "Use Balanced or High Accuracy with normalization." if issues else "Balanced should work well.",
    }
