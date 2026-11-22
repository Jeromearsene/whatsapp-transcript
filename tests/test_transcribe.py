import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import transcribe

# --- Pure functions ----------------------------------------------------------

def test_format_timestamp():
    assert transcribe.format_timestamp(0) == "00:00"
    assert transcribe.format_timestamp(65) == "01:05"
    assert transcribe.format_timestamp(-5) == "00:00"  # never negative


def test_confidence_score_empty_segments():
    assert transcribe.confidence_score({"segments": []}) == -1.0


def test_confidence_score_average():
    result = {"segments": [{"avg_logprob": -0.2}, {"avg_logprob": -0.4}]}
    assert transcribe.confidence_score(result) == pytest.approx(-0.3)


def test_find_weak_segments_flags_low_confidence_and_no_speech():
    result = {
        "segments": [
            {"start": 0.0, "end": 1.0, "text": " ok ", "avg_logprob": -0.1, "no_speech_prob": 0.05},
            {"start": 1.0, "end": 2.0, "text": "uncertain", "avg_logprob": -1.5, "no_speech_prob": 0.05},
            {"start": 2.0, "end": 3.0, "text": "noise", "avg_logprob": -0.1, "no_speech_prob": 0.9},
        ]
    }
    weak = transcribe.find_weak_segments(result, threshold=-0.8, no_speech_threshold=0.6)
    assert [w["text"] for w in weak] == ["uncertain", "noise"]
    # kept segments have their text stripped of extra whitespace
    assert all("text" in w for w in weak)


def test_load_save_json_roundtrip(tmp_path):
    path = tmp_path / "data.json"
    assert transcribe.load_json(path) == {}  # missing file -> empty dict
    transcribe.save_json(path, {"a": 1})
    assert transcribe.load_json(path) == {"a": 1}


def test_write_review_file_lists_segments_and_cleans_up_when_empty(tmp_path):
    review_file = tmp_path / "to_review.md"
    transcripts = {
        "abc123": {
            "media_file": "00002-AUDIO.opus",
            "flagged_segments": [
                {"start": 1.0, "end": 3.5, "text": "uncertain passage"},
            ],
        },
        "def456": {"media_file": "00004-AUDIO.opus", "flagged_segments": []},
    }
    total = transcribe.write_review_file(review_file, transcripts)
    assert total == 1
    content = review_file.read_text(encoding="utf-8")
    assert "00002-AUDIO.opus" in content
    assert "uncertain passage" in content
    assert "00:01" in content and "00:03" in content

    # No flagged segment left -> the file gets deleted, not left empty
    total = transcribe.write_review_file(review_file, {"abc123": {"media_file": "x", "flagged_segments": []}})
    assert total == 0
    assert not review_file.exists()


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_preprocess_audio_produces_a_wav_file(tmp_path):
    src = tmp_path / "test.opus"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-c:a", "libopus", str(src)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    result = transcribe.preprocess_audio(src, out_dir)
    assert result.exists()
    assert result.suffix == ".wav"


# --- Light integration test (without mlx-whisper) ----------------------------

def test_transcribe_without_mlx_whisper_exits_cleanly(tmp_path):
    """Without mlx-whisper installed, the script must stop cleanly with a
    clear message rather than a stack trace — which is what will happen on
    any machine that isn't an Apple Silicon Mac.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "messages.json").write_text(json.dumps([]), encoding="utf-8")

    script = Path(transcribe.__file__)
    proc = subprocess.run(
        [sys.executable, str(script), "--data", str(data_dir)],
        capture_output=True, text=True,
    )
    if transcribe.mlx_whisper is None:
        assert proc.returncode != 0
        assert "mlx-whisper is not installed" in proc.stdout + proc.stderr
    else:
        pytest.skip("mlx-whisper is installed in this environment")
