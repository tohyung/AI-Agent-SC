"""Build or check dataset/all_cases.jsonl: every case of every dataset in one file.

Each line holds one case exactly as its source file has it, plus which dataset it comes from and what it
was used for. The source files stay where they are, because their frozen SHA-256 values and the runners
depend on them; this file only gathers them for reading.

    python -m dataset.all_cases           # write dataset/all_cases.jsonl
    python -m dataset.all_cases --check   # fail if a source changed or the combined file is stale

Two hash conventions were used when the datasets were frozen: v2 and v3 over the bytes as they sit on
disk (see .gitattributes), v4 and v5 over LF-only bytes. A source passes when its frozen value matches
either form.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "all_cases.jsonl"

# (dataset, path relative to dataset/, frozen SHA-256, used for, used in the results report)
SOURCES = (
    ("v2", "cases.jsonl", "e05c23f43a2bd025258ad5e2fa77569874357f79173e98863a8f8d48ee9a907a",
     "RQ1 (E4), RQ2 (E5); also E2, E3", True),
    ("supplement", "supplement/conflicts_author_v1.jsonl",
     "4e107995b796960a03e51c212bff007cba1bba4e251dc522c5e3e860ad4294e8", "RQ1 (E4), conflict cases", True),
    ("v3", "v3/cases.jsonl", "cdc0ea456f2e103d86bb195522b6510755e65fdd5c9f9e1e2342cf68ad6e46cc",
     "E6 (not in the report)", False),
    ("v4", "v4/cases.jsonl", "d9609682a9b3e4a239eb7731a26fc36cd41f3b2897791b537271197d8d48fc1b",
     "E7 dry runs only (v3 prompts)", False),
    ("v5", "v5/cases.jsonl", "85f70d4330a547663706381a8079e0b3176769d669946235650340cdd8d09cae",
     "RQ3, RQ4 (E7)", True),
)


def source_hashes(path: Path) -> tuple[str, str]:
    """Return the SHA-256 of the file as stored on disk and of its LF-only bytes."""
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest(), hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def check_sources() -> list[str]:
    """Return one problem per source whose bytes no longer match its frozen hash."""
    problems = []
    for name, relative, frozen, _, _ in SOURCES:
        if frozen not in source_hashes(HERE / relative):
            problems.append(f"{name}: {relative} does not match its frozen SHA-256 {frozen[:12]}…")
    return problems


def build() -> str:
    """Return the text of all_cases.jsonl."""
    lines = []
    for name, relative, frozen, used_for, in_report in SOURCES:
        rows = (HERE / relative).read_text(encoding="utf-8").splitlines()
        for number, row in enumerate((row for row in rows if row.strip()), start=1):
            lines.append(json.dumps({"dataset": name, "index": number, "source": f"dataset/{relative}",
                                     "source_sha256": frozen, "used_for": used_for,
                                     "in_report": in_report, "case": json.loads(row)},
                                    ensure_ascii=False, sort_keys=True))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="check instead of writing")
    args = parser.parse_args(argv)
    problems = check_sources()
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    text = build()
    if args.check:
        current = OUT.read_bytes().replace(b"\r\n", b"\n").decode("utf-8") if OUT.exists() else ""
        if current != text:
            print("dataset/all_cases.jsonl is stale; run python -m dataset.all_cases", file=sys.stderr)
            return 1
        print(f"ok: {text.count(chr(10))} cases, every source matches its frozen hash")
        return 0
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(HERE.parent)}: {text.count(chr(10))} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
