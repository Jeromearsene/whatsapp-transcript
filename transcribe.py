#!/usr/bin/env python3
"""
transcribe.py — Step 2: transcribes every voice message (type == "audio")
listed in data/messages.json using mlx-whisper (100% local, Apple Silicon).

Usage:
    python3 transcribe.py --data ./data
    python3 transcribe.py --data ./data --model large-v3-turbo   # favor speed over accuracy
    python3 transcribe.py --data ./data --threshold -0.6         # stricter review flagging
    python3 transcribe.py --data ./data --skip-preprocess        # disable audio preprocessing

Resuming: voice notes already transcribed (present in data/transcripts.json)
are not reprocessed, so you can rerun this script after a new incremental
import without redoing everything. Failed files (data/errors.json) are
retried automatically on the next run, since they're never added to
transcripts.json until they succeed.

Audio preprocessing: before transcription, each file goes through ffmpeg
(volume normalization + light noise reduction) — useful since some WhatsApp
voice notes are of middling audio quality. If ffmpeg fails on a given file,
the script falls back to the original file instead of giving up.

Targeted review: rather than flagging an entire voice note as soon as one
passage is uncertain, each low-confidence SEGMENT is listed separately in
data/to_review.md with its timestamp in the file, so you only need to
re-listen to a few seconds rather than the whole note.

NB: the exact signature of mlx_whisper.transcribe() and the structure of its
segments can vary slightly depending on the installed version. If it crashes
on first try:
    poetry run python3 -c "import mlx_whisper; help(mlx_whisper.transcribe)"
gives you the exact parameter names to fix — a one-line change, nothing more.
"""
import argparse
import json
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

try:
    import mlx_whisper
except ImportError:
    mlx_whisper = None

MODEL_REPOS = {
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
    "medium": "mlx-community/whisper-medium-mlx",
}


