from pathlib import Path
from contextlib import ExitStack
import json
import os
import time
from urllib.parse import urlparse

from PIL import Image
import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class UploadPostBridgeError(RuntimeError):
    pass


THUMBNAIL_MAX_BYTES = 1_800_000
UPLOAD_STATUS_POLL_INTERVAL_SECONDS = 30
UPLOAD_STATUS_TIMEOUT_SECONDS = 600
DEFAULT_UPLOADPOST_PLATFORMS = ["youtube", "facebook", "tiktok"]


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
    user: str = "thefluentbuild",
    platforms: list[str] | None = None,
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
        "platforms": platforms or DEFAULT_UPLOADPOST_PLATFORMS,
        "user": user,
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
    for platform in package.get("platforms", DEFAULT_UPLOADPOST_PLATFORMS):
        data.append(("platform[]", platform))
        if platform == "tiktok":
            data.append(("tiktok_title", package["title"][:100]))
            data.append(("tiktok_description", package["description"]))
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
    for platform_result in platform_results(response):
        if platform_result.get("thumbnail_set") is False:
            platform = platform_result.get("platform", "unknown")
            error = platform_result.get("thumbnail_error") or "Upload-Post did not apply the thumbnail."
            print(f"WARNING: Upload-Post {platform} thumbnail was not applied: {error}")


def response_payload(response: dict) -> dict:
    payload = response.get("result")
    return payload if isinstance(payload, dict) else response


def platform_results(response: dict) -> list[dict]:
    payload = response_payload(response)
    results = payload.get("results", {})
    if isinstance(results, dict):
        return [dict(value, platform=platform) for platform, value in results.items() if isinstance(value, dict)]
    if isinstance(results, list):
        return [result for result in results if isinstance(result, dict)]
    return []


def platform_result_for(response: dict, platform: str) -> dict | None:
    for result in platform_results(response):
        if result.get("platform") == platform:
            return result
    return None


def is_background_accepted(response: dict) -> bool:
    payload = response_payload(response)
    message = str(payload.get("message", "")).lower()
    return bool(payload.get("background_accepted")) or (
        bool(payload.get("request_id"))
        and (
            "background" in message
            or "upload initiated" in message
            or "handed off" in message
        )
    )


def is_final_status(response: dict) -> bool:
    payload = response_payload(response)
    status = str(payload.get("status", "")).lower()
    if status in {"completed", "success", "failed"}:
        return True
    total = payload.get("total")
    completed = payload.get("completed")
    if isinstance(total, int) and isinstance(completed, int) and total > 0 and completed >= total:
        return True
    return bool(platform_results(response)) and status not in {"queued", "processing", "pending", "running"}


def get_upload_status(request_id: str, api_key: str) -> dict:
    response = requests.get(
        "https://api.upload-post.com/api/uploadposts/status",
        headers={"Authorization": f"Apikey {api_key}"},
        params={"request_id": request_id},
        timeout=60,
    )
    print(f"Upload-Post status check HTTP status: {response.status_code}")
    print(f"Upload-Post status response preview: {response.text[:500]}")
    if response.status_code >= 400:
        raise UploadPostBridgeError(f"Upload-Post status HTTP {response.status_code}: {response.text[:1000]}")
    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise UploadPostBridgeError("Upload-Post status returned invalid JSON.") from exc


def poll_upload_status(
    request_id: str,
    api_key: str,
    interval_seconds: int = UPLOAD_STATUS_POLL_INTERVAL_SECONDS,
    timeout_seconds: int = UPLOAD_STATUS_TIMEOUT_SECONDS,
    sleep_fn=time.sleep,
) -> dict | None:
    deadline = time.monotonic() + timeout_seconds
    while True:
        status_response = get_upload_status(request_id, api_key)
        if is_final_status(status_response):
            print(f"Upload-Post final status received for request_id={request_id}")
            return status_response
        if time.monotonic() >= deadline:
            print(f"WARNING: Upload-Post still processing after {timeout_seconds}s. request_id={request_id}")
            return None
        print(f"Upload-Post still processing. Waiting {interval_seconds}s before next status check.")
        sleep_fn(interval_seconds)


