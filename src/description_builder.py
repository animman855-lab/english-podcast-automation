import re


def clean_script_text(script: str) -> str:
    lines = []
    for raw_line in script.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^(Host|Guest):\s*", "", line)
        lines.append(line)
    return " ".join(lines)


def useful_phrases_from_script(script: str, limit: int = 5) -> list[str]:
    quoted = re.findall(r'"([^"]{3,80})"', script)
    phrases = []
    for phrase in quoted:
        cleaned = phrase.strip()
        if cleaned and cleaned not in phrases:
            phrases.append(cleaned)
    return phrases[:limit]


def build_youtube_description(title: str, script: str) -> str:
    clean_text = clean_script_text(script)
    phrases = useful_phrases_from_script(script)

    lines = [
        f"In this English conversation podcast, we practice: {title}.",
        "",
        "This episode helps intermediate English learners understand why speaking can feel difficult even when listening feels easy.",
        "You will hear a natural Host and Guest conversation with practical phrases you can use when your mind goes blank.",
    ]

    if phrases:
        lines.extend(["", "Useful phrases from this episode:"])
        lines.extend(f"- {phrase}" for phrase in phrases)

    lines.extend(
        [
            "",
            "Practice listening, speaking, and responding naturally in real-life English conversations.",
            "",
            "Follow Saloo English for more natural English conversation practice.",
        ]
    )

    if clean_text:
        lines.extend(["", "Episode focus:", clean_text[:450].rstrip() + ("..." if len(clean_text) > 450 else "")])

    return "\n".join(lines)
