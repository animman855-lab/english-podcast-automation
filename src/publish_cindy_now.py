from datetime import datetime
from pathlib import Path
import json
import os
import shutil
import sys
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from airtable_client import AirtableClient, AirtableConfigError, AirtableRequestError, normalize_slot
from cindy_audio_builder import CINDY_VOICE, generate_cindy_audio, script_lines
from download_assets import AssetDownloadError, download_episode_assets
from subtitle_ass import generate_ass
from uploadpost_bridge import (
    UploadPostBridgeError,
    build_uploadpost_package,
    env_bool,
    optimize_thumbnail_for_uploadpost,
    submit_or_dry_run,
)
from video_renderer import probe_duration, render_video, require_ffmpeg


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"
TEMP_ROOT = PROJECT_ROOT / "temp"
CINDY_TABLE = "Cindy Long Form"
CINDY_UPLOAD_USER = "cindy"
CINDY_PLATFORMS = ["youtube", "facebook", "tiktok"]
SALOO_LINK = "https://apps.apple.com/app/saloo-english/id6770722987"
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


def workflow_config() -> dict:
    return {
        "slot": os.getenv("CINDY_SLOT", "10").strip() or "10",
        "timezone": os.getenv("CINDY_TIMEZONE", "America/Toronto").strip() or "America/Toronto",
        "voice": os.getenv("CINDY_VOICE", CINDY_VOICE).strip() or CINDY_VOICE,
        "table_name": os.getenv("AIRTABLE_TABLE_NAME_CINDY", CINDY_TABLE).strip() or CINDY_TABLE,
    }


def record_date_is_due(fields: dict, now: datetime) -> bool:
    publication_date = fields.get("Date Publication", "")
    if not publication_date:
        return False
    return publication_date <= now.date().isoformat()


def explain_candidate_rejection(fields: dict, expected_slot: str, now: datetime) -> str | None:
    raw_slot = fields.get("Slot", "")
    normalized_slot = normalize_slot(raw_slot)
    if not normalized_slot:
        return (
            f"Slot Airtable brut={raw_slot!r}; Slot Airtable normalise=invalid; "
            f"Slot attendu normalise={expected_slot}; raison=slot vide ou impossible a parser"
        )
    if normalized_slot != expected_slot:
        return (
            f"Slot Airtable brut={raw_slot!r}; Slot Airtable normalise={normalized_slot}; "
            f"Slot attendu normalise={expected_slot}; raison=slot different"
        )
    if not record_date_is_due(fields, now):
        return (
            f"Slot Airtable brut={raw_slot!r}; Slot Airtable normalise={normalized_slot}; "
            f"Slot attendu normalise={expected_slot}; raison=Date Publication pas encore due"
        )
    return None


def validate_record_fields(fields: dict) -> None:
    missing = [field for field in REQUIRED_FIELDS if not fields.get(field)]
    if missing:
        raise RuntimeError(f"Ready Cindy record is missing required field(s): {', '.join(missing)}")


def get_ready_cindy_record(client: AirtableClient, expected_slot: str, now: datetime) -> tuple[dict | None, list[str]]:
    formula = (
        "AND("
        "{Statut} = 'A publier',"
        "{Script} != '',"
        "{Lien Image} != '',"
        "{Lien Thumbnail} != '',"
        "{Lien Video} = ''"
        ")"
    )
    candidates = client.find_record_by_formula(formula, max_records=10)
    rejection_reasons: list[str] = []

    for candidate in candidates:
        fields = candidate.get("fields", {})
        rejection_reason = explain_candidate_rejection(fields, expected_slot, now)
        if rejection_reason:
            rejection_reasons.append(rejection_reason)
            continue
        return candidate, rejection_reasons

    return None, rejection_reasons


def build_cindy_description(title: str, script: str) -> str:
    excerpt = " ".join(script_lines(script)[:12])
    return "\n".join(
        [
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
    )


def main() -> int:
    load_dotenv(ENV_PATH)
    dry_run = env_bool("FORCE_DRY_RUN", default=env_bool("DRY_RUN", default=False))
    record_id = ""
    workflow_dir: Path | None = None

    try:
        require_ffmpeg()
        config = workflow_config()
        now = datetime.now(ZoneInfo(config["timezone"]))
        expected_slot = normalize_slot(config["slot"])
        if not expected_slot:
            raise RuntimeError(f"Invalid CINDY_SLOT value: {config['slot']}")

        client = AirtableClient(table_name=config["table_name"])
        record, rejection_reasons = get_ready_cindy_record(client, expected_slot, now)
        if not record:
            print("No eligible Cindy row found")
            print(
                "Expected: Statut=A publier, Date Publication<=now, "
                f"Slot={config['slot']} (normalized {expected_slot}), "
                "Script/Lien Image/Lien Thumbnail non-empty, Lien Video empty."
            )
            if rejection_reasons:
                print("Rejected ready Cindy rows:")
                for reason in rejection_reasons:
                    print(f"- {reason}")
            print(f"DRY_RUN={str(dry_run).lower()}. Nothing was published.")
            return 0

        record_id = record["id"]
        fields = record.get("fields", {})
        validate_record_fields(fields)

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
        print(f"DRY_RUN={str(dry_run).lower()}")
        print(f"Cindy voice: {config['voice']}")
        print("TikTok 9:16 renderer is not implemented yet; publishing the generated 16:9 video to all requested platforms.")

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

        audio_result = generate_cindy_audio(fields["Script"], audio_path, audio_dir, metadata_path, voice=config["voice"])
        print(
            f"Audio generated: {audio_result['audio_path']} "
            f"({audio_result['duration']:.1f}s, generation {audio_result['generation_seconds']:.1f}s)"
        )

        generate_ass(metadata_path, subtitles_path)
        print(f"Subtitles generated: {subtitles_path}")

        render_video(assets["image_path"], audio_path, subtitles_path, video_path)
        video_duration = probe_duration(video_path)
        print(f"Video generated: {video_path} ({video_duration:.1f}s)")

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

        upload_result = submit_or_dry_run(package, dry_run=dry_run)
        platform_urls = upload_result.get("platform_urls", {})
        youtube_url = upload_result.get("youtube_url", "")
        link_to_store = youtube_url or next(iter(platform_urls.values()), "")
        accepted = (
            upload_result.get("published")
            or upload_result.get("background_accepted")
            or (upload_result.get("upload_accepted") and upload_result.get("still_processing"))
        )

        if accepted and not dry_run:
            update_fields = {"Statut": "Publie"}
            if link_to_store:
                update_fields["Lien Video"] = link_to_store
            client.update_record(record_id, update_fields)
            print("Airtable Statut set to Publie.")
            if link_to_store:
                print(f"Airtable Lien Video set to: {link_to_store}")
            else:
                print("Lien Video left empty because Upload-Post did not return a URL yet.")
        elif dry_run:
            print("Dry-run complete. Airtable was not marked Publie and no Lien Video was written.")
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
                    "still_processing": upload_result.get("still_processing"),
                },
                indent=2,
            )
        )
        return 0

    except (AirtableConfigError, AirtableRequestError, AssetDownloadError, UploadPostBridgeError, Exception) as exc:
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
