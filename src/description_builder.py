import re

BASE_HASHTAGS = [
    "#LearnEnglish",
    "#EnglishPodcast",
    "#EnglishConversation",
    "#SpeakEnglish",
    "#EnglishPractice",
    "#DailyEnglish",
    "#RealEnglish",
    "#ImproveYourEnglish",
    "#EnglishListening",
    "#EnglishVocabulary",
]

TOPIC_HASHTAG_RULES = [
    (("#daily", "daily", "day", "everyday", "morning", "work", "school", "routine"), ["#NaturalEnglish", "#EverydayEnglish", "#EnglishSpeaking", "#EnglishLesson"]),
    (("speak", "speaking", "freeze", "conversation", "respond"), ["#EnglishSpeaking", "#SpeakEnglishFluently", "#ConversationPractice", "#SpokenEnglish"]),
    (("vocabulary", "phrases", "words"), ["#EnglishPhrases", "#EnglishVocabulary", "#UsefulEnglish", "#EnglishWords"]),
    (("listening", "podcast", "understand"), ["#EnglishListening", "#ListeningPractice", "#EnglishPodcast", "#LearnEnglishOnline"]),
]


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


def dedupe_hashtags(hashtags: list[str]) -> list[str]:
    seen = set()
    cleaned = []
    for hashtag in hashtags:
        normalized = hashtag.strip()
        if not normalized:
            continue
        if not normalized.startswith("#"):
            normalized = "#" + normalized
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(normalized)
    return cleaned


def topic_hashtags(title: str, script: str, limit: int = 5) -> list[str]:
    text = f"{title} {script}".lower()
    selected = []
    for keywords, hashtags in TOPIC_HASHTAG_RULES:
        if any(keyword in text for keyword in keywords):
            selected.extend(hashtags)
    return dedupe_hashtags(selected)[:limit]


def build_hashtag_blocks(title: str, script: str) -> tuple[list[str], list[str]]:
    specific = topic_hashtags(title, script)
    main = dedupe_hashtags(BASE_HASHTAGS + specific)
    middle = dedupe_hashtags(["#EnglishConversation", "#SpeakEnglish"] + specific[:3])[:5]
    return middle, main


def build_youtube_description(title: str, script: str) -> str:
    clean_text = clean_script_text(script)
    phrases = useful_phrases_from_script(script)
    middle_hashtags, final_hashtags = build_hashtag_blocks(title, script)

    lines = [
        f"In this English conversation podcast, we practice: {title}.",
        "",
        "This episode helps intermediate English learners understand why speaking can feel difficult even when listening feels easy.",
        "You will hear a natural Host and Guest conversation with practical phrases you can use when your mind goes blank.",
    ]

    if middle_hashtags:
        lines.extend(["", " ".join(middle_hashtags)])

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

    if final_hashtags:
        lines.extend(["", " ".join(final_hashtags)])

    return "\n".join(lines)
