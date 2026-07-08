from collections import Counter
from datetime import datetime
from pathlib import Path
import json
import shutil
import sys

from dotenv import load_dotenv

from airtable_client import AirtableClient, AirtableRequestError
from audio_assembler import assemble_audio, audio_duration_seconds, pause_after_text
from download_assets import download_episode_assets
from subtitle_ass import generate_ass
from tts_kokoro import KokoroTTS
from uploadpost_bridge import (
    UploadPostBridgeError,
    build_uploadpost_package,
    optimize_thumbnail_for_uploadpost,
    submit_or_dry_run,
)
from video_renderer import probe_duration, render_video, require_ffmpeg


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"
TEMP_ROOT = PROJECT_ROOT / "temp"
CINDY_TABLE = "Cindy Long Form"
CINDY_VOICE = "bf_emma"
CINDY_UPLOAD_USER = "cindy"
CINDY_PLATFORMS = ["youtube", "facebook", "tiktok"]
SALOO_LINK = "https://apps.apple.com/app/saloo-english/id6770722987"


def safe_slug(value: str) -> str:
    return "".join(character.lower() if character.isalnum() else "_" for character in value).strip("_")[:80]


def script_lines(script: str) -> list[str]:
    return [line.strip() for line in script.splitlines() if line.strip()]


def chunk_lines(lines: list[str], max_characters: int = 750) -> list[list[str]]:
    chunks: list[list[str]] = []
    current: list[str] = []
    current_length = 0

    for line in lines:
        next_length = current_length + len(line) + 1
        if current and next_length > max_characters:
            chunks.append(current)
            current = []
            current_length = 0
        current.append(line)
        current_length += len(line) + 1

    if current:
        chunks.append(current)
    return chunks


def line_timings_for_chunk(lines: list[str], start_time: float, duration: float) -> list[dict]:
    weights = [max(1, len(line)) for line in lines]
    total_weight = sum(weights)
    cursor = start_time
    timings: list[dict] = []

    for index, line in enumerate(lines):
        if index == len(lines) - 1:
            end_time = start_time + duration
        else:
            end_time = cursor + duration * (weights[index] / total_weight)
        timings.append(
            {
                "text": line,
                "start_time": cursor,
                "end_time": end_time,
                "duration": end_time - cursor,
            }
        )
        cursor = end_time

    return timings


