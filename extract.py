#!/usr/bin/env python3
"""
extract.py — Step 1: parses a WhatsApp export (.zip or an already-extracted
folder) into a structured list of messages (messages.json), copying the
media files into a separate folder.

Usage:
    python3 extract.py --export "~/Downloads/WhatsApp Chat with XXX.zip" --out ./data
    python3 extract.py --export ./already_extracted_folder --out ./data
    python3 extract.py --export ... --out ./data --since 01/10/2026 --until 31/10/2026

The _chat.txt file is parsed line by line with a regular expression. To work
out which media file (photo, video, voice note...) a message refers to, we
don't rely on WhatsApp's exact wording (which changes depending on the
phone's language) but on the real file name being present in the line,
which is robust regardless of the export's language.
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path

MEDIA_EXT = {
    "image": {".jpg", ".jpeg", ".png", ".webp", ".gif"},
    "video": {".mp4", ".mov", ".3gp"},
    "audio": {".opus", ".m4a", ".mp3", ".aac"},
    "document": {".pdf", ".doc", ".docx", ".xls", ".xlsx"},
}
EXT_TO_TYPE = {ext: t for t, exts in MEDIA_EXT.items() for ext in exts}

# Two possible timestamp formats depending on the WhatsApp version / OS:
#   [18/11/2026, 09:15:32] John Doe: message      (recent iOS)
#   18/11/2026, 09:15 - John Doe: message          (legacy format / Android)
LINE_RE_BRACKET = re.compile(
    r"^‎?\[(?P<date>\d{1,2}/\d{1,2}/\d{2,4}),?\s+(?P<time>\d{1,2}:\d{2}(:\d{2})?(\s?[AP]M)?)\]\s+"
    r"(?P<sender>[^:]+):\s?(?P<content>.*)$"
)
LINE_RE_DASH = re.compile(
    r"^‎?(?P<date>\d{1,2}/\d{1,2}/\d{2,4}),?\s+(?P<time>\d{1,2}:\d{2}(\s?[AP]M)?)\s*-\s*"
    r"(?P<sender>[^:]+):\s?(?P<content>.*)$"
)

DATETIME_FORMATS = [
    "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
    "%d/%m/%y %H:%M:%S", "%d/%m/%y %H:%M",
    "%d/%m/%Y %I:%M:%S %p", "%d/%m/%Y %I:%M %p",
]


def parse_datetime(date_str: str, time_str: str):
    time_str = time_str.replace(" ", " ").strip()  # iOS sometimes inserts a non-breaking space
    for fmt in DATETIME_FORMATS:
        try:
            return datetime.strptime(f"{date_str} {time_str}", fmt)
        except ValueError:
            continue
    return None


def find_media_file(content: str, media_files: list[str]):
    for name in media_files:
        if name in content:
            return name
    return None


def load_export(export_path: Path, raw_dir: Path) -> Path:
    """Unzips the export if it's a .zip, returns the folder containing _chat.txt + media."""
    if export_path.is_dir():
        return export_path
    raw_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(export_path) as zf:
        zf.extractall(raw_dir)
    return raw_dir


def find_chat_txt(raw_dir: Path) -> Path:
    for candidate in raw_dir.rglob("_chat.txt"):
        return candidate
    txts = [p for p in raw_dir.rglob("*.txt")]
    if not txts:
        sys.exit(f"No .txt file found in {raw_dir} — is the export actually complete?")
    return txts[0]


def parse_date_arg(value: str) -> datetime:
    return datetime.strptime(value, "%d/%m/%Y")


def assign_stable_id(msg: dict, dup_counter: dict) -> str:
    """Content-based ID rather than one based on the message's position in the list.

    This way, a message keeps the same ID across imports (as long as its
    content doesn't change), which avoids desyncing transcripts.json and
    cursor.json if the parsing logic ever evolves. Exact duplicates (same
    timestamp, same sender, same content) are disambiguated with a counter —
    deterministic as long as the message order doesn't change.
    """
    key = "||".join([
        msg["datetime"] or "",
        msg["sender"],
        msg["type"],
        msg["content"] or "",
        msg["media_file"] or "",
    ])
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    n = dup_counter.get(h, 0)
    dup_counter[h] = n + 1
    return h if n == 0 else f"{h}-{n}"