def format_timestamp(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def preprocess_audio(src_path: Path, tmp_dir: Path) -> Path:
    """Normalizes volume and reduces noise before transcription (via ffmpeg).

    Returns the path to the processed file (.wav, 16kHz mono). Raises an
    exception if ffmpeg fails — it's up to the caller to fall back to the
    original file.
    """
    dest_path = tmp_dir / (src_path.stem + ".wav")
    cmd = [
        "ffmpeg", "-y", "-i", str(src_path),
        "-af", "afftdn=nf=-25,loudnorm=I=-16:TP=-1.5:LRA=11",
        "-ar", "16000", "-ac", "1",
        str(dest_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
    return dest_path


def confidence_score(result: dict) -> float:
    """Average of the segments' avg_logprob: closer to 0 means more confident."""
    segments = result.get("segments", [])
    if not segments:
        return -1.0
    scores = [s.get("avg_logprob", -1.0) for s in segments]
    return sum(scores) / len(scores)


def find_weak_segments(result: dict, threshold: float, no_speech_threshold: float) -> list[dict]:
    """Individually doubtful segments: low confidence, or likely noise/silence
    misread as speech (high no_speech_prob) rather than an actual
    transcription. We flag the precise passage, not the whole file.
    """
    weak = []
    for seg in result.get("segments", []):
        avg_logprob = seg.get("avg_logprob", 0.0)
        no_speech = seg.get("no_speech_prob", 0.0)
        if avg_logprob < threshold or no_speech > no_speech_threshold:
            weak.append({
                "start": seg.get("start", 0.0),
                "end": seg.get("end", 0.0),
                "text": (seg.get("text") or "").strip(),
                "avg_logprob": round(avg_logprob, 3),
                "no_speech_prob": round(no_speech, 3),
            })
    return weak


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_review_file(review_file: Path, transcripts: dict) -> int:
    """Rewrites data/to_review.md with every segment to review, grouped by
    audio file. Returns the total number of segments listed, and removes the
    file if there's nothing left to review.
    """
    total = 0
    lines = [
        "# Low-confidence passages to review\n",
        "Each line points to a specific passage, with its timestamp in the "
        "original audio file — no need to re-listen to the whole voice note.\n",
    ]
    for t in transcripts.values():
        segs = t.get("flagged_segments") or []
        if not segs:
            continue
        lines.append(f"\n## `{t['media_file']}`\n")
        for seg in segs:
            total += 1
            lines.append(f"- [{format_timestamp(seg['start'])}–{format_timestamp(seg['end'])}] {seg['text']}")

    if total:
        review_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    elif review_file.exists():
        review_file.unlink()
    return total


def main():
    parser = argparse.ArgumentParser(description="Transcribes WhatsApp voice notes with mlx-whisper")
    parser.add_argument("--data", default="./data", help="Folder containing messages.json and media/")
    parser.add_argument("--model", default="large-v3", choices=list(MODEL_REPOS.keys()),
                         help="large-v3 = most accurate (recommended given variable audio quality)")
    parser.add_argument("--threshold", type=float, default=-0.8,
                         help="Confidence score (avg_logprob) below which a SEGMENT is flagged")
    parser.add_argument("--no-speech-threshold", type=float, default=0.6,
                         help="Non-speech probability above which a segment is flagged")
    parser.add_argument("--language", default="fr")
    parser.add_argument("--skip-preprocess", action="store_true",
                         help="Disable ffmpeg preprocessing (normalization/denoising) and "
                              "send the raw file straight to Whisper")
    args = parser.parse_args()

    if mlx_whisper is None:
        raise SystemExit(
            "mlx-whisper is not installed.\n"
            "Install it with: poetry install\n"
            "(also requires ffmpeg: brew install ffmpeg)"
        )

    data_dir = Path(args.data).expanduser()
    media_dir = data_dir / "media"
    messages_file = data_dir / "messages.json"
    transcripts_file = data_dir / "transcripts.json"
    errors_file = data_dir / "errors.json"
    review_file = data_dir / "to_review.md"

    if not messages_file.exists():
        raise SystemExit(f"{messages_file} not found — run extract.py first")

    messages = json.loads(messages_file.read_text(encoding="utf-8"))
    transcripts = load_json(transcripts_file)
    errors = load_json(errors_file)

    audio_msgs = [m for m in messages if m["type"] == "audio" and m.get("media_file")]
    todo = [m for m in audio_msgs if str(m["id"]) not in transcripts]
    retried = sum(1 for m in todo if m["media_file"] in errors)
    already_cached = len(audio_msgs) - len(todo)
    status = f"{len(audio_msgs)} voice notes total, {len(todo)} to transcribe ({already_cached} already cached"
    status += f", including {retried} previously failed, now retried" if retried else ""
    print(status + ").")

    if not todo:
        return

    model_repo = MODEL_REPOS[args.model]

    with tempfile.TemporaryDirectory(prefix="whatsapp_audio_") as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        for i, msg in enumerate(todo, 1):
            audio_path = media_dir / msg["media_file"]
            if not audio_path.exists():
                print(f"  [!] file not found, skipped: {audio_path}")
                errors[msg["media_file"]] = {
                    "error": "file not found in data/media",
                    "when": datetime.now().isoformat(),
                }
                save_json(errors_file, errors)
                continue

            print(f"  ({i}/{len(todo)}) {msg['media_file']} ...", flush=True)

            transcribe_path = audio_path
            if not args.skip_preprocess:
                try:
                    transcribe_path = preprocess_audio(audio_path, tmp_dir)
                except Exception as exc:
                    print(f"      [!] ffmpeg preprocessing failed, using the raw file: {exc}")
                    transcribe_path = audio_path

            try:
                result = mlx_whisper.transcribe(
                    str(transcribe_path), path_or_hf_repo=model_repo, language=args.language
                )
            except Exception as exc:
                print(f"      -> transcription failed: {exc}")
                errors[msg["media_file"]] = {"error": str(exc), "when": datetime.now().isoformat()}
                save_json(errors_file, errors)
                if transcribe_path != audio_path:
                    transcribe_path.unlink(missing_ok=True)
                continue

            if transcribe_path != audio_path:
                transcribe_path.unlink(missing_ok=True)

            weak_segments = find_weak_segments(result, args.threshold, args.no_speech_threshold)
            transcripts[str(msg["id"])] = {
                "text": result["text"].strip(),
                "confidence": round(confidence_score(result), 3),
                "flagged": bool(weak_segments),
                "flagged_segments": weak_segments,
                "media_file": msg["media_file"],
            }
            errors.pop(msg["media_file"], None)

            # Saved as we go: an interruption (Ctrl+C, power loss) doesn't lose
            # everything, and you can resume later with the same command.
            save_json(transcripts_file, transcripts)
            save_json(errors_file, errors)

    print(f"\nTranscripts saved to {transcripts_file}")

    n_segments = write_review_file(review_file, transcripts)
    print(f"{n_segments} low-confidence passage(s) -> {review_file}" if n_segments
          else "No passage flagged for review.")

    if errors:
        print(f"{len(errors)} failed file(s) -> {errors_file} (will be retried on the next run)")


if __name__ == "__main__":
    main()
