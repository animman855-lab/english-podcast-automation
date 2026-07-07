from pathlib import Path
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"


class AirtableConfigError(RuntimeError):
    pass


class AirtableRequestError(RuntimeError):
    pass


def load_airtable_env(table_name_env: str = "AIRTABLE_TABLE_NAME", default_table_name: str = "English Podcast Publishing Clean") -> dict[str, str]:
    load_dotenv(ENV_PATH)
    env_values = {
        "AIRTABLE_API_KEY": os.getenv("AIRTABLE_API_KEY", "").strip(),
        "AIRTABLE_BASE_ID": os.getenv("AIRTABLE_BASE_ID", "").strip(),
        "AIRTABLE_TABLE_NAME": os.getenv(table_name_env, default_table_name).strip(),
    }
    missing = [name for name, value in env_values.items() if not value]
    if missing:
        raise AirtableConfigError(
            "Missing Airtable environment variable(s): "
            + ", ".join(missing)
            + ". Create a local .env file from .env.example."
        )
    return {
        "api_key": env_values["AIRTABLE_API_KEY"],
        "base_id": env_values["AIRTABLE_BASE_ID"],
        "table_name": env_values["AIRTABLE_TABLE_NAME"],
    }


def airtable_formula_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def normalize_slot(value: object) -> str | None:
    raw_value = str(value or "").strip().lower()
    if not raw_value:
        return None

    raw_value = raw_value.replace("h", ":00")
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", raw_value)
    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2) or "0")
    meridiem = match.group(3)

    if minute > 59:
        return None
    if meridiem:
        if not 1 <= hour <= 12:
            return None
        if meridiem == "am" and hour == 12:
            hour = 0
        elif meridiem == "pm" and hour != 12:
            hour += 12
    elif hour > 23:
        return None

    return f"{hour:02d}:{minute:02d}"


class AirtableClient:
    def __init__(self, table_name: str | None = None, table_name_env: str = "AIRTABLE_TABLE_NAME") -> None:
        config = load_airtable_env(table_name_env=table_name_env)
        self.api_key = config["api_key"]
        self.base_id = config["base_id"]
        self.table_name = table_name or config["table_name"]
        self.base_url = f"https://api.airtable.com/v0/{quote(self.base_id)}/{quote(self.table_name, safe='')}"

    def _request(self, method: str, url: str, payload: dict | None = None) -> dict:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(url, data=data, headers=headers, method=method)

        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise AirtableRequestError(f"Airtable HTTP {exc.code}: {details}") from exc
        except URLError as exc:
            raise AirtableRequestError(f"Airtable connection failed: {exc.reason}") from exc

    def find_record_by_title(self, title: str) -> dict | None:
        formula = f"{{Titre}} = {airtable_formula_string(title)}"
        url = f"{self.base_url}?maxRecords=1&filterByFormula={quote(formula, safe='')}"
        data = self._request("GET", url)
        records = data.get("records", [])
        return records[0] if records else None

    def find_record_by_field(self, field_name: str, value: str) -> dict | None:
        formula = f"{{{field_name}}} = {airtable_formula_string(value)}"
        url = f"{self.base_url}?maxRecords=1&filterByFormula={quote(formula, safe='')}"
        data = self._request("GET", url)
        records = data.get("records", [])
        return records[0] if records else None

    def find_record_by_formula(self, formula: str, max_records: int = 1) -> list[dict]:
        url = f"{self.base_url}?maxRecords={max_records}&filterByFormula={quote(formula, safe='')}"
        data = self._request("GET", url)
        return data.get("records", [])

    def find_ready_record(self) -> dict | None:
        formula = (
            "AND("
            "{Statut} = 'A publier',"
            "{Script} != '',"
            "{Lien Image} != '',"
            "{Lien Thumbnail} != '',"
            "{Lien Video} = ''"
            ")"
        )
        query = (
            f"?maxRecords=1"
            f"&filterByFormula={quote(formula, safe='')}"
            f"&sort%5B0%5D%5Bfield%5D={quote('Date Publication', safe='')}"
            f"&sort%5B0%5D%5Bdirection%5D=asc"
        )
        data = self._request("GET", self.base_url + query)
        records = data.get("records", [])
        return records[0] if records else None

    def find_publish_candidates(self, max_records: int = 10) -> list[dict]:
        formula = (
            "AND("
            "{Statut} = 'A publier',"
            "{Script} != '',"
            "{Lien Image} != '',"
            "{Lien Thumbnail} != '',"
            "{Lien Video} = ''"
            ")"
        )
        query = (
            f"?maxRecords={max_records}"
            f"&filterByFormula={quote(formula, safe='')}"
            f"&sort%5B0%5D%5Bfield%5D={quote('Date Publication', safe='')}"
            f"&sort%5B0%5D%5Bdirection%5D=asc"
        )
        data = self._request("GET", self.base_url + query)
        return data.get("records", [])

    def create_record(self, fields: dict) -> dict:
        return self._request("POST", self.base_url, {"fields": fields})

    def update_record(self, record_id: str, fields: dict) -> dict:
        url = f"{self.base_url}/{quote(record_id, safe='')}"
        return self._request("PATCH", url, {"fields": fields})