def main():
    parser = argparse.ArgumentParser(description="Parses a WhatsApp export into messages.json")
    parser.add_argument("--export", required=True, help="Exported .zip file or already-extracted folder")
    parser.add_argument("--out", default="./data", help="Output folder (default: ./data)")
    parser.add_argument("--since", help="Only keep messages from this date onward (DD/MM/YYYY)")
    parser.add_argument("--until", help="Only keep messages up to and including this date (DD/MM/YYYY)")
    args = parser.parse_args()

    export_path = Path(args.export).expanduser()
    out_dir = Path(args.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    media_dir = out_dir / "media"
    media_dir.mkdir(exist_ok=True)

    since = parse_date_arg(args.since) if args.since else None
    until = parse_date_arg(args.until) if args.until else None

    raw_dir = load_export(export_path, out_dir / "_raw")
    chat_txt = find_chat_txt(raw_dir)

    # List all source media files first (before copying anything): if --out is
    # a subfolder of --export, copying while scanning would make the scan pick
    # up the files we just copied and count them twice.
    source_files = [
        f for f in raw_dir.rglob("*")
        if f.is_file() and f.suffix.lower() in EXT_TO_TYPE and out_dir not in f.parents
    ]
    media_files = []
    for f in source_files:
        dest = media_dir / f.name
        if not dest.exists():
            shutil.copy2(f, dest)
        media_files.append(f.name)

    lines = chat_txt.read_text(encoding="utf-8", errors="replace").splitlines()

    messages = []
    current = None
    for line in lines:
        m = LINE_RE_BRACKET.match(line) or LINE_RE_DASH.match(line)
        if m:
            if current:
                messages.append(current)
            date_str = m.group("date")
            time_str = m.group("time")
            sender = m.group("sender").strip()
            content = m.group("content").strip()
            dt = parse_datetime(date_str, time_str)
            current = {"datetime": dt, "sender": sender, "raw_content": content}
        else:
            if current is not None and line.strip():
                current["raw_content"] += "\n" + line
    if current:
        messages.append(current)

    # Optional date filter
    if since or until:
        filtered = []
        for msg in messages:
            d = msg["datetime"]
            if d is None:
                continue
            if since and d.date() < since.date():
                continue
            if until and d.date() > until.date():
                continue
            filtered.append(msg)
        messages = filtered

    # Assign type + attach media
    for msg in messages:
        media_name = find_media_file(msg["raw_content"], media_files)
        if media_name:
            ext = Path(media_name).suffix.lower()
            msg["type"] = EXT_TO_TYPE.get(ext, "document")
            msg["media_file"] = media_name
            msg["content"] = None
        else:
            msg["type"] = "text"
            msg["media_file"] = None
            msg["content"] = msg["raw_content"] or None
        del msg["raw_content"]
        msg["datetime"] = msg["datetime"].isoformat() if msg["datetime"] else None

    messages.sort(key=lambda m: m["datetime"] or "")
    dup_counter = {}
    for msg in messages:
        msg["id"] = assign_stable_id(msg, dup_counter)

    out_file = out_dir / "messages.json"
    out_file.write_text(json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8")

    counts = {}
    for msg in messages:
        counts[msg["type"]] = counts.get(msg["type"], 0) + 1
    print(f"{len(messages)} messages extracted -> {out_file}")
    for t, c in sorted(counts.items()):
        print(f"  - {t}: {c}")
    if messages:
        print(f"  Date range: {messages[0]['datetime']} -> {messages[-1]['datetime']}")
    print(f"Media copied to {media_dir} ({len(media_files)} files)")


if __name__ == "__main__":
    main()
