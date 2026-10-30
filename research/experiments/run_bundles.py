"""Bundle finished per-case run evidence, 20 cases per JSONL file, losslessly.

A case is either a directory `case-NN/` or flat files named `case-NN-*`. Each
bundle line is one original file: {"case", "path", "sha256", "text"}, where
`path` is relative to the batch directory and `text` is the exact UTF-8 text,
so `extract` restores byte-identical files. Readers use `iter_cases`, which
sees loose case files and bundles the same way.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Iterator
from pathlib import Path

CASE = re.compile(r"case-(\d+)")
BUNDLE = re.compile(r"cases-(\d+)-(\d+)\.jsonl\Z")
SIZE = 20


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read(path: Path) -> str:
    # newline="" keeps CRLF exactly as written.
    with path.open(encoding="utf-8", newline="") as source:
        return source.read()


def loose_cases(batch: Path) -> dict[str, dict[str, Path]]:
    """Map case name -> {path relative to the batch: file} for unbundled evidence."""
    cases: dict[str, dict[str, Path]] = {}
    for entry in sorted(batch.iterdir()):
        match = CASE.match(entry.name)
        if not match:
            continue
        name = f"case-{int(match.group(1)):02d}"
        if entry.is_dir():
            files = {path.relative_to(batch).as_posix(): path
                     for path in sorted(entry.rglob("*")) if path.is_file()}
        elif entry.is_file():
            files = {entry.name: entry}
        else:
            continue
        cases.setdefault(name, {}).update(files)
    return cases


def iter_cases(batch: Path) -> Iterator[tuple[str, dict[str, str]]]:
    """Yield (case name, {path inside the case: text}) from bundles and loose files.

    Files of a `case-NN/` directory are keyed relative to that directory.
    """
    merged: dict[str, dict[str, str]] = {}
    for bundle in sorted(batch.glob("cases-*.jsonl")):
        for line in _read(bundle).splitlines():
            row = json.loads(line)
            merged.setdefault(row["case"], {})[row["path"]] = row["text"]
    for name, files in loose_cases(batch).items():
        merged.setdefault(name, {}).update({rel: _read(path) for rel, path in files.items()})
    for name in sorted(merged, key=lambda item: int(CASE.match(item).group(1))):
        yield name, {rel.split("/", 1)[1] if "/" in rel else rel: text
                     for rel, text in merged[name].items()}


def bundle(batch: Path, size: int = SIZE) -> list[Path]:
    """Write one bundle per block of `size` case numbers, verify it, then remove originals."""
    cases = loose_cases(batch)
    blocks: dict[int, list[str]] = {}
    for name in cases:
        number = int(CASE.match(name).group(1))
        blocks.setdefault((number - 1) // size, []).append(name)
    written = []
    for block, names in sorted(blocks.items()):
        target = batch / f"cases-{block * size + 1:02d}-{block * size + size:02d}.jsonl"
        if target.exists():
            raise FileExistsError(f"{target} already exists; extract it before re-bundling")
        rows = [{"case": name, "path": rel, "sha256": _sha(text), "text": text}
                for name in sorted(names) for rel, path in cases[name].items()
                for text in (_read(path),)]
        with target.open("x", encoding="utf-8", newline="\n") as writer:
            for row in rows:
                writer.write(json.dumps(row, ensure_ascii=False) + "\n")
        restored = [json.loads(line) for line in _read(target).splitlines()]
        if [(row["case"], row["path"], _sha(row["text"])) for row in restored] != [
                (row["case"], row["path"], row["sha256"]) for row in rows]:
            target.unlink()
            raise RuntimeError(f"verification failed for {target}")
        for name in names:
            for path in cases[name].values():
                path.unlink()
            folder = batch / name
            if folder.is_dir():
                for directory in sorted(folder.rglob("*"), reverse=True):
                    if directory.is_dir():
                        directory.rmdir()
                folder.rmdir()
        written.append(target)
    return written


def extract(bundle_path: Path) -> int:
    """Restore a bundle's files next to it; refuse to overwrite anything."""
    batch = bundle_path.parent
    rows = [json.loads(line) for line in _read(bundle_path).splitlines()]
    for row in rows:
        target = batch / row["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8", newline="") as writer:
            writer.write(row["text"])
        if _sha(_read(target)) != row["sha256"]:
            raise RuntimeError(f"restored file differs: {target}")
    bundle_path.unlink()
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Bundle or restore per-case run evidence")
    sub = parser.add_subparsers(dest="command", required=True)
    pack = sub.add_parser("bundle")
    pack.add_argument("batch", type=Path)
    unpack = sub.add_parser("extract")
    unpack.add_argument("bundle", type=Path)
    args = parser.parse_args()
    if args.command == "bundle":
        for path in bundle(args.batch):
            print(path)
    else:
        print(f"restored {extract(args.bundle)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
