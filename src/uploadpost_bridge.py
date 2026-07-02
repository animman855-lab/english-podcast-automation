from pathlib import Path
import json
import os
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class UploadPostBridgeError(RuntimeError):
    pass


def env_bool(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def build_uploadpost_package(
    video_path: str | Path,
    thumbnail_path: str | Path,
    title: str,
    description: str,
    publish_datetime: str | None,
    output_path: str | Path,
) -> dict:
    package = {
        "platform": "YouTube",
        "video_path": str(Path(video_path).resolve()),
        "thumbnail_path": str(Path(thumbnail_path).resolve()),
        "title": title,
        "description": description,
        "publish_datetime": publish_datetime,
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(package, indent=2), encoding="utf-8")
    package["package_path"] = str(output.resolve())
    return package


def submit_or_dry_run(package: dict, dry_run: bool) -> dict:
    if dry_run:
        print("DRY_RUN=true. Nothing will be sent to Upload-Post.")
        print("Upload-Post package that would be sent:")
        print(json.dumps(package, indent=2))
        return {"published": False, "youtube_url": "", "dry_run": True}

    repo_path = os.getenv("UPLOADPOST_REPO_PATH", "").strip()
    command = os.getenv("UPLOADPOST_COMMAND", "").strip()
    if not repo_path or not command:
        raise UploadPostBridgeError(
            "DRY_RUN=false but UPLOADPOST_REPO_PATH or UPLOADPOST_COMMAND is missing. "
            "Upload-Post real interface must be confirmed before publishing."
        )

    package_path = package["package_path"]
    completed = subprocess.run(
        command + f' "{package_path}"',
        cwd=repo_path,
        shell=True,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if completed.returncode != 0:
        raise UploadPostBridgeError(
            "Upload-Post command failed.\n"
            f"STDOUT:\n{completed.stdout}\n\nSTDERR:\n{completed.stderr}"
        )

    try:
        response = json.loads(completed.stdout)
    except json.JSONDecodeError:
        response = {"raw_stdout": completed.stdout}

    youtube_url = response.get("youtube_url") or response.get("url") or response.get("link") or ""
    return {"published": True, "youtube_url": youtube_url, "dry_run": False, "response": response}
