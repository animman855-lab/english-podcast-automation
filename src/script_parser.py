from dataclasses import dataclass
from pathlib import Path
import re


TARGET_MAX_CHARS = 500
HARD_MAX_CHARS = 850


@dataclass(frozen=True)
class ScriptSegment:
    speaker: str
    text: str


def split_long_text(text: str, target_max_chars: int = TARGET_MAX_CHARS) -> list[str]:
    if len(text) <= target_max_chars:
        return [text]

    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > target_max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = candidate

        while len(current) > HARD_MAX_CHARS:
            split_at = current.rfind(" ", 0, target_max_chars)
            if split_at == -1:
                split_at = target_max_chars
            chunks.append(current[:split_at].strip())
            current = current[split_at:].strip()

    if current:
        chunks.append(current)

    return chunks


def parse_script(path: str | Path) -> list[ScriptSegment]:
    script_path = Path(path)
    segments: list[ScriptSegment] = []

    for line_number, raw_line in enumerate(script_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("Host:"):
            speaker = "Host"
            text = line.removeprefix("Host:").strip()
        elif line.startswith("Guest:"):
            speaker = "Guest"
            text = line.removeprefix("Guest:").strip()
        else:
            raise ValueError(
                f"Invalid script line {line_number}. Expected exact label 'Host:' or 'Guest:'."
            )

        if not text:
            raise ValueError(f"Invalid script line {line_number}. Speaker line has no text.")

        for chunk in split_long_text(text):
            segments.append(ScriptSegment(speaker=speaker, text=chunk))

    if not segments:
        raise ValueError(f"No Host/Guest segments found in {script_path}.")

    return segments
