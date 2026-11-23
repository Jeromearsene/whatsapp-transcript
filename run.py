#!/usr/bin/env python3
"""
run.py — interactive wizard: walks you through extract.py, transcribe.py
and compile.py one step at a time, so you don't have to remember every
command-line flag.

Usage:
    python3 run.py
    python3 run.py --yes          # accept every suggested default, no prompts

Each step still just runs one of the three scripts, with the same flags and
behavior documented in the README — this wizard only asks the questions and
builds the command lines for you. If you'd rather call extract.py,
transcribe.py and compile.py yourself, that still works exactly as before.
"""
import argparse
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def ask(prompt: str, default: str = "", auto: bool = False) -> str:
    if auto:
        return default
    suffix = f" [{default}]" if default else ""
    answer = input(f"{prompt}{suffix}: ").strip()
    return answer or default


def ask_yes_no(prompt: str, default: bool = True, auto: bool = False) -> bool:
    if auto:
        return default
    suffix = " [Y/n]" if default else " [y/N]"
    answer = input(f"{prompt}{suffix}: ").strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes")


def ask_choice(prompt: str, choices: list[str], default: str, auto: bool = False) -> str:
    if auto:
        return default
    print(prompt)
    for i, choice in enumerate(choices, 1):
        marker = "  (default)" if choice == default else ""
        print(f"  {i}. {choice}{marker}")
    answer = input(f"Choice [1-{len(choices)}, Enter = default]: ").strip()
    if not answer:
        return default
    if answer.isdigit() and 1 <= int(answer) <= len(choices):
        return choices[int(answer) - 1]
    if answer in choices:
        return answer
    print("Unrecognized choice, using the default.")
    return default


def guess_latest_export() -> str:
    """Looks for the most recently modified WhatsApp export in ~/Downloads, to
    suggest it as a default rather than making you type out the full path.
    """
    downloads = Path.home() / "Downloads"
    if not downloads.exists():
        return ""
    candidates = sorted(downloads.glob("WhatsApp Chat*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    return str(candidates[0]) if candidates else ""


def run_step(script: str, args: list[str]) -> None:
    cmd = [sys.executable, str(SCRIPT_DIR / script), *args]
    print(f"\n$ {' '.join(cmd)}\n")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise SystemExit(f"\n{script} failed (exit code {result.returncode}) — stopping here.")


def main():
    parser = argparse.ArgumentParser(description="Interactive wizard: extract -> transcribe -> compile")
    parser.add_argument("--data", default="./data")
    parser.add_argument("--yes", action="store_true",
                         help="Accept every suggested default without asking (non-interactive)")
    args = parser.parse_args()
    auto = args.yes

    print("=== WhatsApp Transcript — interactive wizard ===\n")

    # --- Step 1: extract ---
    export_path = ask("WhatsApp export (.zip or already-extracted folder)", guess_latest_export(), auto=auto)
    if not export_path:
        raise SystemExit("No export path given — nothing to do.")
    extract_args = ["--export", export_path, "--out", args.data]
    if ask_yes_no("Filter by date range?", default=False, auto=auto):
        since = ask("From (DD/MM/YYYY, Enter = no limit)", auto=auto)
        until = ask("Until (DD/MM/YYYY, Enter = no limit)", auto=auto)
        if since:
            extract_args += ["--since", since]
        if until:
            extract_args += ["--until", until]
    run_step("extract.py", extract_args)

    # --- Step 2: transcribe ---
    if ask_yes_no("\nTranscribe voice notes now?", default=True, auto=auto):
        model = ask_choice("Transcription model:", ["large-v3", "large-v3-turbo", "medium"],
                            "large-v3", auto=auto)
        run_step("transcribe.py", ["--data", args.data, "--model", model])

    # --- Step 3: compile ---
    if ask_yes_no("\nCompile the book now?", default=True, auto=auto):
        fmt = ask_choice("Output format:", ["markdown", "json", "text"], "markdown", auto=auto)
        run_step("compile.py", ["--data", args.data, "--format", fmt])

    print("\nDone.")


if __name__ == "__main__":
    main()
