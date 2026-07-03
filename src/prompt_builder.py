DEFAULT_CHARACTER_ANCHOR = {
    "female_host": (
        "recognizable friendly cartoon woman host in her early 30s, fair warm skin tone, "
        "distinct oval face, expressive green eyes, soft freckles, long wavy copper red hair, "
        "bright supportive smile, yellow sweater, memorable reassuring presence"
    ),
    "male_guest": (
        "recognizable friendly cartoon man guest in his early 30s, light skin tone, "
        "rounded thoughtful face, expressive blue eyes, short neat blond hair, relaxed curious smile, "
        "blue shirt, memorable approachable presence"
    ),
    "style": (
        "clean premium YouTube educational podcast illustration inspired by successful English learning thumbnails, "
        "warm cream background, friendly colorful cartoon look, soft shadows, crisp outlines, large readable layout, "
        "microphones visible, cozy desk or daily-life setting, polished but simple, not photorealistic, not live action"
    ),
}

NEGATIVE_VISUAL_STYLE = (
    "No photorealistic humans, no live-action look, no real-photo style, no realistic human skin texture, "
    "no ultra-realistic portrait, no dark cinematic look, no generic corporate avatars, no cheap look, "
    "no clutter, no watermark."
)


def choose_thumbnail_hook(title: str, video_type: str = "", script: str = "") -> str:
    text = f"{title} {video_type} {script}".lower()
    if any(term in text for term in ["daily", "day", "everyday", "morning", "work", "school"]):
        return "TALK ABOUT YOUR DAY"
    if any(term in text for term in ["natural", "basic"]):
        return "SOUND MORE NATURAL"
    if any(term in text for term in ["speak", "speaking", "freeze"]):
        return "STOP BASIC ENGLISH"
    return "DAILY ENGLISH"


def character_anchor_text(anchor: dict = DEFAULT_CHARACTER_ANCHOR) -> str:
    return (
        "Use the exact same two character identities in the main image and thumbnail. "
        f"Host identity: {anchor['female_host']}. "
        f"Guest identity: {anchor['male_guest']}. "
        f"Overall visual style: {anchor['style']}. "
        "Keep the same faces, skin tones, hair colors, hair styles, facial proportions, and overall character design."
    )


def build_podcast_prompt_image(
    title: str,
    video_type: str = "",
    script: str = "",
    anchor: dict = DEFAULT_CHARACTER_ANCHOR,
    supporting_text: str | None = None,
) -> str:
    hook = supporting_text or choose_thumbnail_hook(title, video_type, script)
    return (
        "Create a 16:9 main image for a YouTube English conversation podcast. "
        + character_anchor_text(anchor)
        + " Use a bright illustrated layout like a polished English learning podcast thumbnail: cream or soft pastel "
        "background, friendly classroom/podcast mood, simple desk, visible microphones, coffee or notebook details, "
        "and clear daily-life visual cues. The blond guest and red-haired host must be the visual focus. "
        "Faces should be distinctive, warm, and memorable, with strong but not exaggerated expressions. "
        "The image should feel readable, attractive, and not empty, while staying clean and uncluttered. "
        f"Add only small/light supporting text if useful, not dominant: \"{hook}\". "
        + NEGATIVE_VISUAL_STYLE
    )


def build_podcast_prompt_thumbnail(
    title: str,
    video_type: str = "",
    script: str = "",
    anchor: dict = DEFAULT_CHARACTER_ANCHOR,
    hook_text: str | None = None,
) -> str:
    hook = hook_text or choose_thumbnail_hook(title, video_type, script)
    return (
        "Create a 16:9 clickable YouTube thumbnail for an English conversation podcast. "
        + character_anchor_text(anchor)
        + " Use the same host and guest as the main image, with the same face, skin tone, hair color, hair style, "
        "and overall identity: one red-haired female host and one blond male guest, absolutely no brown-haired or "
        "black-haired avatars. Make the facial expressions stronger and more emotional: the host looks encouraging "
        "and confident, the guest looks slightly stuck but relieved to learn useful daily English. "
        "Use the reference style of successful English learning thumbnails: big clean title area, warm cream or "
        "green/blue background blocks, friendly cartoon characters, visible microphones, high contrast, simple props, "
        "and a strong readable YouTube composition with bigger emotional impact. "
        f"Add large readable hook text directly connected to the episode topic: \"{hook}\". "
        "The hook text must be the main thumbnail text, short, strong, and not generic. Use bold dark blue or white "
        "letters with clean outline/shadow so it is readable on mobile. "
        + NEGATIVE_VISUAL_STYLE
    )


def build_podcast_visual_prompts(title: str, video_type: str = "", script: str = "") -> dict:
    hook = choose_thumbnail_hook(title, video_type, script)
    return {
        "hook_text": hook,
        "prompt_image": build_podcast_prompt_image(title, video_type, script, supporting_text=hook),
        "prompt_thumbnail": build_podcast_prompt_thumbnail(title, video_type, script, hook_text=hook),
    }