def write_metadata(metadata: list[dict], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return path


def generate_cindy_audio(script: str, output_path: Path, temp_dir: Path, metadata_path: Path) -> dict:
    lines = script_lines(script)
    if not lines:
        raise RuntimeError("Cindy script is empty.")

    tts = KokoroTTS(lang_code="a", sample_rate=24000)
    temp_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    segment_paths = []
    segment_texts = []
    metadata = []
    cursor_seconds = 0.15
    chunks = chunk_lines(lines)
    line_index = 1

    print(f"Cindy script lines: {len(lines)}")
    print(f"Cindy TTS chunks: {len(chunks)}")

    for chunk_index, chunk in enumerate(chunks, start=1):
        text = "\n".join(chunk)
        segment_path = temp_dir / f"{chunk_index:03d}_cindy_chunk.wav"
        print(f"Generating Cindy TTS chunk {chunk_index}/{len(chunks)} with voice '{CINDY_VOICE}'...")
        tts.synthesize_to_file(text, CINDY_VOICE, segment_path)
        duration = audio_duration_seconds(segment_path)
        start_time = cursor_seconds
        end_time = start_time + duration
        for timing in line_timings_for_chunk(chunk, start_time, duration):
            metadata.append(
                {
                    "index": line_index,
                    "speaker": "Cindy",
                    "text": timing["text"],
                    "voice": CINDY_VOICE,
                    "audio_path": str(segment_path),
                    "start_time": round(timing["start_time"], 3),
                    "end_time": round(timing["end_time"], 3),
                    "duration": round(timing["duration"], 3),
                }
            )
            line_index += 1
        segment_paths.append(segment_path)
        segment_texts.append(text)
        cursor_seconds = end_time
        if chunk_index < len(chunks):
            cursor_seconds += pause_after_text(chunk[-1], 0.75, 1.0, 0.9)

    assemble_audio(
        segment_paths=segment_paths,
        segment_texts=segment_texts,
        output_path=output_path,
        default_pause_seconds=0.75,
        question_pause_seconds=1.0,
        long_reply_pause_seconds=0.9,
    )
    write_metadata(metadata, metadata_path)

    return {
        "segments": len(lines),
        "voice": CINDY_VOICE,
        "duration": audio_duration_seconds(output_path),
        "audio_path": output_path,
        "metadata_path": metadata_path,
    }


def build_cindy_description(title: str, script: str) -> str:
    excerpt = " ".join(script_lines(script)[:12])
    lines = [
        "Practice real English conversations with Saloo English:",
        SALOO_LINK,
        "",
        f"In this Cindy long-form shadowing practice, we train: {title}.",
        "",
        "Listen first, repeat out loud, and copy the rhythm of calm natural English.",
        "This practice is for learners who understand English but freeze when it is time to speak.",
        "",
        "Use Saloo English to practice real conversations, build speaking confidence, and stop blocking when you need to answer.",
        "",
        "Practice focus:",
        excerpt[:500].rstrip() + ("..." if len(excerpt) > 500 else ""),
        "",
        "#EnglishShadowing #SpeakEnglish #EnglishListening #EnglishPractice #LearnEnglish #SpokenEnglish #EnglishSpeaking #SalooEnglish",
    ]
    return "\n".join(lines)


def get_ready_cindy_record(client: AirtableClient) -> dict | None:
    formula = (
        "AND("
        "OR({Statut} = 'A publier', {Statut} = 'En cours'),"
        "{Script} != '',"
        "{Lien Image} != '',"
        "{Lien Thumbnail} != '',"
        "{Lien Video} = ''"
        ")"
    )
    records = client.find_record_by_formula(formula, max_records=1)
    return records[0] if records else None


def main() -> int:
    load_dotenv(ENV_PATH)
    record_id = ""
    workflow_dir: Path | None = None

    try:
        require_ffmpeg()
        client = AirtableClient(table_name=CINDY_TABLE)
        record = get_ready_cindy_record(client)
        if not record:
            print("No eligible Cindy row found.")
            print("Expected one row with Statut=A publier, Script/Lien Image/Lien Thumbnail non-empty, Lien Video empty.")
            return 0

        record_id = record["id"]
        fields = record.get("fields", {})
        title = fields["Titre"]
        workflow_dir = TEMP_ROOT / f"cindy_publish_{record_id}_{safe_slug(title)}"
        assets_dir = workflow_dir / "assets"
        audio_dir = workflow_dir / "audio_segments"
        output_dir = workflow_dir / "output"
        package_path = workflow_dir / "uploadpost_package.json"
        audio_path = output_dir / "cindy_audio.wav"
        metadata_path = workflow_dir / "segments_metadata.json"
        subtitles_path = workflow_dir / "subtitles.ass"
        video_path = output_dir / "cindy_video_16x9.mp4"

        print(f"Processing Cindy record: {record_id}")
        print(f"Title: {title}")
        print("Publishing now: ignoring normal slot window.")

        client.update_record(record_id, {"Statut": "En cours"})
        print("Airtable Statut set to En cours.")

        assets = download_episode_assets(fields["Lien Image"], fields["Lien Thumbnail"], assets_dir)
        print(f"Main image downloaded: {assets['image_path']}")
        print(f"Thumbnail downloaded: {assets['thumbnail_path']}")

        thumbnail_optimized_path = assets_dir / "thumbnail_optimized.jpg"
        try:
            thumbnail_result = optimize_thumbnail_for_uploadpost(assets["thumbnail_path"], thumbnail_optimized_path)
            print(f"Original thumbnail size: {thumbnail_result['original_size_bytes']} bytes")
            print(f"Optimized thumbnail size: {thumbnail_result['optimized_size_bytes']} bytes")
        except UploadPostBridgeError as exc:
            thumbnail_optimized_path = None
            print(f"WARNING: Thumbnail optimization failed; falling back to thumbnail_url. Error: {exc}")

        audio_result = generate_cindy_audio(fields["Script"], audio_path, audio_dir, metadata_path)
        print(f"Audio generated: {audio_result['audio_path']} ({audio_result['duration']:.1f}s)")

        generate_ass(metadata_path, subtitles_path)
        print(f"Subtitles generated: {subtitles_path}")

        render_video(assets["image_path"], audio_path, subtitles_path, video_path)
        video_duration = probe_duration(video_path)
        print(f"Video generated: {video_path} ({video_duration:.1f}s)")
        print("TikTok 9:16 renderer is not implemented yet; publishing the generated 16:9 video to all requested platforms.")

        package = build_uploadpost_package(
            video_path=video_path,
            thumbnail_path=assets["thumbnail_path"],
            thumbnail_optimized_path=thumbnail_optimized_path,
            thumbnail_url=fields["Lien Thumbnail"],
            title=title,
            description=build_cindy_description(title, fields["Script"]),
            publish_datetime=None,
            output_path=package_path,
            user=CINDY_UPLOAD_USER,
            platforms=CINDY_PLATFORMS,
        )
        print(f"Upload-Post package prepared: {package_path}")

        upload_result = submit_or_dry_run(package, dry_run=False)
        platform_urls = upload_result.get("platform_urls", {})
        youtube_url = upload_result.get("youtube_url", "")
        link_to_store = youtube_url or next(iter(platform_urls.values()), "")

        if upload_result.get("published") or upload_result.get("background_accepted"):
            update_fields = {"Statut": "Publie"}
            if link_to_store:
                update_fields["Lien Video"] = link_to_store
            client.update_record(record_id, update_fields)
            print("Airtable Statut set to Publie.")
            if link_to_store:
                print(f"Airtable Lien Video set to: {link_to_store}")
        else:
            raise RuntimeError("Upload-Post did not confirm publication acceptance.")

        print()
        print("Cindy publish summary:")
        print(
            json.dumps(
                {
                    "record_id": record_id,
                    "title": title,
                    "platforms": CINDY_PLATFORMS,
                    "platform_successes": upload_result.get("platform_successes", []),
                    "platform_urls": platform_urls,
                    "youtube_url": youtube_url,
                    "request_id": upload_result.get("request_id", ""),
                    "published": upload_result.get("published"),
                    "background_accepted": upload_result.get("background_accepted"),
                },
                indent=2,
            )
        )
        return 0

    except (AirtableRequestError, UploadPostBridgeError, Exception) as exc:
        print()
        print("Cindy publish failed.")
        print(f"Error: {exc}")
        if record_id:
            print("Record was left as En cours to avoid duplicate publishing.")
        return 1
    finally:
        if workflow_dir and workflow_dir.exists():
            shutil.rmtree(workflow_dir, ignore_errors=True)
            print("Temporary Cindy workflow files deleted.")


if __name__ == "__main__":
    sys.exit(main())
