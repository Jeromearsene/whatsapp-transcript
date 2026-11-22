#!/usr/bin/env python3
"""
compile.py — Step 3: assembles messages.json + transcripts.json into a
single output file, grouped by day, with incremental resume (a cursor
tracks the last message already compiled so only new ones are processed on
later imports).

Output format is chosen with --format: "markdown" (default), "json" or
"text". If --out isn't given, the output file defaults to book.md,
book.json or book.txt depending on the chosen format.

Usage:
    python3 compile.py --data ./data                      # -> book.md
    python3 compile.py --data ./data --format json        # -> book.json
    python3 compile.py --data ./data --format text --out ./chat.txt

To rebuild everything from scratch (e.g. after changing the rendering style):
    rm ./data/cursor.json ./book.md
    python3 compile.py --data ./data --out ./book.md

Note: switching --format between runs without clearing data/cursor.json
will only compile whatever became new since the last import into the new
file. Delete data/cursor.json (and the old output file) first if you want a
full rebuild in the new format.
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

# Day/month names are kept in French on purpose: the compiled output is a
# direct transcript of a French-language conversation, so its day headers
# render in French too, even though the surrounding code and CLI are in
# English.
WEEKDAYS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
             "août", "septembre", "octobre", "novembre", "décembre"]

DEFAULT_EXTENSIONS = {"markdown": "md", "json": "json", "text": "txt"}


def format_day(dt: datetime) -> str:
    return f"{WEEKDAYS_FR[dt.weekday()].capitalize()} {dt.day} {MONTHS_FR[dt.month - 1]} {dt.year}"


def render_message_markdown(msg: dict, transcript: dict | None, media_rel: str) -> str:
    sender = msg["sender"]
    time_str = datetime.fromisoformat(msg["datetime"]).strftime("%H:%M") if msg["datetime"] else "?"
    mtype = msg["type"]

    # The short annotations below ("(à vérifier)", "(pas encore transcrit)"...)
    # are written straight into the compiled output and are kept in French
    # for the same reason as the day headers above.
    if mtype == "text":
        body = msg["content"] or "*(message vide)*"
    elif mtype == "image":
        body = f"![photo]({media_rel}/{msg['media_file']})"
    elif mtype == "video":
        body = f"🎥 [vidéo]({media_rel}/{msg['media_file']})"
    elif mtype == "audio":
        if transcript and transcript.get("text"):
            flag = " ⚠️ *(à vérifier)*" if transcript.get("flagged") else ""
            body = (f"🎙️ {transcript['text']}{flag}  \n"
                    f"   [écouter l'original]({media_rel}/{msg['media_file']})")
        else:
            body = f"🎙️ *(pas encore transcrit)* — [écouter]({media_rel}/{msg['media_file']})"
    elif mtype == "document":
        body = f"📄 [{msg['media_file']}]({media_rel}/{msg['media_file']})"
    else:
        body = msg.get("content") or f"[{mtype}]"

    return f"**{sender}** ({time_str}) — {body}"


def render_message_text(msg: dict, transcript: dict | None, media_rel: str) -> str:
    """Same content as render_message_markdown, without Markdown syntax."""
    sender = msg["sender"]
    time_str = datetime.fromisoformat(msg["datetime"]).strftime("%H:%M") if msg["datetime"] else "?"
    mtype = msg["type"]

    if mtype == "text":
        body = msg["content"] or "(message vide)"
    elif mtype == "image":
        body = f"📷 photo : {media_rel}/{msg['media_file']}"
    elif mtype == "video":
        body = f"🎥 vidéo : {media_rel}/{msg['media_file']}"
    elif mtype == "audio":
        if transcript and transcript.get("text"):
            flag = " ⚠️ (à vérifier)" if transcript.get("flagged") else ""
            body = f"🎙️ {transcript['text']}{flag} (original : {media_rel}/{msg['media_file']})"
        else:
            body = f"🎙️ (pas encore transcrit) — {media_rel}/{msg['media_file']}"
    elif mtype == "document":
        body = f"📄 {media_rel}/{msg['media_file']}"
    else:
        body = msg.get("content") or f"[{mtype}]"

    return f"{sender} ({time_str}) — {body}"


def build_entry(msg: dict, transcript: dict | None) -> dict:
    """Structured representation of one message, used for the JSON format."""
    dt = datetime.fromisoformat(msg["datetime"]) if msg["datetime"] else None
    return {
        "id": msg.get("id"),
        "datetime": msg["datetime"],
        "day": format_day(dt) if dt else None,
        "sender": msg["sender"],
        "type": msg["type"],
        "content": msg.get("content"),
        "media_file": msg.get("media_file"),
        "transcript": transcript.get("text") if transcript else None,
        "transcript_flagged": transcript.get("flagged") if transcript else None,
    }


def compile_text_based(new_messages, transcripts, media_rel, out_file, resuming, render_fn, day_header_fn,
                        title_line):
    mode = "a" if resuming else "w"
    current_day = None
    with out_file.open(mode, encoding="utf-8") as f:
        if not resuming:
            f.write(title_line)
        else:
            # Start a fresh section: avoids appending text right after the
            # last existing paragraph with no line break in between.
            f.write("\n")
        for msg in new_messages:
            dt = datetime.fromisoformat(msg["datetime"])
            day = format_day(dt)
            if day != current_day:
                f.write(day_header_fn(day))
                current_day = day
            transcript = transcripts.get(str(msg["id"])) if msg["type"] == "audio" else None
            f.write(render_fn(msg, transcript, media_rel) + "\n\n")


def compile_json(new_messages, transcripts, out_file, resuming):
    entries = []
    if resuming and out_file.exists():
        entries = json.loads(out_file.read_text(encoding="utf-8"))
    for msg in new_messages:
        transcript = transcripts.get(str(msg["id"])) if msg["type"] == "audio" else None
        entries.append(build_entry(msg, transcript))
    out_file.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Compiles messages.json + transcripts.json into one file")
    parser.add_argument("--data", default="./data")
    parser.add_argument("--out", default=None,
                         help="Output file (default: ./book.md, ./book.json or ./book.txt, matching --format)")
    parser.add_argument("--format", choices=["markdown", "json", "text"], default="markdown",
                         help="Output format (default: markdown)")
    parser.add_argument("--media-dir-rel", default="data/media",
                         help="Relative path to the media folder from the output file (markdown/text only)")
    args = parser.parse_args()

    data_dir = Path(args.data).expanduser()
    out_file = Path(args.out).expanduser() if args.out else Path(f"./book.{DEFAULT_EXTENSIONS[args.format]}")
    state_file = data_dir / "cursor.json"

    messages_file = data_dir / "messages.json"
    if not messages_file.exists():
        raise SystemExit(f"{messages_file} not found — run extract.py first")

    messages = json.loads(messages_file.read_text(encoding="utf-8"))
    transcripts = {}
    tfile = data_dir / "transcripts.json"
    if tfile.exists():
        transcripts = json.loads(tfile.read_text(encoding="utf-8"))

    last_cursor = None
    if state_file.exists():
        last_cursor = json.loads(state_file.read_text(encoding="utf-8")).get("last_datetime")

    new_messages = [
        m for m in messages
        if m["datetime"] and (not last_cursor or m["datetime"] > last_cursor)
    ]

    if not new_messages:
        print("Nothing new to compile since the last import.")
        return

    resuming = out_file.exists() and last_cursor is not None

    if args.format == "markdown":
        compile_text_based(new_messages, transcripts, args.media_dir_rel, out_file, resuming,
                            render_message_markdown, lambda day: f"\n## {day}\n\n", "# Notre discussion\n\n")
    elif args.format == "text":
        compile_text_based(new_messages, transcripts, args.media_dir_rel, out_file, resuming,
                            render_message_text, lambda day: f"\n{day}\n{'-' * len(day)}\n\n",
                            "Notre discussion\n\n")
    else:  # json
        compile_json(new_messages, transcripts, out_file, resuming)

    last_dt = max(m["datetime"] for m in new_messages)
    state_file.write_text(json.dumps({"last_datetime": last_dt}, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{len(new_messages)} new messages compiled -> {out_file}")
    if resuming and args.format != "json":
        print("Note: since we're resuming partway through a day, that day's heading may "
              "appear a second time in the file if it was already started in a previous "
              "import — merge by hand if that bothers you.")


if __name__ == "__main__":
    main()
