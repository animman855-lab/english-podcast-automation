from pathlib import Path
import json
import os

import requests


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
        "platforms": ["youtube", "facebook"],
        "user": "thefluentbuild",
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


def upload_to_upload_post(package: dict) -> dict:
    api_key = os.getenv("UPLOAD_POST_API_KEY", "").strip()
    if not api_key:
        raise UploadPostBridgeError("Missing UPLOAD_POST_API_KEY.")

    video_path = Path(package["video_path"])
    if not video_path.exists():
        raise UploadPostBridgeError(f"Video file does not exist: {video_path}")

    data = [
        ("user", package.get("user", "thefluentbuild")),
        ("title", package["title"]),
        ("description", package["description"]),
    ]
    for platform in package.get("platforms", ["youtube", "facebook"]):
        data.append(("platform[]", platform))

    print("Custom thumbnail is downloaded and kept in the package, but no reliable Upload-Post video thumbnail field was confirmed. It will not be sent.")
    with video_path.open("rb") as video_file:
        response = requests.post(
            "https://api.upload-post.com/api/upload",
            headers={"Authorization": f"Apikey {api_key}"},
            data=data,
            files={"video": ("video.mp4", video_file, "video/mp4")},
            timeout=900,
        )

    print(f"Upload-Post status: {response.status_code}")
    print(f"Upload-Post response preview: {response.text[:500]}")
    if response.status_code >= 400:
        raise UploadPostBridgeError(f"Upload-Post HTTP {response.status_code}: {response.text[:1000]}")

    try:
        result = response.json()
    except json.JSONDecodeError as exc:
        raise UploadPostBridgeError("Upload-Post returned invalid JSON.") from exc

    if result.get("success") is False or result.get("status") == "failed":
        raise UploadPostBridgeError(f"Upload-Post reported failure: {result}")

    for platform in package.get("platforms", []):
        platform_result = result.get("results", {}).get(platform)
        if isinstance(platform_result, dict) and platform_result.get("success") is False:
            raise UploadPostBridgeError(f"Upload-Post {platform} failed: {platform_result}")

    return result


def extract_youtube_url(response: dict) -> str:
    direct = response.get("youtube_url") or response.get("url") or response.get("link")
    if direct:
        return direct

    youtube_result = response.get("results", {}).get("youtube")
    if isinstance(youtube_result, dict):
        return youtube_result.get("url") or youtube_result.get("link") or youtube_result.get("post_url") or ""
    return ""


def submit_or_dry_run(package: dict, dry_run: bool) -> dict:
    if dry_run:
        print("DRY_RUN=true. Nothing will be sent to Upload-Post.")
        print("Upload-Post package that would be sent:")
        print(json.dumps(package, indent=2))
        return {"published": False, "youtube_url": "", "dry_run": True}

    response = upload_to_upload_post(package)
    youtube_url = extract_youtube_url(response)
    return {"published": True, "youtube_url": youtube_url, "dry_run": False, "response": response}
