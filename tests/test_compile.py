import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import compile as compile_mod  # "compile" is a valid module name (not a Python keyword)

# --- Pure functions ----------------------------------------------------------

def test_format_day():
    # November 18, 2026 is a Wednesday. The output is in French by design: the
    # compiled output mirrors the conversation it comes from (see compile.py).
    dt = datetime(2026, 11, 18, 9, 0)
    assert compile_mod.format_day(dt) == "Mercredi 18 novembre 2026"


def test_render_markdown_text():
    msg = {"sender": "John", "datetime": "2026-11-18T09:15:00", "type": "text",
           "content": "Hi!", "media_file": None}
    rendered = compile_mod.render_message_markdown(msg, None, "media")
    assert rendered == "**John** (09:15) — Hi!"


def test_render_markdown_image():
    msg = {"sender": "John", "datetime": "2026-11-18T09:15:00", "type": "image",
           "content": None, "media_file": "photo.jpg"}
    rendered = compile_mod.render_message_markdown(msg, None, "media")
    assert "![photo](media/photo.jpg)" in rendered


def test_render_markdown_audio_with_transcript():
    msg = {"sender": "John", "datetime": "2026-11-18T09:15:00", "type": "audio",
           "content": None, "media_file": "voice.opus"}
    transcript = {"text": "Hey, how's it going", "flagged": False}
    rendered = compile_mod.render_message_markdown(msg, transcript, "media")
    assert "Hey, how's it going" in rendered
    assert "⚠️" not in rendered
    assert "media/voice.opus" in rendered


def test_render_markdown_audio_flagged():
    msg = {"sender": "John", "datetime": "2026-11-18T09:15:00", "type": "audio",
           "content": None, "media_file": "voice.opus"}
    transcript = {"text": "Unsure passage", "flagged": True}
    rendered = compile_mod.render_message_markdown(msg, transcript, "media")
    assert "⚠️" in rendered


def test_render_markdown_audio_without_transcript_yet():
    msg = {"sender": "John", "datetime": "2026-11-18T09:15:00", "type": "audio",
           "content": None, "media_file": "voice.opus"}
    rendered = compile_mod.render_message_markdown(msg, None, "media")
    assert "pas encore transcrit" in rendered


def test_render_markdown_document():
    msg = {"sender": "John", "datetime": "2026-11-18T09:15:00", "type": "document",
           "content": None, "media_file": "report.pdf"}
    rendered = compile_mod.render_message_markdown(msg, None, "media")
    assert "media/report.pdf" in rendered


def test_render_text_has_no_markdown_syntax():
    msg = {"sender": "John", "datetime": "2026-11-18T09:15:00", "type": "text",
           "content": "Hi!", "media_file": None}
    rendered = compile_mod.render_message_text(msg, None, "media")
    assert rendered == "John (09:15) — Hi!"
    assert "**" not in rendered


def test_render_text_image_and_audio():
    img = {"sender": "John", "datetime": "2026-11-18T09:15:00", "type": "image",
           "content": None, "media_file": "photo.jpg"}
    rendered_img = compile_mod.render_message_text(img, None, "media")
    assert "media/photo.jpg" in rendered_img
    assert "![" not in rendered_img and "](" not in rendered_img

    audio = {"sender": "John", "datetime": "2026-11-18T09:15:00", "type": "audio",
             "content": None, "media_file": "voice.opus"}
    transcript = {"text": "Unsure passage", "flagged": True}
    rendered_audio = compile_mod.render_message_text(audio, transcript, "media")
    assert "Unsure passage" in rendered_audio
    assert "⚠️" in rendered_audio
    assert "](" not in rendered_audio  # no markdown link syntax


def test_build_entry_text_message():
    msg = {"id": "a1", "sender": "John", "datetime": "2026-11-18T09:15:00", "type": "text",
           "content": "Hi!", "media_file": None}
    entry = compile_mod.build_entry(msg, None)
    assert entry == {
        "id": "a1", "datetime": "2026-11-18T09:15:00", "day": "Mercredi 18 novembre 2026",
        "sender": "John", "type": "text", "content": "Hi!", "media_file": None,
        "transcript": None, "transcript_flagged": None,
    }


def test_build_entry_audio_with_transcript():
    msg = {"id": "a2", "sender": "Jane", "datetime": "2026-11-18T09:20:00", "type": "audio",
           "content": None, "media_file": "voice.opus"}
    transcript = {"text": "Unsure passage", "flagged": True}
    entry = compile_mod.build_entry(msg, transcript)
    assert entry["transcript"] == "Unsure passage"
    assert entry["transcript_flagged"] is True


# --- Integration tests --------------------------------------------------------

def _write_messages(data_dir: Path, messages: list[dict]) -> None:
    (data_dir / "messages.json").write_text(json.dumps(messages, ensure_ascii=False), encoding="utf-8")


def _write_transcripts(data_dir: Path, transcripts: dict) -> None:
    (data_dir / "transcripts.json").write_text(json.dumps(transcripts, ensure_ascii=False), encoding="utf-8")


