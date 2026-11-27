#!/usr/bin/env python3
"""Check formatting in new Python files and lint diagnostics on changed lines."""

import os
import re
import subprocess
import sys
from pathlib import Path

HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
FLAKE8_RE = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+):(?P<column>\d+): "
    r"(?P<code>[A-Z]\d+) (?P<message>.*)$"
)


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def changed_python_ranges(
    base_sha: str,
) -> tuple[dict[str, list[tuple[int, int]]], set[str]]:
    result = run(["git", "diff", "--unified=0", base_sha, "--", "*.py"])
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git diff failed")

    ranges: dict[str, list[tuple[int, int]]] = {}
    current_path = None
    pending_new_file = False
    new_files = set()
    for line in result.stdout.splitlines():
        if line.startswith("--- /dev/null"):
            pending_new_file = True
            continue
        if line.startswith("+++ b/"):
            current_path = line[6:]
            if pending_new_file:
                new_files.add(current_path)
            pending_new_file = False
        elif line.startswith("+++ "):
            current_path = None
            pending_new_file = False
        elif current_path and line.startswith("@@"):
            match = HUNK_RE.match(line)
            if not match:
                raise RuntimeError(f"Unable to parse diff hunk: {line}")
            start = int(match.group(1))
            count = int(match.group(2) or 1)
            if count:
                ranges.setdefault(current_path, []).append((start, start + count - 1))
    return ranges, new_files


def changed_lines(ranges: list[tuple[int, int]]) -> set[int]:
    return {line for start, end in ranges for line in range(start, end + 1)}


def check_black(paths: set[str]) -> list[str]:
    if not paths:
        return []
    result = run(["black", "--check", "--quiet", *sorted(paths)])
    if result.returncode == 0:
        return []
    details = (result.stdout + result.stderr).strip()
    return [
        f"Black check failed for new Python files: {details or 'non-zero exit status'}"
    ]


def check_flake8(
    ranges: dict[str, list[tuple[int, int]]],
) -> tuple[list[str], int]:
    paths = [path for path in ranges if Path(path).is_file()]
    if not paths:
        return [], 0

    result = run(
        [
            "flake8",
            "--max-line-length=120",
            "--ignore=E501,W503",
            "--format=%(path)s:%(row)d:%(col)d: %(code)s %(text)s",
            *paths,
        ]
    )
    if result.returncode not in {0, 1}:
        details = (result.stdout + result.stderr).strip()
        return [f"Flake8 failed to run: {details or 'non-zero exit status'}"], 0
    if result.returncode == 1 and not result.stdout.strip():
        return ["Flake8 exited with errors but produced no diagnostics."], 0

    errors = []
    unchanged_diagnostic_count = 0
    for output_line in result.stdout.splitlines():
        match = FLAKE8_RE.match(output_line)
        if not match:
            errors.append(f"Unable to parse Flake8 output: {output_line}")
            continue
        path = Path(match.group("path")).as_posix()
        line = int(match.group("line"))
        if line in changed_lines(ranges.get(path, [])):
            errors.append(output_line)
        else:
            unchanged_diagnostic_count += 1
    return errors, unchanged_diagnostic_count


def main() -> int:
    base_sha = os.environ.get("BASE_SHA", "")
    if not re.fullmatch(r"[0-9a-f]{40}", base_sha):
        print("BASE_SHA must contain a full 40-character commit SHA.", file=sys.stderr)
        return 2

    ranges, new_files = changed_python_ranges(base_sha)
    ranges = {
        path: file_ranges
        for path, file_ranges in ranges.items()
        if Path(path).is_file() and file_ranges
    }
    if not ranges:
        print("No changed Python lines to check.")
        return 0

    new_python_files = new_files.intersection(ranges)
    failures = check_black(new_python_files)
    flake8_failures, unchanged_diagnostic_count = check_flake8(ranges)
    failures.extend(flake8_failures)

    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1

    if new_python_files:
        black_result = f"Black passed for {len(new_python_files)} new Python file(s)"
    else:
        black_result = "Black skipped (no new Python files)"
    print(
        f"{black_result}; Flake8 passed for changed lines in {len(ranges)} Python "
        f"file(s), with {unchanged_diagnostic_count} pre-existing diagnostic(s) ignored."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
