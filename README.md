# English Podcast Automation

Phase 1 of this separate project tests local Kokoro TTS for an English conversation podcast with two speakers:

- Host
- Guest

This phase only generates a short audio test. It does not connect Airtable, Upload-Post, YouTube, FFmpeg video rendering, subtitles, GitHub Actions, or any existing workflow.

## What This Test Does

The script:

1. Reads `input/sample_episode.txt`
2. Parses exact `Host:` and `Guest:` labels
3. Generates each reply with Kokoro TTS
4. Uses a different voice for Host and Guest
5. Adds natural pauses between replies
6. Assembles one final audio file
7. Exports `output/podcast_audio_test.wav`

## Install Python Dependencies

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

## Install espeak-ng

Kokoro uses `espeak-ng` for English text processing. If Kokoro fails with an `espeak-ng` or phonemizer-related error, install it first.

Windows options:

```powershell
winget install eSpeak-NG.eSpeak-NG
```

Or install it manually from:

```text
https://github.com/espeak-ng/espeak-ng/releases
```

After installation, restart the terminal so `espeak-ng` is available in `PATH`.

Ubuntu/Debian:

```bash
sudo apt-get update
sudo apt-get install -y espeak-ng
```

macOS:

```bash
brew install espeak-ng
```

## Run The Audio Test

From this project folder:

```powershell
python src/main.py
```

The final file will be written to:

```text
output/podcast_audio_test.wav
```

Temporary segment files are written to `temp/`.

## Voices

The default voices are configured in `config/voices.yaml`:

- Host: `af_heart`
- Guest: `am_echo`

Both are English voices for the Kokoro `lang_code: a` pipeline.

## Selected MVP Voices

- Host: `af_heart`
- Guest: `am_echo`

Forbidden voice:

- `am_adam` must not be used for production podcast audio.

## Voice Audition

Use this step to compare multiple Kokoro English voices before choosing the final production Host and Guest voices.

Run:

```powershell
python src/voice_audition.py
```

The audition script reads:

```text
config/voice_audition.yaml
input/voice_audition_script.txt
```

It writes individual samples and Host/Guest pair tests to:

```text
output/voice_auditions/
```

Expected files include:

```text
output/voice_auditions/voice_af_heart.wav
output/voice_auditions/voice_af_bella.wav
output/voice_auditions/pair_test_01.wav
output/voice_auditions/pair_test_02.wav
output/voice_auditions/pair_test_03.wav
```

Choose the final voices by listening for:

- clear pronunciation on phone speakers
- natural podcast rhythm
- warm but not exaggerated emotion
- strong contrast between Host and Guest
- comfortable speed for B1/B2 learners

`am_adam` is included only as a reference from Phase 1. It is temporary and should not be used as the final production voice.

## Phase 2 Video Test

This is a local technical test only. It is not the final channel rendering workflow.

Prerequisite:

```powershell
ffmpeg -version
ffprobe -version
```

If either command is missing on Windows:

```powershell
winget install Gyan.FFmpeg
```

Run:

```powershell
python src/render_video_test.py
```

The script:

- verifies `ffmpeg` and `ffprobe`
- uses `output/podcast_audio_test.wav`, or runs `python src/main.py` first if audio/metadata is missing
- creates `assets/sample_main_image.png` if no test image exists
- writes `temp/segments_metadata.json`
- writes `temp/subtitles.ass`
- renders `output/podcast_video_test.mp4`

Subtitle style:

- burn-in ASS subtitles
- English only
- phrase by phrase
- no `Host` / `Guest` labels
- large bottom-center text
- strong outline and semi-transparent box for phone readability

Waveform style:

- visible audio waveform
- placed above the subtitle area
- stable podcast-style visual layer
- does not cover the subtitles

## Cindy Long-Form Shadowing

Cindy long-form is a separate Airtable workflow from TheFluentBuild podcast.

- Airtable table: `Cindy Long Form`
- Voice: Kokoro `bf_emma`
- Format: Cindy alone, shadowing / listening / speaking practice
- Future platforms: YouTube, Facebook, TikTok
- Future video formats: `16:9` for YouTube/Facebook and `9:16` for TikTok
- Visual style: premium 2D illustration, orange/gold with dark navy accents
- The same visual is used as thumbnail and fixed video image

Create or update the first Cindy draft row:

```powershell
python src/create_first_cindy_long_form.py
```

This script writes to Airtable only if the `Cindy Long Form` table already exists.
It does not generate audio, video, images, or publish anything.

Required Airtable fields for `Cindy Long Form`:

- `Title`
- `Date Publication`
- `Slot`
- `Platforms`
- `Status`
- `Script / Transcript`
- `Prompt Image`
- `Prompt Thumbnail`
- `Single Visual Prompt`
- `Image Link`
- `Thumbnail Link`
- `Video Link`
- `Video Format`
- `Voice`
- `Duration Target`
- `Content Type`
- `Description`

Recommended `Status` values:

- `Draft`
- `Waiting for Image`
- `A publier`
- `En cours`
- `Publie`

Do not set `Status = A publier` until `Image Link` and `Thumbnail Link` are filled.

## Notes

- No API keys are required.
- The first run may download Kokoro model files.
- If generation fails in this environment, read the printed error and try the same commands locally after installing `espeak-ng`.
