from pathlib import Path
import traceback

import yaml

from audio_assembler import assemble_audio, audio_duration_seconds
from script_parser import parse_script
from tts_kokoro import KokoroTTS


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config" / "voice_audition.yaml"
SCRIPT_PATH = PROJECT_ROOT / "input" / "voice_audition_script.txt"
TEMP_DIR = PROJECT_ROOT / "temp" / "voice_auditions"
OUTPUT_DIR = PROJECT_ROOT / "output" / "voice_auditions"


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def clean_voice_filename(voice: str) -> str:
    return "".join(character if character.isalnum() or character in ("_", "-") else "_" for character in voice)


def discover_english_voices() -> list[str]:
    try:
        from huggingface_hub import list_repo_files

        files = list_repo_files("hexgrad/Kokoro-82M")
        voices = [
            Path(file).stem
            for file in files
            if file.startswith("voices/")
            and file.endswith(".pt")
            and Path(file).stem.startswith(("af_", "am_", "bf_", "bm_"))
        ]
        return sorted(voices)
    except Exception:
        return []


def synthesize_individual_samples(tts: KokoroTTS, voices: list[str], text: str) -> tuple[list[Path], list[str]]:
    generated: list[Path] = []
    errors: list[str] = []

    for voice in voices:
        output_path = OUTPUT_DIR / f"voice_{clean_voice_filename(voice)}.wav"
        try:
            print(f"Generating individual sample: {voice}")
            tts.synthesize_to_file(text=text, voice=voice, output_path=output_path)
            generated.append(output_path)
        except Exception as exc:
            errors.append(f"{voice}: {exc}")

    return generated, errors


def synthesize_pair_tests(
    tts: KokoroTTS,
    pair_tests: list[dict],
    pause_config: dict,
) -> tuple[list[Path], list[str]]:
    generated: list[Path] = []
    errors: list[str] = []
    dialogue_segments = parse_script(SCRIPT_PATH)

    for pair in pair_tests:
        name = pair["name"]
        host_voice = pair["host_voice"]
        guest_voice = pair["guest_voice"]
        segment_paths: list[Path] = []
        segment_texts: list[str] = []
        pair_temp_dir = TEMP_DIR / name
        pair_temp_dir.mkdir(parents=True, exist_ok=True)

        try:
            print(f"Generating pair test: {name} ({host_voice} + {guest_voice})")
            for index, segment in enumerate(dialogue_segments, start=1):
                voice = host_voice if segment.speaker == "Host" else guest_voice
                segment_path = pair_temp_dir / f"{index:03d}_{segment.speaker.lower()}_{clean_voice_filename(voice)}.wav"
                tts.synthesize_to_file(text=segment.text, voice=voice, output_path=segment_path)
                segment_paths.append(segment_path)
                segment_texts.append(segment.text)

            output_path = OUTPUT_DIR / f"{name}.wav"
            assemble_audio(
                segment_paths=segment_paths,
                segment_texts=segment_texts,
                output_path=output_path,
                default_pause_seconds=float(pause_config.get("default", 0.5)),
                question_pause_seconds=float(pause_config.get("after_question", 0.65)),
                long_reply_pause_seconds=float(pause_config.get("after_long_reply", 0.6)),
            )
            generated.append(output_path)
        except Exception as exc:
            errors.append(f"{name} ({host_voice} + {guest_voice}): {exc}")

    return generated, errors


def print_voice_groups(voices: list[str]) -> None:
    if not voices:
        print("Discovered English voices: unavailable in this environment.")
        return

    groups = {
        "American female": [voice for voice in voices if voice.startswith("af_")],
        "American male": [voice for voice in voices if voice.startswith("am_")],
        "British female": [voice for voice in voices if voice.startswith("bf_")],
        "British male": [voice for voice in voices if voice.startswith("bm_")],
    }
    print("Discovered English voices:")
    for label, group in groups.items():
        print(f"- {label}: {', '.join(group) if group else 'none'}")


def main() -> int:
    config = load_config()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    voices_to_test = config.get("voices_to_test", [])
    pair_tests = config.get("pair_tests", [])
    individual_text = config["individual_sample_text"]
    pause_config = config.get("pause_seconds", {})

    print_voice_groups(discover_english_voices())
    print()
    print(config.get("note", ""))
    print()

    all_generated: list[Path] = []
    all_errors: list[str] = []

    try:
        tts = KokoroTTS(
            lang_code=config.get("lang_code", "a"),
            sample_rate=int(config.get("sample_rate", 24000)),
        )

        individual_files, individual_errors = synthesize_individual_samples(tts, voices_to_test, individual_text)
        pair_files, pair_errors = synthesize_pair_tests(tts, pair_tests, pause_config)
        all_generated.extend(individual_files)
        all_generated.extend(pair_files)
        all_errors.extend(individual_errors)
        all_errors.extend(pair_errors)

        print()
        print("Voice audition complete.")
        print(f"Voices tested: {', '.join(voices_to_test)}")
        print("Pairs tested:")
        for pair in pair_tests:
            print(f"- {pair['name']}: Host={pair['host_voice']} Guest={pair['guest_voice']}")
        print("Files generated:")
        for path in all_generated:
            print(f"- {path} ({audio_duration_seconds(path):.1f}s)")

        if all_errors:
            print("Errors:")
            for error in all_errors:
                print(f"- {error}")
            print("Recommendation: remove failed voices from config/voice_audition.yaml or verify the voice exists in Kokoro.")
            return 1

        print("Errors: none")
        print("Recommendation: listen for clarity, warmth, speaker contrast, and comfortable B1/B2 pacing before updating config/voices.yaml.")
        return 0

    except Exception as exc:
        print()
        print("Voice audition failed.")
        print(f"Error: {exc}")
        print()
        traceback.print_exc()
        print()
        print("Try:")
        print("  pip install -r requirements.txt")
        print("  python src/voice_audition.py")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
