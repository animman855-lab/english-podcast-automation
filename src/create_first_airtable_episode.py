from datetime import date, timedelta
import sys

from airtable_client import AirtableClient, AirtableConfigError, AirtableRequestError
from prompt_builder import build_podcast_visual_prompts


TITLE = "You Understand English But Can't Speak"
PUBLICATION_DATE = (date.today() + timedelta(days=1)).isoformat()


SCRIPT = """Host: Have you ever understood English perfectly, but then frozen when it was your turn to speak?
Guest: Oh yes. That feeling is so real. You know the words, you understand the question, but suddenly your brain goes blank.
Host: Exactly. And today, we are talking about that moment. Not in a complicated way, but in a real conversation way.
Guest: I like that, because many learners think the problem is their English. But sometimes the problem is pressure.
Host: Yes. When you listen, you have time. You can relax. But when someone looks at you and waits for your answer, everything feels faster.
Guest: Right. Your heart goes a little faster, and you start thinking, "What is the perfect sentence?"
Host: And that is the trap. Real conversation is not about perfect sentences. It is about responding naturally.
Guest: So what can someone say when they need more time?
Host: A very useful phrase is, "Let me think for a second." It is simple, natural, and it gives you space.
Guest: That sounds much better than staying silent. And it does not sound weak.
Host: Not at all. Native speakers say things like that all the time. Another phrase is, "That's a good question."
Guest: Ah, I use that one. It gives you one or two seconds to organize your answer.
Host: Exactly. You can say, "That's a good question. I think..." and then continue with a simple idea.
Guest: So instead of trying to build a perfect long answer, you start with a small natural phrase.
Host: Yes. Small phrases are powerful. They keep the conversation alive.
Guest: What about when you do not understand the question?
Host: Great point. You can say, "Sorry, can you say that again?" or "Do you mean...?" and then repeat what you understood.
Guest: That feels more confident than pretending to understand.
Host: Definitely. Conversation is a team activity. You are allowed to ask for help.
Guest: I think many learners forget that. They feel they must answer immediately.
Host: Yes, but even confident speakers pause. They say, "Hmm, let me see," or "I guess..." or "For me, it depends."
Guest: Those little phrases make the answer feel natural.
Host: Exactly. Let's practice a simple example. If someone asks, "Why are you learning English?" you can start with, "That's a good question. I think English helps me connect with more people."
Guest: Nice. Simple and clear.
Host: Or you can say, "Let me think for a second. I use English for work, but I also enjoy learning it."
Guest: That sounds natural. Not like a textbook.
Host: That is the goal. You do not need perfect English to speak. You need useful phrases, calm breathing, and practice with real situations.
Guest: And maybe a little patience with yourself. Because freezing does not mean you failed.
Host: Exactly. It means your brain needs more speaking practice, not more pressure.
Guest: So the recap is: use short starter phrases, ask for repetition when needed, and do not chase perfect grammar in every sentence.
Host: Beautiful recap. Start small, stay calm, and keep the conversation moving.
Guest: I like that. Keep it moving.
Host: If you want more natural English conversations like this, follow Saloo English. We will help you practice real phrases for real life.
Guest: See you in the next conversation."""


VISUAL_PROMPTS = build_podcast_visual_prompts(TITLE, "Speaking Problem", SCRIPT)
PROMPT_IMAGE = VISUAL_PROMPTS["prompt_image"]
PROMPT_THUMBNAIL = VISUAL_PROMPTS["prompt_thumbnail"]


def build_first_episode_fields() -> dict:
    return {
        "Titre": TITLE,
        "Date Publication": PUBLICATION_DATE,
        "Slot": "00:00",
        "Video Type": "Speaking Problem",
        "Statut": "En cours",
        "Script": SCRIPT,
        "Prompt Image": PROMPT_IMAGE,
        "Lien Image": "",
        "Prompt Thumbnail": PROMPT_THUMBNAIL,
        "Lien Thumbnail": "",
        "Lien Video": "",
    }


def print_report(record: dict, created: bool, fields: dict) -> None:
    status = "created" if created else "already existed"
    print(f"Airtable record {status}.")
    print(f"Record ID: {record.get('id')}")
    print(f"Titre: {fields['Titre']}")
    print(f"Date Publication: {fields['Date Publication']}")
    print(f"Slot: {fields['Slot']}")
    print(f"Video Type: {fields['Video Type']}")
    print(f"Statut: {fields['Statut']}")
    print(f"Lien Image empty: {fields['Lien Image'] == ''}")
    print(f"Lien Thumbnail empty: {fields['Lien Thumbnail'] == ''}")
    print(f"Lien Video empty: {fields['Lien Video'] == ''}")


def main() -> int:
    fields = build_first_episode_fields()

    try:
        client = AirtableClient()
        existing = client.find_record_by_title(fields["Titre"])
        if existing:
            print("Duplicate protection: a record with this Titre already exists. No new record was created.")
            print_report(existing, created=False, fields=fields)
            return 0

        created = client.create_record(fields)
        print_report(created, created=True, fields=fields)
        return 0

    except AirtableConfigError as exc:
        print("Airtable setup incomplete. No Airtable request was made.")
        print(f"Error: {exc}")
        print("Create .env from .env.example, then run: python src/create_first_airtable_episode.py")
        return 1
    except AirtableRequestError as exc:
        print("Airtable request failed. No fallback action was taken.")
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