def upload_response_summary(response: dict, expected_platforms: list[str]) -> dict:
    payload = response_payload(response)
    results = platform_results(response)
    failures = []
    successes = []
    thumbnail_errors = []
    thumbnail_confirmed = False

    for result in results:
        platform = result.get("platform", "unknown")
        if result.get("success") is False:
            failures.append(f"{platform}: {result.get('error') or result.get('error_message') or result}")
        else:
            successes.append(platform)

        if result.get("thumbnail_set") is True:
            thumbnail_confirmed = True
        if result.get("thumbnail_set") is False or result.get("thumbnail_error"):
            thumbnail_errors.append(f"{platform}: {result.get('thumbnail_error') or 'thumbnail_set=false'}")

    status = str(payload.get("status", "")).lower()
    if status in {"failed", "error"} and not failures:
        failures.append(payload.get("error") or payload.get("message") or f"Upload-Post status={status}")

    failed_platforms = [failure.split(":", 1)[0] for failure in failures]
    missing_platforms = [
        platform for platform in expected_platforms if platform not in successes and platform not in failed_platforms
    ]
    if results and missing_platforms:
        print(f"WARNING: Upload-Post returned no final result for platform(s): {', '.join(missing_platforms)}")
    return {
        "platform_successes": successes,
        "platform_failures": failures,
        "missing_platforms": missing_platforms,
        "thumbnail_confirmed": thumbnail_confirmed,
        "thumbnail_failed": bool(thumbnail_errors),
        "thumbnail_errors": thumbnail_errors,
    }


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
    print(f"Upload-Post multipart file fields: {', '.join(file_specs.keys())}")

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

    if (result.get("success") is False or result.get("status") == "failed") and not platform_results(result):
        raise UploadPostBridgeError(f"Upload-Post reported failure: {result}")

    if is_background_accepted(result):
        request_id = response_payload(result).get("request_id", "")
        print(f"Upload-Post accepted publication in background. request_id={request_id}")
        print("Upload-Post final platform URLs are not available in the immediate response.")
        print("Thumbnail final status is not available yet because the upload is still processing in background.")
        final_status = poll_upload_status(request_id=request_id, api_key=api_key)
        if final_status:
            final_payload = response_payload(final_status)
            final_payload.setdefault("request_id", request_id)
            final_payload["background_accepted"] = True
            return final_status
        result["background_timeout"] = True
        return result

    for platform in package.get("platforms", []):
        platform_result = platform_result_for(result, platform)
        if isinstance(platform_result, dict) and platform_result.get("success") is False:
            print(f"WARNING: Upload-Post {platform} failed: {platform_result}")

    warn_thumbnail_result(result)
    return result


def extract_youtube_url(response: dict) -> str:
    payload = response_payload(response)
    direct = payload.get("youtube_url") or payload.get("url") or payload.get("link")
    if direct:
        return direct

    results = payload.get("results", {})
    if isinstance(results, dict):
        youtube_result = results.get("youtube")
        if isinstance(youtube_result, dict):
            return youtube_result.get("url") or youtube_result.get("link") or youtube_result.get("post_url") or ""
    for result in platform_results(response):
        if result.get("platform") == "youtube":
            return result.get("url") or result.get("link") or result.get("post_url") or ""
    return ""


def extract_platform_urls(response: dict) -> dict[str, str]:
    urls = {}
    for result in platform_results(response):
        platform = result.get("platform", "")
        url = result.get("url") or result.get("link") or result.get("post_url") or ""
        if platform and url:
            urls[platform] = url
    return urls


def best_platform_url(platform_urls: dict[str, str], youtube_url: str = "") -> str:
    if youtube_url:
        return youtube_url
    for platform in ("youtube", "facebook", "tiktok"):
        if platform_urls.get(platform):
            return platform_urls[platform]
    return next(iter(platform_urls.values()), "")


def submit_or_dry_run(package: dict, dry_run: bool) -> dict:
    if dry_run:
        print("DRY_RUN=true. Nothing will be sent to Upload-Post.")
        print("Upload-Post package that would be sent:")
        print(json.dumps(package, indent=2))
        print("Upload-Post form fields that would be sent:")
        print(json.dumps(build_uploadpost_data(package), indent=2))
        print("Upload-Post multipart files that would be sent:")
        print(json.dumps({name: [spec[0], str(spec[1]), spec[2]] for name, spec in build_uploadpost_file_specs(package).items()}, indent=2))
        return {
            "published": False,
            "upload_accepted": False,
            "youtube_url": "",
            "platform_urls": {},
            "platform_successes": [],
            "platform_failures": [],
            "dry_run": True,
        }

    response = upload_to_upload_post(package)
    youtube_url = extract_youtube_url(response)
    payload = response_payload(response)
    background_accepted = is_background_accepted(response)
    still_processing = bool(payload.get("background_timeout"))
    summary = upload_response_summary(response, package.get("platforms", []))

    for failure in summary["platform_failures"]:
        print(f"WARNING: Upload-Post platform failure: {failure}")

    accepted = bool(summary["platform_successes"]) or background_accepted or still_processing
    if not accepted:
        raise UploadPostBridgeError(f"Upload-Post platform failure(s): {summary['platform_failures'] or ['No platform accepted publication.']}")

    return {
        "published": bool(summary["platform_successes"]) and not still_processing,
        "upload_accepted": True,
        "youtube_url": youtube_url,
        "platform_urls": extract_platform_urls(response),
        "dry_run": False,
        "background_accepted": background_accepted,
        "still_processing": still_processing,
        "request_id": payload.get("request_id", ""),
        "thumbnail_confirmed": summary["thumbnail_confirmed"],
        "thumbnail_failed": summary["thumbnail_failed"],
        "thumbnail_errors": summary["thumbnail_errors"],
        "platform_successes": summary["platform_successes"],
        "platform_failures": summary["platform_failures"],
        "response": response,
    }
