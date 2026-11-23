import sys
import time
from pathlib import Path

import pytest

import run

# --- Pure prompt helpers ------------------------------------------------------

def test_ask_returns_input_or_default(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "custom value")
    assert run.ask("Prompt", "default") == "custom value"

    monkeypatch.setattr("builtins.input", lambda _: "")
    assert run.ask("Prompt", "default") == "default"


def test_ask_auto_mode_never_calls_input(monkeypatch):
    def boom(_):
        raise AssertionError("input() should not be called in auto mode")

    monkeypatch.setattr("builtins.input", boom)
    assert run.ask("Prompt", "default", auto=True) == "default"


@pytest.mark.parametrize("answer,expected", [("y", True), ("yes", True), ("n", False), ("no", False), ("", True)])
def test_ask_yes_no(monkeypatch, answer, expected):
    monkeypatch.setattr("builtins.input", lambda _: answer)
    assert run.ask_yes_no("Prompt?", default=True) == expected


def test_ask_yes_no_default_false_on_blank_answer(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "")
    assert run.ask_yes_no("Prompt?", default=False) is False


def test_ask_yes_no_auto_mode_never_calls_input(monkeypatch):
    def boom(_):
        raise AssertionError("input() should not be called in auto mode")

    monkeypatch.setattr("builtins.input", boom)
    assert run.ask_yes_no("Prompt?", default=True, auto=True) is True


def test_ask_choice_by_number_and_by_name(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "2")
    assert run.ask_choice("Pick one:", ["a", "b", "c"], "a") == "b"

    monkeypatch.setattr("builtins.input", lambda _: "c")
    assert run.ask_choice("Pick one:", ["a", "b", "c"], "a") == "c"

    monkeypatch.setattr("builtins.input", lambda _: "")
    assert run.ask_choice("Pick one:", ["a", "b", "c"], "a") == "a"


def test_ask_choice_invalid_falls_back_to_default(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "not-a-choice")
    assert run.ask_choice("Pick one:", ["a", "b", "c"], "b") == "b"


def test_ask_choice_auto_mode_never_calls_input(monkeypatch):
    def boom(_):
        raise AssertionError("input() should not be called in auto mode")

    monkeypatch.setattr("builtins.input", boom)
    assert run.ask_choice("Pick one:", ["a", "b"], "a", auto=True) == "a"


# --- guess_latest_export -------------------------------------------------------

def test_guess_latest_export_picks_most_recent(tmp_path, monkeypatch):
    monkeypatch.setattr(run.Path, "home", lambda: tmp_path)
    downloads = tmp_path / "Downloads"
    downloads.mkdir()

    older = downloads / "WhatsApp Chat with Jane.zip"
    older.write_bytes(b"\x00")
    time.sleep(0.01)
    newer = downloads / "WhatsApp Chat with Jane (1).zip"
    newer.write_bytes(b"\x00")

    assert run.guess_latest_export() == str(newer)


def test_guess_latest_export_returns_empty_when_nothing_found(tmp_path, monkeypatch):
    monkeypatch.setattr(run.Path, "home", lambda: tmp_path)  # no Downloads folder at all
    assert run.guess_latest_export() == ""


# --- run_step ------------------------------------------------------------------

def test_run_step_raises_systemexit_on_failure(monkeypatch):
    class FakeResult:
        returncode = 1

    monkeypatch.setattr(run.subprocess, "run", lambda cmd: FakeResult())
    with pytest.raises(SystemExit):
        run.run_step("extract.py", ["--export", "x"])


def test_run_step_passes_through_the_right_command(monkeypatch):
    class FakeResult:
        returncode = 0

    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        return FakeResult()

    monkeypatch.setattr(run.subprocess, "run", fake_run)
    run.run_step("extract.py", ["--export", "x"])

    assert Path(calls[0][1]).name == "extract.py"
    assert calls[0][-2:] == ["--export", "x"]


# --- main(): end-to-end wiring, with subprocess calls faked out ---------------

def test_main_auto_mode_runs_all_three_steps(tmp_path, monkeypatch):
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    export_zip = downloads / "WhatsApp Chat with Jane.zip"
    export_zip.write_bytes(b"\x00")
    monkeypatch.setattr(run.Path, "home", lambda: tmp_path)

    calls = []

    class FakeResult:
        returncode = 0

    def fake_run(cmd):
        calls.append(cmd)
        return FakeResult()

    monkeypatch.setattr(run.subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["run.py", "--data", str(tmp_path / "data"), "--yes"])

    run.main()

    scripts_called = [Path(c[1]).name for c in calls]
    assert scripts_called == ["extract.py", "transcribe.py", "compile.py"]
    assert str(export_zip) in calls[0]
    assert "large-v3" in calls[1]
    assert "markdown" in calls[2]


def test_main_without_export_found_exits_cleanly(tmp_path, monkeypatch):
    monkeypatch.setattr(run.Path, "home", lambda: tmp_path)  # no Downloads -> no guessed export
    monkeypatch.setattr(sys, "argv", ["run.py", "--data", str(tmp_path / "data"), "--yes"])
    with pytest.raises(SystemExit):
        run.main()
