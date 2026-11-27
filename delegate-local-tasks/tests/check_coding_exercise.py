#!/usr/bin/env python3
"""Check a manually reviewed implementation of the documented coding exercise."""
import runpy
import sys


def main(path):
    module = runpy.run_path(path)
    retry = module["retry_after_seconds"]
    cases = [
        ("absent", None, 120, None),
        ("empty", " ", 120, None),
        ("zero", " 0 ", 120, 0),
        ("normal", " 17 ", 120, 17),
        ("cap", "121", 120, 120),
        ("custom cap", "10", 3, 3),
        ("negative", "-1", 120, None),
        ("plus", "+1", 120, None),
        ("decimal", "1.5", 120, None),
        ("space", "1 2", 120, None),
        ("unicode", "１２", 120, None),
        ("superscript", "²", 120, None),
        ("huge", "9" * 5000, 120, 120),
        ("leading zeros", "0" * 5000 + "1", 120, 1),
    ]
    failures = []
    for label, value, cap, expected in cases:
        try:
            result = retry(value, cap)
            if result != expected or type(result) is not type(expected):
                failures.append(f"{label}: got {result!r}")
        except Exception as exc:
            failures.append(f"{label}: {type(exc).__name__}")
    if [module["delay_for_attempt"](i) for i in range(8)] != [1, 2, 4, 8, 16, 32, 60, 60]:
        failures.append("delay_for_attempt changed")
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        return 1
    print(f"Passed {len(cases)} cases and the existing-function check.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: check_coding_exercise.py REVIEWED_CANDIDATE.py")
    sys.exit(main(sys.argv[1]))
