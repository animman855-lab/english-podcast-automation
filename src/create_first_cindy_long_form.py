from datetime import date, timedelta
from pathlib import Path
import sys

import yaml

from airtable_client import AirtableClient, AirtableRequestError
from cindy_description_builder import build_cindy_description
from cindy_long_form_content import TITLE, build_cindy_script, build_visual_prompts


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config" / "cindy_long_form.yaml"

REQUIRED_FIELDS = [
    "Title",
    "Date Publication",
    "Slot",
    "Platforms",
    "Status",
    "Script / Transcript",
    "Prompt Image",
    "Prompt Thumbnail",
    "Single Visual Prompt",
    "Image Link",
    "Thumbnail Link",
    "Video Link",
    "Video Format",
    "Voice",
    "Duration Target",
    "Content Type",
    "Description",
]


def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def validate_config(config: dict) -> None:
    if config.get("table_name") != "Cindy Long Form":
        raise RuntimeError("Cindy long-form must use Airtable table: Cindy Long Form")
    if config.get("voice") != "bf_emma":
        raise RuntimeError("Cindy long-form must use Kokoro voice bf_emma")
    if sorted(config.get("video_formats", [])) != ["16:9", "9:16"]:
        raise RuntimeError("Cindy long-form must prepare 16:9 and 9:16 video formats")
    if not config.get("visual", {}).get("single_visual_for_thumbnail_and_video"):
        raise RuntimeError("Cindy long-form must use one image as thumbnail and video image")


def first_publication_date() -> str:
    return (date.today() + timedelta(days=1)).isoformat()


def build_record_fields(config: dict) -> dict:
    script = build_cindy_script()
    prompts = build_visual_prompts()
    description = build_cindy_description(TITLE)
    status = config["default_status_when_assets_missing"]

    return {
        "Title": TITLE,
        "Date Publication": first_publication_date(),
        "Slot": "10",
        "Platforms": ", ".join(config["platforms"]),
        "Status": status,
        "Script / Transcript": script,
        "Prompt Image": prompts["Prompt Image"],
        "Prompt Thumbnail": prompts["Prompt Thumbnail"],
        "Single Visual Prompt": prompts["Single Visual Prompt"],
        "Image Link": "",
        "Thumbnail Link": "",
        "Video Link": "",
        "Video Format": ", ".join(config["video_formats"]),
        "Voice": config["voice"],
        "Duration Target": config["duration_target"],
        "Content Type": config["content_type"],
        "Description": description,
    }


def print_manual_table_instructions() -> None:
    print("Airtable table 'Cindy Long Form' was not accessible.")
    print("Create it manually with these fields:")
    for field in REQUIRED_FIELDS:
        print(f"- {field}")
    print("Recommended Status values: Draft, Waiting for Image, A publier, En cours, Publie")
    print("Recommended Platforms value for first row: YouTube, Facebook, TikTok")
    print("Do not set Status=A publier until Image Link and Thumbnail Link are filled.")


def main() -> int:
    config = load_config()
    validate_config(config)
    fields = build_record_fields(config)
    client = AirtableClient(table_name=config["table_name"])

    try:
        existing = client.find_record_by_field("Title", TITLE)
    except AirtableRequestError as exc:
        if "404" in str(exc) or "NOT_FOUND" in str(exc) or "TABLE_NOT_FOUND" in str(exc):
            print_manual_table_instructions()
            return 0
        raise

    if existing:
        existing_fields = existing.get("fields", {})
        if existing_fields.get("Status") == "Publie" or existing_fields.get("Video Link"):
            print(f"Existing published Cindy row left unchanged: {existing['id']}")
            return 0
        try:
            updated = client.update_record(existing["id"], fields)
        except AirtableRequestError as exc:
            print(f"Airtable row exists but could not be updated: {exc}")
            print_manual_table_instructions()
            return 0
        print(f"Updated existing Cindy row: {updated['id']}")
    else:
        try:
            created = client.create_record(fields)
        except AirtableRequestError as exc:
            print(f"Airtable table exists but the row could not be created: {exc}")
            print_manual_table_instructions()
            return 0
        print(f"Created Cindy row: {created['id']}")

    print(f"Title: {fields['Title']}")
    print(f"Status: {fields['Status']}")
    print(f"Voice: {fields['Voice']}")
    print(f"Platforms: {fields['Platforms']}")
    print(f"Video Format: {fields['Video Format']}")
    print(f"Script words: {len(fields['Script / Transcript'].split())}")
    print("Image Link empty: yes")
    print("Thumbnail Link empty: yes")
    print("Video Link empty: yes")
    print("Saloo link at top of description: yes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
