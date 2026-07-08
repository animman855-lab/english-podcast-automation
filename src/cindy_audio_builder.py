from pathlib import Path
import json
import time

from pydub import AudioSegment
from pydub.silence import detect_nonsilent

from audio_assembler import audio_duration_seconds


CINDY_VOICE = "bf_emma"
CINDY_LANG_CODE = "a"
CINDY_SAMPLE_RATE = 24000
CINDY_PAUSE_DEFAULT_SECONDS = 0.5
CINDY_PAUSE_BETWEEN_REPEAT_SECONDS = 0.45
CINDY_PAUSE_AFTER_REPEAT_SECONDS = 0.8
CINDY_PAUSE_AFTER_QUESTION_SECONDS = 0.65
CINDY_PAUSE_AFTER_LONG_LINE_SECONDS = 0.6
CINDY_PAUSE_SECTION_SECONDS = 1.0
CINDY_TRIM_KEEP_MS = 90


def script_lines(script: str) -> list[str]:
    return [line.strip() for line in script.splitlines() if line.strip()]


def normalized_text(value: str) -> str:
    return " ".join(value.lower().strip().split())


def trim_segment_silence(audio_path: Path) -> Path:
    audio = AudioSegment.from_file(audio_path)
    silence_threshold = max(audio.dBFS - 18, -50)
    ranges = detect_nonsilent(audio, min_silence_len=120, silence_thresh=silence_threshold)
    if not ranges:
        return audio_path

    start = max(0, ranges[0][0] - CINDY_TRIM_KEEP_MS)
    end = min(len(audio), ranges[-1][1] + CINDY_TRIM_KEEP_MS)
    audio[start:end].export(audio_path, format=audio_path.suffix.lstrip(".") or "wav")
    return audio_path


def cindy_pause_seconds(segment_texts: list[str], index: int) -> float:
    current = normalized_text(segment_texts[index])
    previous_text = normalized_text(segment_texts[index - 1]) if index > 0 else ""
    next_text = normalized_text(segment_texts[index + 1]) if index + 1 < len(segment_texts) else ""

    if next_text and current == next_text:
        return CINDY_PAUSE_BETWEEN_REPEAT_SECONDS
    if previous_text and current == previous_text:
        return CINDY_PAUSE_AFTER_REPEAT_SECONDS
    if segment_texts[index].strip().endswith("?"):
        return CINDY_PAUSE_AFTER_QUESTION_SECONDS
    if "let us begin" in current or "let's begin" in current:
        return CINDY_PAUSE_SECTION_SECONDS
    if len(segment_texts[index]) >= 120:
        return CINDY_PAUSE_AFTER_LONG_LINE_SECONDS
    return CINDY_PAUSE_DEFAULT_SECONDS


def assemble_cindy_audio(segment_paths: list[Path], segment_texts: list[str], output_path: Path) -> Path:
    if len(segment_paths) != len(segment_texts):
        raise ValueError("segment_paths and segment_texts must have the same length.")
    if not segment_paths:
        raise ValueError("No Cindy audio segments to assemble.")

    final_audio = AudioSegment.silent(duration=80)

    for index, segment_path in enumerate(segment_paths):
        final_audio += AudioSegment.from_file(segment_path)
        if index < len(segment_paths) - 1:
            final_audio += AudioSegment.silent(duration=int(cindy_pause_seconds(segment_texts, index) * 1000))

    final_audio += AudioSegment.silent(duration=120)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    final_audio.export(output_path, format=output_path.suffix.lstrip(".") or "wav")
    return output_path


def write_metadata(metadata: list[dict], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return path


def generate_cindy_audio(
    script: str,
    output_path: Path,
    temp_dir: Path,
    metadata_path: Path,
    voice: str = CINDY_VOICE,
) -> dict:
    lines = script_lines(script)
    if not lines:
        raise RuntimeError("Cindy script is empty.")

    temp_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    from tts_kokoro import KokoroTTS

    tts = KokoroTTS(lang_code=CINDY_LANG_CODE, sample_rate=CINDY_SAMPLE_RATE)
    segment_paths: list[Path] = []
    metadata: list[dict] = []
    cursor_seconds = 0.08
    generation_start = time.perf_counter()

    print(f"Cindy script lines: {len(lines)}")
    print(f"Cindy voice: {voice}")
    print("Cindy audio mode: line-by-line with validated pauses and silence trim.")

    for index, text in enumerate(lines, start=1):
        segment_path = temp_dir / f"{index:03d}_cindy.wav"
        print(f"Generating Cindy segment {index}/{len(lines)} with voice '{voice}'...")
        tts.synthesize_to_file(text, voice, segment_path)
        trim_segment_silence(segment_path)
        duration = audio_duration_seconds(segment_path)
        start_time = cursor_seconds
        end_time = start_time + duration
        metadata.append(
            {
                "index": index,
                "speaker": "Cindy",
                "text": text,
                "voice": voice,
                "audio_path": str(segment_path),
                "start_time": round(start_time, 3),
                "end_time": round(end_time, 3),
                "duration": round(duration, 3),
            }
        )
        segment_paths.append(segment_path)
        cursor_seconds = end_time
        if index < len(lines):
            cursor_seconds += cindy_pause_seconds(lines, index - 1)

    assemble_cindy_audio(segment_paths, lines, output_path)
    write_metadata(metadata, metadata_path)
    audio_duration = audio_duration_seconds(output_path)

    return {
        "segments": len(lines),
        "voice": voice,
        "generation_seconds": round(time.perf_counter() - generation_start, 2),
        "duration": audio_duration,
        "audio_path": output_path,
        "metadata_path": metadata_path,
    }
