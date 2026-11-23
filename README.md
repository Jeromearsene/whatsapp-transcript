# WhatsApp Transcript

*[Lire en français](README.fr.md)*

[![CI](https://github.com/jeromearsene/whatsapp-transcript/actions/workflows/ci.yml/badge.svg)](https://github.com/jeromearsene/whatsapp-transcript/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10–3.15](https://img.shields.io/badge/python-3.10%E2%80%933.15-blue.svg)](pyproject.toml)
[![Lint: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

Three scripts that turn a WhatsApp conversation (text, voice notes, photos,
videos, links) into a Markdown book. Everything runs locally on your Mac,
nothing leaves your machine (except for the very first download of the
transcription model, which only happens once).

**Python:** tested with version **3.12** (pinned in `.python-version`). Any
version from **3.10 to 3.15** works (`mlx`, the library underlying
`mlx-whisper`, supports this range on Apple Silicon — see the constraint in
`pyproject.toml`).

**License:** [MIT](LICENSE).

> ⚠️ **Before your first public commit:** the `data/` folder and `book.md`
> contain the real content of your conversation. They're excluded by
> `.gitignore` — just double-check with `git status` that neither one sneaks
> in.

```
extract.py     step 1: turns the WhatsApp export into structured messages.json
transcribe.py  step 2: transcribes voice notes (.opus) with mlx-whisper
compile.py     step 3: assembles everything into a book, grouped by day
               (Markdown, JSON or plain text — your choice)
run.py         optional: interactive wizard that walks you through all 3
               steps above, so you don't have to remember any flag
```

## Installation (one-time)

```bash
# ffmpeg is needed to decode .opus audio files
brew install ffmpeg

# Poetry, if you don't already have it
brew install poetry

# Python dependencies (mlx-whisper, optimized for Apple Silicon), in a
# virtual environment managed by Poetry
poetry install
```

The commands in the following steps should be run with `poetry run` in
front (it runs the command inside the project's virtual environment), e.g.
`poetry run python3 extract.py ...`. You can also run `poetry shell` once to
activate the environment, then run `python3 ...` commands as-is for the rest
of the terminal session.

## Quick start: the interactive wizard

If you'd rather be asked a few questions than remember command-line flags,
run:

```bash
poetry run python3 run.py
```

It asks for the export path (suggesting the most recent `WhatsApp Chat*.zip`
found in `~/Downloads`), whether to filter by date, which transcription
model to use, and which output format you want — then runs `extract.py`,
`transcribe.py` and `compile.py` for you with the matching flags. Pass
`--yes` to accept every suggested default without being asked (handy once
you've settled on your usual choices, for a quick repeat import).

The sections below describe the same 3 steps run individually, which is
still the way to go if you want finer control (date filtering details,
skipping a step, scripting it, etc.).

## Step 0 — get the WhatsApp export

On the Mac, in the WhatsApp Desktop app (no need for the iPhone):

1. Open the conversation.
2. Click the contact's name at the top (or the "…" menu), then **Export
   Chat**.
3. Choose **Attach Media** (otherwise voice notes, photos and videos won't
   be included).
4. The `.zip` file lands in your **Downloads** folder.

## Step 1 — extraction

```bash
poetry run python3 extract.py --export "~/Downloads/WhatsApp Chat with XXX.zip" --out ./data
```

To restrict to a specific period:

```bash
poetry run python3 extract.py --export "~/Downloads/WhatsApp Chat with XXX.zip" --out ./data \
    --since 01/10/2026 --until 31/10/2026
```

The script prints a count by message type and the date range covered.
**Check that the earliest date shown really matches the actual start of
your conversation** — if WhatsApp had truncated the export (this happens on
very long conversations), it would show up here.

## Step 2 — transcribing voice notes

```bash
poetry run python3 transcribe.py --data ./data
```

Uses the `large-v3` model by default (the most accurate, recommended since
some voice notes are of middling audio quality) and French as the spoken
language. This can take a while for ~500 voice notes of 5 minutes each —
that's expected, and the script saves its progress as it goes (you can
interrupt with Ctrl+C and rerun the same command; it will resume where it
left off without retranscribing what's already done).

Before transcription, each file goes through `ffmpeg` preprocessing (volume
normalization + light noise reduction), to help with the medium-quality
voice notes. If `ffmpeg` fails on a specific file, the script automatically
falls back to the raw file instead of giving up. To disable this
preprocessing: `--skip-preprocess`.

Rather than flagging an entire 5-minute voice note as soon as one passage is
uncertain, only the low-confidence **segments** are listed — with their
precise timestamp in the audio file — in `data/to_review.md`. You only need
to listen to the few seconds concerned, not the whole note.

Files that fail completely (corrupted audio, etc.) are logged in
`data/errors.json` instead of just printed to the terminal, and are
automatically retried on the next run of the script.

Useful options: `--threshold` (sensitivity for detecting uncertain passages,
default `-0.8`), `--no-speech-threshold` (detects likely silent/noisy
segments, default `0.6`), `--skip-preprocess`.

## Step 3 — compiling the book

```bash
poetry run python3 compile.py --data ./data                    # -> book.md (default)
poetry run python3 compile.py --data ./data --format json      # -> book.json
poetry run python3 compile.py --data ./data --format text      # -> book.txt
poetry run python3 compile.py --data ./data --format text --out ./chat.txt
```

`--format` chooses the output format: `markdown` (default), `json` or
`text`. If `--out` isn't given, the file name defaults to `book.md`,
`book.json` or `book.txt` to match the format.

- **markdown** (default): a chronological feed grouped by day, with photos
  embedded, videos and voice notes linked (the voice note is replaced by
  its transcript, with a link to the original audio file and a ⚠️ if
  confidence was low), and text links left as-is.
- **text**: the same content, without Markdown syntax — plain, readable
  lines grouped by day.
- **json**: a flat, chronologically ordered array of message objects
  (`id`, `datetime`, `day`, `sender`, `type`, `content`, `media_file`,
  `transcript`, `transcript_flagged`), meant for scripting or importing
  into another tool rather than reading directly.

Note: in the markdown and text formats, the day headers and a few short
inline annotations are rendered in French, since the book is meant to be a
readable copy of a French-language conversation. Everything else — the
code, the CLI, this README — is in English.

## Importing more later

When the conversation continues, repeat the 3 steps:

1. Make a new **WhatsApp export** (step 0) — it contains the whole history,
   not just what's new, that's fine.
2. Rerun `extract.py` into the **same** `--out ./data` folder (this
   overwrites `messages.json` with the up-to-date version, but transcripts
   already done in `transcripts.json` stay cached).
3. Rerun `transcribe.py` — only the new voice notes get transcribed.
4. Rerun `compile.py` — only messages after the last import
   (`data/cursor.json`) are added to `book.md`.

## Tests and linting

```bash
poetry run pytest        # 54 tests (pure functions + end-to-end on each script)
poetry run ruff check .  # lint (style, imports, common bugs)
```

The tests don't need `mlx-whisper` to pass: `transcribe.py` imports and
behaves correctly even without Apple Silicon (it exits cleanly with a clear
message), which lets them run on any machine. Only one test (ffmpeg
preprocessing) is skipped if `ffmpeg` isn't installed.

## Continuous integration

`.github/workflows/ci.yml` runs on a macOS runner (Apple Silicon required
for `mlx`) on every push/PR to `main`: it installs the project with Poetry,
checks the syntax of the three scripts, runs the linter (`ruff check .`) and
the test suite (`pytest`). It doesn't run an actual transcription (too slow,
and there's no versioned test audio content — intentionally, given the
privacy of the voice notes).

## Known limitations

- WhatsApp's native export caps out at ~10,000 messages with media (~40,000
  without). At your conversation's current pace, that's plenty of headroom,
  but if it ever becomes an issue, `extract.py` could be adapted to read the
  local database directly (via the `whatsapp-chat-exporter` tool) instead of
  the consumer-facing export — happy to revisit that when it comes up.
- WhatsApp system messages (phone number changes, encryption notices, etc.)
  aren't always recognized as such and may get silently absorbed into the
  previous message. No impact on text, voice notes, photos/videos or links.
- If an incremental import resumes partway through a day already started in
  `book.md`, that day's heading may appear twice — merge by hand if that
  bothers you.
- The `mlx_whisper.transcribe()` function and the structure of its segments
  (`start`, `end`, `avg_logprob`, `no_speech_prob`) may have changed
  depending on the installed version. If `transcribe.py` crashes on it, run
  `poetry run python3 -c "import mlx_whisper; help(mlx_whisper.transcribe)"`
  to see the exact parameter names to fix — a one-line change, nothing more.
- Each message's ID is now a hash of its content (stable across imports), so
  if a message is edited or deleted on WhatsApp's side after being
  transcribed, its existing transcript becomes orphaned (not reused, not
  deleted) and the "new" message gets retranscribed as if it were new.
- Switching `--format` between runs doesn't convert what was already
  compiled: it only appends newly-imported messages to whichever file
  matches the new format. For a full rebuild in a different format, delete
  `data/cursor.json` and the old output file first.
