from pathlib import Path
import json
import math
import shutil
import struct
import subprocess
import zlib

import numpy as np
import soundfile as sf


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = PROJECT_ROOT / "assets"
DEFAULT_IMAGE_PATH = ASSETS_DIR / "sample_main_image.png"
DEFAULT_AUDIO_PATH = PROJECT_ROOT / "output" / "podcast_audio_test.wav"
DEFAULT_SUBTITLE_PATH = PROJECT_ROOT / "temp" / "subtitles.ass"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "output" / "podcast_video_test.mp4"
DEFAULT_WAVEFORM_DIR = PROJECT_ROOT / "temp" / "premium_waveform_frames"
DEFAULT_WAVEFORM_IMAGE = PROJECT_ROOT / "temp" / "premium_waveform.png"
WINDOWS_FONTS_DIR = Path("C:/Windows/Fonts")
DEFAULT_FONT_FILE = WINDOWS_FONTS_DIR / "arial.ttf"
VIDEO_FPS = 30
WAVEFORM_FPS = 15


def require_ffmpeg() -> None:
    missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if missing:
        raise RuntimeError(
            f"Missing required tool(s): {', '.join(missing)}. Install FFmpeg and make sure ffmpeg/ffprobe are available in PATH. "
            "Windows: winget install Gyan.FFmpeg"
        )

    for tool in ("ffmpeg", "ffprobe"):
        subprocess.run([tool, "-version"], check=True, capture_output=True, text=True)


def run_command(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            "Command failed:\n"
            + " ".join(command)
            + "\n\nSTDOUT:\n"
            + result.stdout
            + "\n\nSTDERR:\n"
            + result.stderr
        )


def ffmpeg_filter_path(path: str | Path) -> str:
    normalized = Path(path).resolve().as_posix()
    return normalized.replace(":", r"\:")


def ensure_sample_image(image_path: str | Path = DEFAULT_IMAGE_PATH) -> Path:
    output = Path(image_path)
    if output.exists():
        return output

    output.parent.mkdir(parents=True, exist_ok=True)
    font_part = ""
    if DEFAULT_FONT_FILE.exists():
        font_part = f"fontfile='{ffmpeg_filter_path(DEFAULT_FONT_FILE)}':"
    drawtext = (
        f"drawtext={font_part}text='English Conversation Podcast Test':"
        "fontcolor=white:fontsize=72:box=1:boxcolor=black@0.35:"
        "boxborderw=28:x=(w-text_w)/2:y=(h-text_h)/2"
    )
    run_command(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=#18212f:s=1920x1080:d=1",
            "-vf",
            drawtext,
            "-frames:v",
            "1",
            str(output),
        ]
    )
    return output


def probe_duration(path: str | Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def write_png_rgba(path: Path, rgba: np.ndarray) -> None:
    height, width, _ = rgba.shape
    raw_rows = [b"\x00" + rgba[row].tobytes() for row in range(height)]
    raw = b"".join(raw_rows)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, level=1))
        + chunk(b"IEND", b"")
    )


def draw_pill_bar(frame: np.ndarray, center_x: int, center_y: int, width: int, height: int, color: tuple[int, int, int], alpha: int) -> None:
    radius = width // 2
    half_height = height // 2
    top = max(0, center_y - half_height)
    bottom = min(frame.shape[0], center_y + half_height)
    left = max(0, center_x - radius)
    right = min(frame.shape[1], center_x + radius)

    for y in range(top, bottom):
        if y < top + radius:
            dy = top + radius - y
        elif y >= bottom - radius:
            dy = y - (bottom - radius - 1)
        else:
            dy = 0

        half_width = radius if dy == 0 else int(max(0, math.sqrt(max(0, radius * radius - dy * dy))))
        row_left = max(0, center_x - half_width)
        row_right = min(frame.shape[1], center_x + half_width + 1)
        if row_left >= row_right:
            continue

        existing_alpha = frame[y, row_left:row_right, 3].astype(np.float32) / 255.0
        new_alpha = alpha / 255.0
        out_alpha = new_alpha + existing_alpha * (1 - new_alpha)
        for channel, value in enumerate(color):
            existing = frame[y, row_left:row_right, channel].astype(np.float32)
            blended = (value * new_alpha + existing * existing_alpha * (1 - new_alpha)) / np.maximum(out_alpha, 0.001)
            frame[y, row_left:row_right, channel] = np.clip(blended, 0, 255).astype(np.uint8)
        frame[y, row_left:row_right, 3] = np.clip(out_alpha * 255, 0, 255).astype(np.uint8)


