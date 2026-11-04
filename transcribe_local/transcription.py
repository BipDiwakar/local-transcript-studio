from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

from faster_whisper import WhisperModel


ProgressCallback = Callable[[float, str], None]


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class TranscriptResult:
    text: str
    detected_language: str | None
    detected_probability: float | None
    segment_count: int
    segments: tuple[TranscriptSegment, ...] = ()
    retried_with_language: str | None = None
    retry_reason: str | None = None


@lru_cache(maxsize=1)
def get_model(model_name: str) -> WhisperModel:
    return WhisperModel(model_name, device="cpu", compute_type="int8")


def transcribe_audio(
    audio_path: Path,
    *,
    model_name: str,
    language_code: str | None,
    initial_prompt: str | None = None,
    hotwords: str | None = None,
    beam_size: int = 5,
    auto_fallback_language: str | None = "en",
    accepted_auto_languages: set[str] | None = None,
    progress_callback: ProgressCallback | None = None,
) -> TranscriptResult:
    if progress_callback:
        progress_callback(0.08, "Loading selected speech model. First use can be slow.")

    model = get_model(model_name)

    if progress_callback:
        progress_callback(0.2, "Reading speech from audio")

    result = _run_transcription(
        model,
        audio_path,
        language_code=language_code,
        initial_prompt=initial_prompt,
        hotwords=hotwords,
        beam_size=beam_size,
        progress_callback=progress_callback,
        progress_start=0.2,
        progress_span=0.75,
    )

    retry_reason = _retry_reason(
        result,
        requested_language=language_code,
        accepted_auto_languages=accepted_auto_languages,
    )
    if retry_reason and auto_fallback_language:
        if progress_callback:
            progress_callback(0.05, f"Auto-detect looked unreliable; retrying as {auto_fallback_language}")
        fallback = _run_transcription(
            model,
            audio_path,
            language_code=auto_fallback_language,
            initial_prompt=initial_prompt,
            hotwords=hotwords,
            beam_size=beam_size,
            progress_callback=progress_callback,
            progress_start=0.2,
            progress_span=0.75,
        )
        return TranscriptResult(
            text=fallback.text,
            detected_language=fallback.detected_language,
            detected_probability=fallback.detected_probability,
            segment_count=fallback.segment_count,
            segments=fallback.segments,
            retried_with_language=auto_fallback_language,
            retry_reason=retry_reason,
        )

    return result


def _run_transcription(
    model: WhisperModel,
    audio_path: Path,
    *,
    language_code: str | None,
    initial_prompt: str | None,
    hotwords: str | None,
    beam_size: int,
    progress_callback: ProgressCallback | None,
    progress_start: float,
    progress_span: float,
) -> TranscriptResult:
    segments, info = model.transcribe(
        str(audio_path),
        language=language_code,
        beam_size=beam_size,
        best_of=beam_size,
        initial_prompt=initial_prompt,
        hotwords=hotwords,
        condition_on_previous_text=False,
        temperature=[0.0],
        compression_ratio_threshold=2.2,
        log_prob_threshold=-0.8,
        no_speech_threshold=0.45,
        no_repeat_ngram_size=3,
        repetition_penalty=1.15,
        hallucination_silence_threshold=1.0,
        language_detection_threshold=0.65,
        language_detection_segments=3,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 700},
    )

    parts: list[str] = []
    transcript_segments: list[TranscriptSegment] = []
    count = 0
    duration = max(float(getattr(info, "duration", 0.0) or 0.0), 1.0)

    for segment in segments:
        cleaned = segment.text.strip()
        if cleaned:
            parts.append(cleaned)
            transcript_segments.append(
                TranscriptSegment(start=float(segment.start), end=float(segment.end), text=cleaned)
            )
        count += 1
        if progress_callback:
            progress = min(0.95, progress_start + (float(segment.end) / duration) * progress_span)
            progress_callback(progress, f"Transcribed {segment.end / 60:.1f} minutes")

    if progress_callback:
        progress_callback(1.0, "Transcription complete")

    return TranscriptResult(
        text="\n\n".join(parts).strip(),
        detected_language=getattr(info, "language", None),
        detected_probability=getattr(info, "language_probability", None),
        segment_count=count,
        segments=tuple(transcript_segments),
    )


def _retry_reason(
    result: TranscriptResult,
    *,
    requested_language: str | None,
    accepted_auto_languages: set[str] | None,
) -> str | None:
    if requested_language is not None:
        return None

    if accepted_auto_languages and result.detected_language:
        if result.detected_language not in accepted_auto_languages:
            return f"detected unsupported language '{result.detected_language}'"

    if _looks_repetitive(result.text):
        return "detected repetitive hallucination"

    return None


def _looks_repetitive(text: str) -> bool:
    words = [word.strip(".,!?;:()[]{}\"'").lower() for word in text.split()]
    words = [word for word in words if word]
    if len(words) < 80:
        return False

    unique_ratio = len(set(words)) / len(words)
    if unique_ratio < 0.18:
        return True

    repeated_trigrams = 0
    seen: dict[tuple[str, str, str], int] = {}
    for index in range(len(words) - 2):
        trigram = (words[index], words[index + 1], words[index + 2])
        seen[trigram] = seen.get(trigram, 0) + 1
        if seen[trigram] >= 6:
            repeated_trigrams += 1

    return repeated_trigrams >= 3
