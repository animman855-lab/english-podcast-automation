from collections import Counter
import json
from pathlib import Path
import sys
import traceback

import yaml

from audio_assembler import assemble_audio, audio_duration_seconds, pause_after_text
from script_parser import parse_script
from tts_kokoro import KokoroTTS


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config" / "voices.yaml"
SCRIPT_PATH = PROJECT_ROOT / "input" / "sample_episode.txt"
TEMP_DIR = PROJECT_ROOT / "temp"
OUTPUT_PATH = PROJECT_ROOT / "output" / "podcast_audio_test.wav"
METADATA_PATH = PROJECT_ROOT / "temp" / "segments_metadata.json"
FORBIDDEN_PRODUCTION_VOICES = {"am_adam"}
FORBIDDEN_VOICE_MESSAGE = (
    "am_adam is forbidden for production podcast audio. "
    "Use af_heart for Host and am_echo for Guest."
)


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def validate_production_voices(host_voice: str, guest_voice: str) -> None:
    if host_voice in FORBIDDEN_PRODUCTION_VOICES or guest_voice in FORBIDDEN_PRODUCTION_VOICES:
        raise ValueError(FORBIDDEN_VOICE_MESSAGE)


def write_segments_metadata(
    metadata: list[dict],
    output_path: Path = METADATA_PATH,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return output_path


def generate_audio_from_script(
    script_path: Path = SCRIPT_PATH,
    output_path: Path = OUTPUT_PATH,
    temp_dir: Path = TEMP_DIR,
    metadata_path: Path = METADATA_PATH,
) -> dict:
    config = load_config()
    segments = parse_script(script_path)
    counts = Counter(segment.speaker for segment in segments)

    host_voice = config["host_voice"]
    guest_voice = config["guest_voice"]
    validate_production_voices(host_voice, guest_voice)
    lang_code = config.get("lang_code", "a")
    sample_rate = int(config.get("sample_rate", 24000))
    pause_config = config.get("pause_seconds", {})

    temp_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tts = KokoroTTS(lang_code=lang_code, sample_rate=sample_rate)

    segment_paths: list[Path] = []
    segment_texts: list[str] = []
    segments_metadata: list[dict] = []
    cursor_seconds = 0.15

    for index, segment in enumerate(segments, start=1):
        voice = host_voice if segment.speaker == "Host" else guest_voice
        segment_path = temp_dir / f"{index:03d}_{segment.speaker.lower()}.wav"
        print(f"Generating {segment.speaker} segment {index}/{len(segments)} with voice '{voice}'...")
        tts.synthesize_to_file(segment.text, voice, segment_path)
        duration = audio_duration_seconds(segment_path)
        start_time = cursor_seconds
        end_time = start_time + duration
        segments_metadata.append(
            {
                "index": index,
                "speaker": segment.speaker,
                "text": segment.text,
                "voice": voice,
                "audio_path": str(segment_path),
                "start_time": round(start_time, 3),
                "end_time": round(end_time, 3),
                "duration": round(duration, 3),
            }
        )
        segment_paths.append(segment_path)
        segment_texts.append(segment.text)
        cursor_seconds = end_time
        if index < len(segments):
            cursor_seconds += pause_after_text(
                segment.text,
                float(pause_config.get("default", 0.5)),
                float(pause_config.get("after_question", 0.65)),
                float(pause_config.get("after_long_reply", 0.6)),
            )

    assemble_audio(
        segment_paths=segment_paths,
        segment_texts=segment_texts,
        output_path=output_path,
        default_pause_seconds=float(pause_config.get("default", 0.5)),
        question_pause_seconds=float(pause_config.get("after_question", 0.65)),
        long_reply_pause_seconds=float(pause_config.get("after_long_reply", 0.6)),
    )
    written_metadata_path = write_segments_metadata(segments_metadata, metadata_path)
    duration = audio_duration_seconds(output_path)

    return {
        "host_replies": counts.get("Host", 0),
        "guest_replies": counts.get("Guest", 0),
        "host_voice": host_voice,
        "guest_voice": guest_voice,
        "duration": duration,
        "audio_path": output_path,
        "metadata_path": written_metadata_path,
    }


def main() -> int:
    try:
        result = generate_audio_from_script()

        print()
        print("Audio test complete.")
        print(f"Host replies: {result['host_replies']}")
        print(f"Guest replies: {result['guest_replies']}")
        print(f"Host voice: {result['host_voice']}")
        print(f"Guest voice: {result['guest_voice']}")
        print(f"Approx final duration: {result['duration']:.1f}s")
        print(f"Generated file: {result['audio_path']}")
        print(f"Segments metadata: {result['metadata_path']}")
        return 0

    except Exception as exc:
        print()
        print("Audio test failed.")
        print(f"Error: {exc}")
        print()
        print("Full traceback:")
        traceback.print_exc()
        print()
        print("Probable causes:")
        print("- Kokoro or one of its Python dependencies is not installed.")
        print("- espeak-ng is missing or not available in PATH.")
        print("- The first Kokoro model download failed or network access was unavailable.")
        print()
        print("Try:")
        print("  pip install -r requirements.txt")
        print("  winget install eSpeak-NG.eSpeak-NG")
        print("  python src/main.py")
        return 1


if __name__ == "__main__":
    sys.exit(main())