def _run_compile(data_dir: Path, out_file: Path, fmt: str | None = None):
    script = Path(compile_mod.__file__)
    cmd = [
        sys.executable, str(script),
        "--data", str(data_dir), "--out", str(out_file), "--media-dir-rel", "media",
    ]
    if fmt:
        cmd += ["--format", fmt]
    return subprocess.run(cmd, capture_output=True, text=True, check=True)


def test_compile_default_format_is_markdown(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    out_file = tmp_path / "book.md"
    msg = {"id": "a1", "datetime": "2026-11-01T09:00:00", "sender": "John",
           "type": "text", "content": "First message", "media_file": None}
    _write_messages(data_dir, [msg])
    _run_compile(data_dir, out_file)  # no --format passed
    assert "**John**" in out_file.read_text(encoding="utf-8")


def test_compile_incremental_import(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    out_file = tmp_path / "book.md"

    msg1 = {"id": "a1", "datetime": "2026-11-01T09:00:00", "sender": "John",
            "type": "text", "content": "First message", "media_file": None}
    _write_messages(data_dir, [msg1])
    _run_compile(data_dir, out_file)

    content_after_first = out_file.read_text(encoding="utf-8")
    assert "First message" in content_after_first

    # Second run with no new message: nothing should change.
    result_no_new = _run_compile(data_dir, out_file)
    assert "Nothing new" in result_no_new.stdout
    assert out_file.read_text(encoding="utf-8") == content_after_first

    # A new message arrives (incremental import): only it should be appended.
    msg2 = {"id": "a2", "datetime": "2026-11-02T10:00:00", "sender": "Jane",
            "type": "text", "content": "Second message", "media_file": None}
    _write_messages(data_dir, [msg1, msg2])
    _run_compile(data_dir, out_file)

    final_content = out_file.read_text(encoding="utf-8")
    assert "First message" in final_content
    assert "Second message" in final_content
    assert final_content.startswith(content_after_first)  # history is never rewritten


def test_compile_text_format(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    out_file = tmp_path / "book.txt"
    msg = {"id": "a1", "datetime": "2026-11-01T09:00:00", "sender": "John",
           "type": "text", "content": "First message", "media_file": None}
    _write_messages(data_dir, [msg])
    _run_compile(data_dir, out_file, fmt="text")

    content = out_file.read_text(encoding="utf-8")
    assert "First message" in content
    assert "John (09:00)" in content
    assert "**" not in content
    assert "![" not in content


def test_compile_json_format(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    out_file = tmp_path / "book.json"

    msg_text = {"id": "a1", "datetime": "2026-11-01T09:00:00", "sender": "John",
                "type": "text", "content": "First message", "media_file": None}
    msg_audio = {"id": "a2", "datetime": "2026-11-01T09:05:00", "sender": "Jane",
                 "type": "audio", "content": None, "media_file": "voice.opus"}
    _write_messages(data_dir, [msg_text, msg_audio])
    _write_transcripts(data_dir, {"a2": {"text": "Unsure passage", "flagged": True}})

    _run_compile(data_dir, out_file, fmt="json")

    entries = json.loads(out_file.read_text(encoding="utf-8"))
    assert len(entries) == 2
    assert entries[0]["content"] == "First message"
    assert entries[1]["transcript"] == "Unsure passage"
    assert entries[1]["transcript_flagged"] is True


def test_compile_json_format_incremental_import(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    out_file = tmp_path / "book.json"

    msg1 = {"id": "a1", "datetime": "2026-11-01T09:00:00", "sender": "John",
            "type": "text", "content": "First message", "media_file": None}
    _write_messages(data_dir, [msg1])
    _run_compile(data_dir, out_file, fmt="json")
    assert len(json.loads(out_file.read_text(encoding="utf-8"))) == 1

    msg2 = {"id": "a2", "datetime": "2026-11-02T10:00:00", "sender": "Jane",
            "type": "text", "content": "Second message", "media_file": None}
    _write_messages(data_dir, [msg1, msg2])
    _run_compile(data_dir, out_file, fmt="json")

    entries = json.loads(out_file.read_text(encoding="utf-8"))
    assert len(entries) == 2
    assert [e["content"] for e in entries] == ["First message", "Second message"]


def test_compile_default_output_filename_matches_format(tmp_path):
    script = Path(compile_mod.__file__)
    msg = {"id": "a1", "datetime": "2026-11-01T09:00:00", "sender": "John",
           "type": "text", "content": "Hello", "media_file": None}

    for fmt, ext in [("markdown", "md"), ("json", "json"), ("text", "txt")]:
        run_dir = tmp_path / fmt
        data_dir = run_dir / "data"
        data_dir.mkdir(parents=True)
        _write_messages(data_dir, [msg])
        subprocess.run(
            [sys.executable, str(script), "--data", str(data_dir), "--format", fmt],
            cwd=run_dir, capture_output=True, text=True, check=True,
        )
        assert (run_dir / f"book.{ext}").exists()
