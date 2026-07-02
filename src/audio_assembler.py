from pathlib import Path

from pydub import AudioSegment


def pause_after_text(text: str, default_seconds: float, question_seconds: float, long_reply_seconds: float) -> float:
    stripped = text.strip()
    if stripped.endswith("?"):
        return question_seconds
    if len(stripped) >= 120:
        return long_reply_seconds
    return default_seconds


def assemble_audio(
    segment_paths: list[Path],
    segment_texts: list[str],
    output_path: str | Path,
    default_pause_seconds: float = 0.5,
    question_pause_seconds: float = 0.65,
    long_reply_pause_seconds: float = 0.6,
) -> Path:
    if len(segment_paths) != len(segment_texts):
        raise ValueError("segment_paths and segment_texts must have the same length.")
    if not segment_paths:
        raise ValueError("No audio segments to assemble.")

    final_audio = AudioSegment.silent(duration=150)

    for index, segment_path in enumerate(segment_paths):
        final_audio += AudioSegment.from_file(segment_path)
        if index < len(segment_paths) - 1:
            pause_seconds = pause_after_text(
                segment_texts[index],
                default_pause_seconds,
                question_pause_seconds,
                long_reply_pause_seconds,
            )
            final_audio += AudioSegment.silent(duration=int(pause_seconds * 1000))

    final_audio += AudioSegment.silent(duration=250)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    final_audio.export(output, format=output.suffix.lstrip(".") or "wav")
    return output


def audio_duration_seconds(path: str | Path) -> float:
    audio = AudioSegment.from_file(path)
    return len(audio) / 1000
