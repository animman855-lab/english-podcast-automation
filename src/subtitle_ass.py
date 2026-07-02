from pathlib import Path
import json
import re
import textwrap


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_METADATA_PATH = PROJECT_ROOT / "temp" / "segments_metadata.json"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "temp" / "subtitles.ass"


def ass_time(seconds: float) -> str:
    centiseconds = round(seconds * 100)
    hours = centiseconds // 360000
    minutes = (centiseconds % 360000) // 6000
    secs = (centiseconds % 6000) // 100
    cs = centiseconds % 100
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def escape_ass_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def split_phrases(text: str) -> list[str]:
    phrases = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    return phrases or [text.strip()]


def wrap_subtitle(text: str, width: int = 32) -> str:
    lines = textwrap.wrap(text, width=width)
    if len(lines) <= 2:
        return r"\N".join(lines)

    midpoint = max(1, len(lines) // 2)
    top = " ".join(lines[:midpoint])
    bottom = " ".join(lines[midpoint:])
    return f"{top}\\N{bottom}"


def phrase_timings(segment: dict) -> list[tuple[float, float, str]]:
    phrases = split_phrases(segment["text"])
    start = float(segment["start_time"])
    end = float(segment["end_time"])
    duration = max(0.1, end - start)
    weights = [max(1, len(phrase)) for phrase in phrases]
    total_weight = sum(weights)
    timings: list[tuple[float, float, str]] = []
    cursor = start

    for index, phrase in enumerate(phrases):
        if index == len(phrases) - 1:
            phrase_end = end
        else:
            phrase_end = cursor + duration * (weights[index] / total_weight)
        timings.append((cursor, phrase_end, phrase))
        cursor = phrase_end

    return timings


def generate_ass(
    metadata_path: str | Path = DEFAULT_METADATA_PATH,
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "[Script Info]",
        "Title: English Podcast Test Subtitles",
        "ScriptType: v4.00+",
        "PlayResX: 1920",
        "PlayResY: 1080",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: PodcastBig,Arial,78,&H00FFFFFF,&H00FFFFFF,&H00000000,&H99000000,-1,0,0,0,100,100,0,0,3,4,2,2,120,120,70,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    for segment in metadata:
        for start, end, phrase in phrase_timings(segment):
            text = wrap_subtitle(escape_ass_text(phrase))
            lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},PodcastBig,,0,0,0,,{text}")

    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    print(generate_ass())
