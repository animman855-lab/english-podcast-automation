from datetime import datetime
from pathlib import Path
import json
import shutil
import sys

from dotenv import load_dotenv

from airtable_client import AirtableClient, AirtableConfigError, AirtableRequestError
from description_builder import build_youtube_description
from download_assets import AssetDownloadError, download_episode_assets
from main import generate_audio_from_script
from subtitle_ass import generate_ass
from uploadpost_bridge import UploadPostBridgeError, build_uploadpost_package, env_bool, submit_or_dry_run
from video_renderer import probe_duration, render_video, require_ffmpeg


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"
TEMP_ROOT = PROJECT_ROOT / "temp"


REQUIRED_FIELDS = [
    "Titre",
    "Date Publication",
    "Slot",
    "Video Type",
    "Statut",
    "Script",
    "Lien Image",
    "Lien Thumbnail",
]


def safe_slug(value: str) -> str:
    return "".join(character.lower() if character.isalnum() else "_" for character in value).strip("_")[:80]


def publish_datetime_from_fields(fields: dict) -> str | None:
    publication_date = fields.get("Date Publication", "")
    slot = fields.get("Slot", "")
    if not publication_date:
        return None
    if not slot:
        return publication_date
    return f"{publication_date}T{slot}:00"


def validate_record_fields(fields: dict) -> None:
    missing = [field for field in REQUIRED_FIELDS if not fields.get(field)]
    if missing:
        raise RuntimeError(f"Ready Airtable record is missing required field(s): {', '.join(missing)}")


def write_script(script: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(script.strip() + "\n", encoding="utf-8")
    return path


def main() -> int:
    load_dotenv(ENV_PATH)
    dry_run = env_bool("DRY_RUN", default=True)
    client: AirtableClient | None = None
    record_id = ""
    workflow_dir: Path | None = None

    try:
        require_ffmpeg()
        client = AirtableClient()

        record = client.find_ready_record()
        if not record:
            print("No ready Airtable record found.")
            print("Expected: Statut=A publier, Script/Lien Image/Lien Thumbnail non-empty, Lien Video empty.")
            print(f"DRY_RUN={str(dry_run).lower()}. Nothing was published.")
            return 0

        record_id = record["id"]
        fields = record.get("fields", {})
        validate_record_fields(fields)

        title = fields["Titre"]
        workflow_dir = TEMP_ROOT / f"workflow_{record_id}_{safe_slug(title)}"
        assets_dir = workflow_dir / "assets"
        audio_dir = workflow_dir / "audio_segments"
        output_dir = workflow_dir / "output"
        package_path = workflow_dir / "uploadpost_package.json"
        script_path = workflow_dir / "script.txt"
        audio_path = output_dir / "podcast_audio.wav"
        metadata_path = workflow_dir / "segments_metadata.json"
        subtitles_path = workflow_dir / "subtitles.ass"
        video_path = output_dir / "podcast_video.mp4"

        print(f"Processing Airtable record: {record_id}")
        print(f"Title: {title}")
        print(f"DRY_RUN={str(dry_run).lower()}")

        client.update_record(record_id, {"Statut": "En cours"})
        print("Airtable Statut set to En cours.")

        assets = download_episode_assets(fields["Lien Image"], fields["Lien Thumbnail"], assets_dir)
        print(f"Main image downloaded: {assets['image_path']}")
        print(f"Thumbnail downloaded: {assets['thumbnail_path']}")

        write_script(fields["Script"], script_path)
        audio_result = generate_audio_from_script(
            script_path=script_path,
            output_path=audio_path,
            temp_dir=audio_dir,
            metadata_path=metadata_path,
        )
        print(f"Audio generated: {audio_result['audio_path']} ({audio_result['duration']:.1f}s)")

        generate_ass(metadata_path, subtitles_path)
        print(f"Subtitles generated: {subtitles_path}")

        render_video(assets["image_path"], audio_path, subtitles_path, video_path)
        video_duration = probe_duration(video_path)
        print(f"Video generated: {video_path} ({video_duration:.1f}s)")

        description = build_youtube_description(title, fields["Script"])
        package = build_uploadpost_package(
            video_path=video_path,
            thumbnail_path=assets["thumbnail_path"],
            title=title,
            description=description,
            publish_datetime=publish_datetime_from_fields(fields),
            output_path=package_path,
        )
        print(f"Upload-Post package prepared: {package_path}")

        upload_result = submit_or_dry_run(package, dry_run=dry_run)

        if upload_result.get("published"):
            youtube_url = upload_result.get("youtube_url", "")
            if not youtube_url:
                raise RuntimeError("Upload-Post published but did not return a YouTube URL.")
            client.update_record(record_id, {"Lien Video": youtube_url, "Statut": "Publie"})
            print(f"Airtable updated with YouTube URL: {youtube_url}")
            if workflow_dir:
                shutil.rmtree(workflow_dir, ignore_errors=True)
                print("Temporary workflow files deleted after publication.")
        else:
            print("Dry-run complete. Airtable was not marked Publie and no Lien Video was written.")

        print()
        print("Workflow summary:")
        print(json.dumps(
            {
                "record_id": record_id,
                "title": title,
                "dry_run": dry_run,
                "video_path": str(video_path),
                "thumbnail_path": str(assets["thumbnail_path"]),
                "package_path": str(package_path),
                "published": bool(upload_result.get("published")),
                "youtube_url": upload_result.get("youtube_url", ""),
            },
            indent=2,
        ))
        return 0

    except (AirtableConfigError, AirtableRequestError, AssetDownloadError, UploadPostBridgeError, Exception) as exc:
        print()
        print("Workflow failed.")
        print(f"Error: {exc}")
        if record_id:
            print("Record was left as En cours to avoid duplicate or partial publishing.")
        print("Nothing was published by this script unless Upload-Post explicitly completed before the error.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
