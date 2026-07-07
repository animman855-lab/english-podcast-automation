from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from airtable_client import AirtableClient, AirtableRequestError
from airtable_client import airtable_formula_string
from cindy_long_form_content import TITLE, build_cindy_script, build_visual_prompts


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config" / "cindy_long_form.yaml"

REQUIRED_FIELDS = [
    "Titre",
    "Date Publication",
    "Slot",
    "Video Type",
    "Statut",
    "Script",
    "Prompt Image",
    "Lien Image",
    "Prompt Thumbnail",
    "Lien Thumbnail",
    "Lien Video",
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
    try:
        return datetime.now(ZoneInfo("America/Toronto")).date().isoformat()
    except ZoneInfoNotFoundError:
        return datetime.now().date().isoformat()


def build_record_fields(config: dict) -> dict:
    script = build_cindy_script()
    prompts = build_visual_prompts()

    return {
        "Titre": TITLE,
        "Date Publication": first_publication_date(),
        "Slot": "10",
        "Video Type": config["video_type"],
        "Statut": config["default_status"],
        "Script": script,
        "Prompt Image": prompts["Prompt Image"],
        "Lien Image": "",
        "Prompt Thumbnail": prompts["Prompt Thumbnail"],
        "Lien Thumbnail": "",
        "Lien Video": "",
    }


def print_manual_table_instructions() -> None:
    print("Airtable table 'Cindy Long Form' was not accessible.")
    print("Create it manually with these fields:")
    for field in REQUIRED_FIELDS:
        print(f"- {field}")
    print("Recommended Statut values: A publier, En cours, Publie")
    print("Future Cindy publishing must refuse rows where Lien Image or Lien Thumbnail is empty.")


def find_existing_cindy_row(client: AirtableClient, fields: dict) -> dict | None:
    formula = f"{{Titre}} = {airtable_formula_string(fields['Titre'])}"
    records = client.find_record_by_formula(formula, max_records=10)
    for record in records:
        record_fields = record.get("fields", {})
        if (
            record_fields.get("Date Publication") == fields["Date Publication"]
            and str(record_fields.get("Slot", "")).strip() == fields["Slot"]
        ):
            return record
    return None


def cindy_row_is_publishable(fields: dict, now_date: str | None = None) -> bool:
    publication_date = fields.get("Date Publication", "")
    due_date = now_date or first_publication_date()
    return all(
        [
            fields.get("Statut") == "A publier",
            publication_date <= due_date,
            str(fields.get("Slot", "")).strip() == "10",
            bool(fields.get("Script")),
            bool(fields.get("Lien Image")),
            bool(fields.get("Lien Thumbnail")),
            not fields.get("Lien Video"),
        ]
    )


def main() -> int:
    config = load_config()
    validate_config(config)
    fields = build_record_fields(config)
    client = AirtableClient(table_name=config["table_name"])

    try:
        existing = find_existing_cindy_row(client, fields)
    except AirtableRequestError as exc:
        if "404" in str(exc) or "NOT_FOUND" in str(exc) or "TABLE_NOT_FOUND" in str(exc):
            print_manual_table_instructions()
            return 0
        raise

    if existing:
        existing_fields = existing.get("fields", {})
        if existing_fields.get("Statut") == "Publie" or existing_fields.get("Lien Video"):
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

    print(f"Titre: {fields['Titre']}")
    print(f"Statut: {fields['Statut']}")
    print(f"Date Publication: {fields['Date Publication']}")
    print(f"Slot: {fields['Slot']}")
    print(f"Video Type: {fields['Video Type']}")
    print(f"Script words: {len(fields['Script'].split())}")
    print("Lien Image empty: yes")
    print("Lien Thumbnail empty: yes")
    print("Lien Video empty: yes")
    print(f"Future publishable now: {cindy_row_is_publishable(fields)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
