import subprocess
import sys
import zipfile
from pathlib import Path

import extract

# --- Pure functions ----------------------------------------------------------

def test_line_re_bracket_matches_ios_format():
    line = "[18/11/2026, 09:15:32] John Doe: Hi!"
    m = extract.LINE_RE_BRACKET.match(line)
    assert m is not None
    assert m.group("date") == "18/11/2026"
    assert m.group("time") == "09:15:32"
    assert m.group("sender") == "John Doe"
    assert m.group("content") == "Hi!"


def test_line_re_dash_matches_legacy_format():
    line = "18/11/2026, 09:15 - John Doe: Hi!"
    m = extract.LINE_RE_DASH.match(line)
    assert m is not None
    assert m.group("date") == "18/11/2026"
    assert m.group("sender") == "John Doe"
    assert m.group("content") == "Hi!"


def test_parse_datetime_with_seconds():
    dt = extract.parse_datetime("18/11/2026", "09:15:32")
    assert dt is not None
    assert (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second) == (2026, 11, 18, 9, 15, 32)


def test_parse_datetime_without_seconds():
    dt = extract.parse_datetime("18/11/2026", "09:15")
    assert dt is not None
    assert (dt.hour, dt.minute) == (9, 15)


def test_parse_datetime_invalid_returns_none():
    assert extract.parse_datetime("not-a-date", "??:??") is None


def test_find_media_file_found_and_not_found():
    media_files = ["00001-AUDIO.opus", "00002-PHOTO.jpg"]
    content = "‎<attached: 00002-PHOTO.jpg>"
    assert extract.find_media_file(content, media_files) == "00002-PHOTO.jpg"
    assert extract.find_media_file("nothing relevant here", media_files) is None


def test_assign_stable_id_is_deterministic():
    msg = {"datetime": "2026-11-18T09:15:00", "sender": "John", "type": "text",
           "content": "Hi", "media_file": None}
    id_a = extract.assign_stable_id(dict(msg), {})
    id_b = extract.assign_stable_id(dict(msg), {})
    assert id_a == id_b


def test_assign_stable_id_disambiguates_exact_duplicates():
    msg = {"datetime": "2026-11-18T09:15:00", "sender": "John", "type": "text",
           "content": "+1", "media_file": None}
    dup_counter = {}
    id_1 = extract.assign_stable_id(dict(msg), dup_counter)
    id_2 = extract.assign_stable_id(dict(msg), dup_counter)
    assert id_1 != id_2
    assert id_2 == f"{id_1}-1"


# --- Integration test: the full script on a fake export ---------------------

CHAT_TXT = """\
[01/11/2026, 09:00:00] John Doe: ‎<attached: 00001-PHOTO.jpg>
[01/11/2026, 09:01:15] Jane Smith: Hi! How are you?
It's been a while since we talked
[01/11/2026, 09:05:00] John Doe: ‎<attached: 00002-AUDIO.opus>
[02/11/2026, 10:00:00] John Doe: ‎<attached: 00003-VIDEO.mp4>
"""


def _make_fake_export(tmp_path: Path) -> Path:
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    (export_dir / "_chat.txt").write_text(CHAT_TXT, encoding="utf-8")
    (export_dir / "00001-PHOTO.jpg").write_bytes(b"\x00")
    (export_dir / "00002-AUDIO.opus").write_bytes(b"\x00")
    (export_dir / "00003-VIDEO.mp4").write_bytes(b"\x00")
    return export_dir


def _run_extract(export_dir: Path, out_dir: Path, extra_args: list[str] | None = None):
    script = Path(extract.__file__)
    cmd = [sys.executable, str(script), "--export", str(export_dir), "--out", str(out_dir)]
    cmd += extra_args or []
    return subprocess.run(cmd, capture_output=True, text=True, check=True)


def test_extract_end_to_end(tmp_path):
    import json

    export_dir = _make_fake_export(tmp_path)
    out_dir = tmp_path / "data"
    _run_extract(export_dir, out_dir)

    messages = json.loads((out_dir / "messages.json").read_text(encoding="utf-8"))
    assert len(messages) == 4
    types = [m["type"] for m in messages]
    assert types == ["image", "text", "audio", "video"]
    assert (out_dir / "media" / "00002-AUDIO.opus").exists()


def test_extract_ids_are_stable_across_runs(tmp_path):
    import json

    export_dir = _make_fake_export(tmp_path)
    out_dir = tmp_path / "data"
    _run_extract(export_dir, out_dir)
    ids_run1 = [m["id"] for m in json.loads((out_dir / "messages.json").read_text(encoding="utf-8"))]

    _run_extract(export_dir, out_dir)  # second run, same input
    ids_run2 = [m["id"] for m in json.loads((out_dir / "messages.json").read_text(encoding="utf-8"))]

    assert ids_run1 == ids_run2


def test_extract_date_filter(tmp_path):
    import json

    export_dir = _make_fake_export(tmp_path)
    out_dir = tmp_path / "data"
    _run_extract(export_dir, out_dir, ["--since", "02/11/2026"])

    messages = json.loads((out_dir / "messages.json").read_text(encoding="utf-8"))
    assert len(messages) == 1
    assert messages[0]["type"] == "video"


def test_extract_from_zip_archive_finds_media(tmp_path):
    """Regression test: the default, documented workflow is to pass a .zip
    export, not an already-extracted folder. In that case extract.py unzips
    into out_dir/"_raw", which is nested *inside* --out by design — a
    previous bug excluded everything under --out as a (presumed) already-
    copied destination file, which silently discarded every real source file
    in this exact default case, turning every photo/voice note/video into a
    plain text message referencing the attachment that was never copied.
    """
    import json

    build_dir = tmp_path / "to_zip"
    build_dir.mkdir()
    export_dir = _make_fake_export(build_dir)
    zip_path = tmp_path / "WhatsApp Chat with Jane.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for f in export_dir.iterdir():
            zf.write(f, arcname=f.name)

    out_dir = tmp_path / "data"  # unrelated to zip_path: out_dir/"_raw" will be created fresh
    _run_extract(zip_path, out_dir)

    messages = json.loads((out_dir / "messages.json").read_text(encoding="utf-8"))
    types = [m["type"] for m in messages]
    assert types == ["image", "text", "audio", "video"]
    assert all(m["media_file"] is not None for m in messages if m["type"] != "text")
    assert (out_dir / "media" / "00002-AUDIO.opus").exists()
