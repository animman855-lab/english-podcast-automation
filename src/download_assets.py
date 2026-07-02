from pathlib import Path
import re
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen


class AssetDownloadError(RuntimeError):
    pass


IMAGE_SIGNATURES = {
    b"\x89PNG\r\n\x1a\n": ".png",
    b"\xff\xd8\xff": ".jpg",
    b"RIFF": ".webp",
}


def google_drive_download_url(url: str) -> str:
    patterns = [
        r"/file/d/([^/]+)",
        r"[?&]id=([^&]+)",
        r"/open\?id=([^&]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return f"https://drive.google.com/uc?export=download&id={match.group(1)}"

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if "id" in query and query["id"]:
        return f"https://drive.google.com/uc?export=download&id={query['id'][0]}"

    return url


def detect_image_extension(content: bytes, content_type: str = "") -> str:
    for signature, extension in IMAGE_SIGNATURES.items():
        if content.startswith(signature):
            return extension
    if "png" in content_type:
        return ".png"
    if "jpeg" in content_type or "jpg" in content_type:
        return ".jpg"
    if "webp" in content_type:
        return ".webp"
    raise AssetDownloadError("Downloaded file does not look like a supported image.")


def download_image(url: str, output_path_without_suffix: str | Path) -> Path:
    if not url:
        raise AssetDownloadError("Image URL is empty.")

    download_url = google_drive_download_url(url)
    request = Request(download_url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=90) as response:
        content = response.read()
        content_type = response.headers.get("content-type", "")

    extension = detect_image_extension(content, content_type)
    output_base = Path(output_path_without_suffix)
    output = output_base.with_suffix(extension)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(content)
    return output


def download_episode_assets(image_url: str, thumbnail_url: str, output_dir: str | Path) -> dict[str, Path]:
    output = Path(output_dir)
    return {
        "image_path": download_image(image_url, output / "main_image"),
        "thumbnail_path": download_image(thumbnail_url, output / "thumbnail"),
    }
