DEFAULT_CHARACTER_ANCHOR = {
    "female_host": (
        "recognizable animated 3D cartoon woman host in her early 30s, warm medium skin tone, "
        "distinct oval face, expressive brown eyes, defined brows, shoulder-length wavy dark brown hair, "
        "confident supportive smile, memorable friendly presence"
    ),
    "male_guest": (
        "recognizable animated 3D cartoon man guest in his early 30s, light olive skin tone, "
        "rounded thoughtful face, expressive hazel eyes, short textured black hair, relaxed but curious smile, "
        "memorable approachable presence"
    ),
    "style": (
        "premium high-quality 3D cartoon illustration, polished cinematic rendering, warm beautiful lighting, "
        "modern YouTube English conversation podcast look, stylized animated characters, not photorealistic, "
        "not live action, no realistic human skin texture"
    ),
}

NEGATIVE_VISUAL_STYLE = (
    "No photorealistic humans, no live-action look, no real-photo style, no realistic human skin texture, "
    "no ultra-realistic portrait, no boring flat design, no cheap look, no clutter, no watermark."
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
        + " Show the two strong recognizable animated 3D cartoon characters in a cozy daily-life podcast environment "
        "with visible microphones, warm table lighting, clean background details, and a polished premium composition. "
        "Faces should be distinctive and memorable, with strong but not exaggerated expressions. "
        "The image should feel readable, attractive, and not empty, while staying clean and uncluttered. "
        f"If text is useful, add only light supporting text related to the episode: \"{hook}\". "
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
        "and overall identity. Make the facial expressions stronger and more emotional: the host looks encouraging "
        "and confident, the guest looks slightly stuck but relieved to learn useful daily English. "
        "Use high contrast, a clean background, visible microphones, premium 3D cartoon rendering, and a strong "
        "YouTube composition with bigger emotional impact. "
        f"Add large readable hook text directly connected to the episode topic: \"{hook}\". "
        "The hook text must be the main thumbnail text, short, strong, and not generic. "
        + NEGATIVE_VISUAL_STYLE
    )


def build_podcast_visual_prompts(title: str, video_type: str = "", script: str = "") -> dict:
    hook = choose_thumbnail_hook(title, video_type, script)
    return {
        "hook_text": hook,
        "prompt_image": build_podcast_prompt_image(title, video_type, script, supporting_text=hook),
        "prompt_thumbnail": build_podcast_prompt_thumbnail(title, video_type, script, hook_text=hook),
    }
