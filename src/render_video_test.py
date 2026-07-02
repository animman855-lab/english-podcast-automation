from pathlib import Path
import subprocess
import sys

import main as audio_main
from subtitle_ass import generate_ass
from video_renderer import (
    DEFAULT_AUDIO_PATH,
    DEFAULT_IMAGE_PATH,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_SUBTITLE_PATH,
    ensure_sample_image,
    probe_duration,
    render_video,
    require_ffmpeg,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
METADATA_PATH = PROJECT_ROOT / "temp" / "segments_metadata.json"


def run_audio_pipeline_if_needed() -> None:
    if DEFAULT_AUDIO_PATH.exists() and METADATA_PATH.exists():
        return

    print("Audio or segment metadata missing. Running audio pipeline first...")
    exit_code = audio_main.main()
    if exit_code != 0:
        raise RuntimeError("Audio pipeline failed, video test cannot continue.")


def verify_phase_1_command() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", "src/main.py"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr)


def main() -> int:
    try:
        require_ffmpeg()
        print("FFmpeg check: ffmpeg and ffprobe are available.")

        verify_phase_1_command()
        run_audio_pipeline_if_needed()

        image_path = ensure_sample_image(DEFAULT_IMAGE_PATH)
        subtitle_path = generate_ass(METADATA_PATH, DEFAULT_SUBTITLE_PATH)
        video_path = render_video(image_path, DEFAULT_AUDIO_PATH, subtitle_path, DEFAULT_OUTPUT_PATH)
        duration = probe_duration(video_path)

        print()
        print("Phase 2 video test complete.")
        print(f"Main image: {image_path}")
        print(f"Audio used: {DEFAULT_AUDIO_PATH}")
        print(f"Segments metadata: {METADATA_PATH}")
        print(f"Subtitles ASS: {subtitle_path}")
        print("Waveform: added above the subtitle area")
        print("Subtitle style: large, bottom-center, phrase-by-phrase, no Host/Guest labels")
        print(f"Video duration: {duration:.1f}s")
        print(f"Generated video: {video_path}")
        return 0

    except Exception as exc:
        print()
        print("Phase 2 video test failed.")
        print(f"Error: {exc}")
        print()
        print("If FFmpeg is missing, install it and make sure ffmpeg/ffprobe are in PATH.")
        print("Windows: winget install Gyan.FFmpeg")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
