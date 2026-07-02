from pathlib import Path
from contextlib import ExitStack
import json
import os
from urllib.parse import urlparse

from PIL import Image
import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class UploadPostBridgeError(RuntimeError):
    pass


THUMBNAIL_MAX_BYTES = 1_800_000


def env_bool(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def optimize_thumbnail_for_uploadpost(
    input_path: str | Path,
    output_path: str | Path,
    max_bytes: int = THUMBNAIL_MAX_BYTES,
) -> dict:
    source = Path(input_path)
    output = Path(output_path)
    if not source.exists():
        raise UploadPostBridgeError(f"Thumbnail file does not exist: {source}")

    output.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        rgb_image = image.convert("RGB")
        width, height = rgb_image.size

        for scale_percent in range(100, 39, -10):
            resized = rgb_image
            if scale_percent < 100:
                new_size = (
                    max(1, int(width * scale_percent / 100)),
                    max(1, int(height * scale_percent / 100)),
                )
                resized = rgb_image.resize(new_size, Image.Resampling.LANCZOS)

            for quality in range(92, 49, -6):
                resized.save(output, format="JPEG", quality=quality, optimize=True, progressive=True)
                size_bytes = output.stat().st_size
                if size_bytes <= max_bytes:
                    return {
                        "original_path": str(source.resolve()),
                        "optimized_path": str(output.resolve()),
                        "original_size_bytes": source.stat().st_size,
                        "optimized_size_bytes": size_bytes,
                        "quality": quality,
                        "dimensions": list(resized.size),
                    }

    final_size = output.stat().st_size if output.exists() else 0
    raise UploadPostBridgeError(
        f"Thumbnail could not be optimized below {max_bytes} bytes. Final size: {final_size} bytes."
    )


def build_uploadpost_package(
    video_path: str | Path,
    thumbnail_path: str | Path,
    thumbnail_optimized_path: str | Path | None,
    thumbnail_url: str,
    title: str,
    description: str,
    publish_datetime: str | None,
    output_path: str | Path,
) -> dict:
    validate_thumbnail_url(thumbnail_url)
    original_thumbnail = Path(thumbnail_path).resolve()
    optimized_thumbnail = Path(thumbnail_optimized_path).resolve() if thumbnail_optimized_path else None
    thumbnail_upload_mode = "url"
    optimized_size = 0
    if optimized_thumbnail and optimized_thumbnail.exists():
        optimized_size = optimized_thumbnail.stat().st_size
        if optimized_size <= THUMBNAIL_MAX_BYTES:
            thumbnail_upload_mode = "file"

    package = {
        "platforms": ["youtube", "facebook"],
        "user": "thefluentbuild",
        "video_path": str(Path(video_path).resolve()),
        "thumbnail_path": str(optimized_thumbnail or original_thumbnail),
        "thumbnail_original_path": str(original_thumbnail),
        "thumbnail_optimized_path": str(optimized_thumbnail) if optimized_thumbnail else "",
        "thumbnail_optimized_size_bytes": optimized_size,
        "thumbnail_upload_mode": thumbnail_upload_mode,
        "thumbnail_url": thumbnail_url,
        "thumbnail_sent_to_uploadpost": True,
        "title": title,
        "description": description,
        "publish_datetime": publish_datetime,
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(package, indent=2), encoding="utf-8")
    package["package_path"] = str(output.resolve())
    return package


def validate_thumbnail_url(thumbnail_url: str) -> None:
    parsed = urlparse((thumbnail_url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise UploadPostBridgeError("Lien Thumbnail is missing or invalid. Expected a public http:// or https:// URL.")


def build_uploadpost_data(package: dict) -> list[tuple[str, str]]:
    thumbnail_url = package.get("thumbnail_url", "")
    validate_thumbnail_url(thumbnail_url)
    data = [
        ("user", package.get("user", "thefluentbuild")),
        ("title", package["title"]),
        ("description", package["description"]),
        ("thumbnail_url", thumbnail_url),
        ("facebook_media_type", "VIDEO"),
    ]
    for platform in package.get("platforms", ["youtube", "facebook"]):
        data.append(("platform[]", platform))
    return data


def build_uploadpost_file_specs(package: dict) -> dict[str, tuple[str, Path, str]]:
    specs = {
        "video": ("video.mp4", Path(package["video_path"]), "video/mp4"),
    }
    thumbnail_path = Path(package.get("thumbnail_optimized_path") or "")
    if package.get("thumbnail_upload_mode") == "file" and thumbnail_path.exists():
        size_bytes = thumbnail_path.stat().st_size
        if size_bytes <= THUMBNAIL_MAX_BYTES:
            specs["thumbnail"] = ("thumbnail.jpg", thumbnail_path, "image/jpeg")
    return specs


def warn_thumbnail_result(response: dict) -> None:
    for platform, platform_result in response.get("results", {}).items():
        if not isinstance(platform_result, dict):
            continue
        if platform_result.get("thumbnail_set") is False:
            error = platform_result.get("thumbnail_error") or "Upload-Post did not apply the thumbnail."
            print(f"WARNING: Upload-Post {platform} thumbnail was not applied: {error}")


def upload_to_upload_post(package: dict) -> dict:
    api_key = os.getenv("UPLOAD_POST_API_KEY", "").strip()
    if not api_key:
        raise UploadPostBridgeError("Missing UPLOAD_POST_API_KEY.")

    video_path = Path(package["video_path"])
    if not video_path.exists():
        raise UploadPostBridgeError(f"Video file does not exist: {video_path}")

    data = build_uploadpost_data(package)
    file_specs = build_uploadpost_file_specs(package)
    thumbnail_mode = "file" if "thumbnail" in file_specs else "url"

    if thumbnail_mode == "file":
        print(f"Using optimized thumbnail file: {file_specs['thumbnail'][1]}")
    else:
        print(f"WARNING: Falling back to thumbnail_url: {package['thumbnail_url']}")
    print(f"thumbnail upload mode: {thumbnail_mode}")

    with ExitStack() as stack:
        files = {}
        for field_name, (filename, file_path, content_type) in file_specs.items():
            files[field_name] = (filename, stack.enter_context(file_path.open("rb")), content_type)
        response = requests.post(
            "https://api.upload-post.com/api/upload",
            headers={"Authorization": f"Apikey {api_key}"},
            data=data,
            files=files,
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

    warn_thumbnail_result(result)
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
        print("Upload-Post form fields that would be sent:")
        print(json.dumps(build_uploadpost_data(package), indent=2))
        print("Upload-Post multipart files that would be sent:")
        print(json.dumps({name: [spec[0], str(spec[1]), spec[2]] for name, spec in build_uploadpost_file_specs(package).items()}, indent=2))
        return {"published": False, "youtube_url": "", "dry_run": True}

    response = upload_to_upload_post(package)
    youtube_url = extract_youtube_url(response)
    return {"published": True, "youtube_url": youtube_url, "dry_run": False, "response": response}