def pill_mask(width: int, height: int) -> np.ndarray:
    radius = width / 2
    y, x = np.ogrid[:height, :width]
    center_x = (width - 1) / 2
    top_center_y = radius
    bottom_center_y = height - radius - 1
    middle = (y >= top_center_y) & (y <= bottom_center_y)
    top = (x - center_x) ** 2 + (y - top_center_y) ** 2 <= radius**2
    bottom = (x - center_x) ** 2 + (y - bottom_center_y) ** 2 <= radius**2
    return middle | top | bottom


def draw_pill_bar_fast(
    frame: np.ndarray,
    center_x: int,
    center_y: int,
    width: int,
    height: int,
    color: tuple[int, int, int],
    alpha: int,
    masks: dict[tuple[int, int], np.ndarray],
) -> None:
    height = max(width + 2, height)
    key = (width, height)
    if key not in masks:
        masks[key] = pill_mask(width, height)
    mask = masks[key]

    top = max(0, center_y - height // 2)
    left = max(0, center_x - width // 2)
    bottom = min(frame.shape[0], top + height)
    right = min(frame.shape[1], left + width)
    cropped_mask = mask[: bottom - top, : right - left]
    area = frame[top:bottom, left:right]
    area[cropped_mask, 0] = color[0]
    area[cropped_mask, 1] = color[1]
    area[cropped_mask, 2] = color[2]
    area[cropped_mask, 3] = alpha


def audio_rms_envelope(audio_path: Path, fps: int, bars_per_frame: int, duration: float) -> np.ndarray:
    samples, sample_rate = sf.read(audio_path, always_2d=True)
    mono = samples.mean(axis=1).astype(np.float32)
    total_frames = max(1, math.ceil(duration * fps))
    envelope_count = total_frames + bars_per_frame
    step = max(1, len(mono) // envelope_count)
    envelope = np.zeros(envelope_count, dtype=np.float32)

    for index in range(envelope_count):
        start = min(len(mono), index * step)
        end = min(len(mono), start + step)
        if end > start:
            chunk = mono[start:end]
            envelope[index] = float(np.sqrt(np.mean(chunk * chunk)))

    if envelope.max() > 0:
        envelope = envelope / envelope.max()
    return np.clip(envelope, 0.08, 1.0)


def generate_premium_waveform_frames(
    audio_path: str | Path,
    frames_dir: str | Path = DEFAULT_WAVEFORM_DIR,
    width: int = 1320,
    height: int = 82,
    fps: int = WAVEFORM_FPS,
) -> Path:
    audio = Path(audio_path)
    output_dir = Path(frames_dir)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    duration = probe_duration(audio)
    frame_count = max(1, math.ceil(duration * fps))
    bar_count = 74
    bar_width = 6
    spacing = (width - (bar_count * bar_width)) / (bar_count - 1)
    center_y = height // 2
    envelope = audio_rms_envelope(audio, fps, bar_count, duration)
    masks: dict[tuple[int, int], np.ndarray] = {}

    for frame_index in range(frame_count):
        frame = np.zeros((height, width, 4), dtype=np.uint8)
        start = frame_index
        values = envelope[start : start + bar_count]
        if len(values) < bar_count:
            values = np.pad(values, (0, bar_count - len(values)), mode="edge")

        for bar_index, value in enumerate(values):
            x = int(round(bar_index * (bar_width + spacing))) + bar_width // 2
            harmony = 0.82 + 0.18 * math.sin((frame_index * 0.055) + (bar_index * 0.42))
            bar_height = int(14 + (height - 24) * min(1.0, float(value) * harmony))
            color = (196, 237, 255) if bar_index % 11 in (4, 5) else (255, 255, 255)
            alpha = 238 if color == (255, 255, 255) else 255
            draw_pill_bar_fast(frame, x, center_y, bar_width, max(10, bar_height), color, alpha, masks)

        write_png_rgba(output_dir / f"wave_{frame_index:05d}.png", frame)

    return output_dir


def generate_premium_waveform_image(
    audio_path: str | Path,
    output_path: str | Path = DEFAULT_WAVEFORM_IMAGE,
    width: int = 1500,
    height: int = 170,
) -> Path:
    audio = Path(audio_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    samples, _ = sf.read(audio, always_2d=True)
    mono = samples.mean(axis=1).astype(np.float32)
    bar_count = 116
    bar_width = 9
    spacing = (width - (bar_count * bar_width)) / (bar_count - 1)
    center_y = height // 2
    frame = np.zeros((height, width, 4), dtype=np.uint8)
    samples_per_bar = max(1, len(mono) // bar_count)

    values = []
    for bar_index in range(bar_count):
        start = bar_index * samples_per_bar
        end = min(len(mono), start + samples_per_bar)
        chunk = mono[start:end]
        rms = float(np.sqrt(np.mean(chunk * chunk))) if len(chunk) else 0.0
        values.append(rms)

    envelope = np.array(values, dtype=np.float32)
    if envelope.max() > 0:
        envelope = envelope / envelope.max()
    envelope = np.clip(envelope, 0.12, 1.0)

    for bar_index, value in enumerate(envelope):
        x = int(round(bar_index * (bar_width + spacing))) + bar_width // 2
        harmony = 0.86 + 0.14 * math.sin(bar_index * 0.55)
        bar_height = int(24 + (height - 34) * min(1.0, float(value) * harmony))
        color = (196, 237, 255) if bar_index % 13 in (5, 6) else (255, 255, 255)
        alpha = 242 if color == (255, 255, 255) else 255
        draw_pill_bar(frame, x, center_y, bar_width, max(14, bar_height), color, alpha)

    write_png_rgba(output, frame)
    return output


def render_video(
    image_path: str | Path = DEFAULT_IMAGE_PATH,
    audio_path: str | Path = DEFAULT_AUDIO_PATH,
    subtitle_path: str | Path = DEFAULT_SUBTITLE_PATH,
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    image = Path(image_path)
    audio = Path(audio_path)
    subtitles = Path(subtitle_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    if not image.exists():
        raise FileNotFoundError(f"Main image not found: {image}")
    if not audio.exists():
        raise FileNotFoundError(f"Audio not found: {audio}")
    if not subtitles.exists():
        raise FileNotFoundError(f"ASS subtitles not found: {subtitles}")

    waveform_dir = generate_premium_waveform_frames(audio)
    subtitle_filter = ffmpeg_filter_path(subtitles)
    fontsdir_filter = ffmpeg_filter_path(WINDOWS_FONTS_DIR) if WINDOWS_FONTS_DIR.exists() else ""
    subtitles_part = f"subtitles='{subtitle_filter}'"
    if fontsdir_filter:
        subtitles_part += f":fontsdir='{fontsdir_filter}'"
    filter_complex = (
        "[0:v]scale=1920:1080:force_original_aspect_ratio=increase,"
        "crop=1920:1080,setsar=1[bg];"
        "[bg]drawbox=x=276:y=604:w=1368:h=108:color=black@0.14:t=fill[band];"
        "[band][2:v]overlay=x=(W-w)/2:y=617[vw];"
        f"[vw]{subtitles_part}[vout]"
    )

    run_command(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(image),
            "-i",
            str(audio),
            "-framerate",
            str(WAVEFORM_FPS),
            "-i",
            str(waveform_dir / "wave_%05d.png"),
            "-filter_complex",
            filter_complex,
            "-map",
            "[vout]",
            "-map",
            "1:a",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            "30",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )
    return output
