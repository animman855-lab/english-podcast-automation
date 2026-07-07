SALOO_APP_LINK = "https://apps.apple.com/app/saloo-english/id6770722987"


def build_cindy_description(title: str) -> str:
    lines = [
        "Practice real English conversations with Saloo English:",
        SALOO_APP_LINK,
        "",
        f"In this Cindy shadowing practice, you will train your speaking confidence with: {title}.",
        "",
        "Listen first, repeat out loud, and copy the rhythm of clear natural English.",
        "This practice is made for learners who understand English but freeze when it is time to speak.",
        "",
        "Use this session to build confidence, speak more naturally, and stop translating every sentence in your head.",
        "",
        "For more real conversation practice, use Saloo English and keep training your speaking every day.",
        "",
        "#EnglishShadowing #SpeakEnglish #EnglishListening #EnglishPractice #LearnEnglish #SpokenEnglish #EnglishSpeaking #SalooEnglish",
    ]
    return "\n".join(lines)
