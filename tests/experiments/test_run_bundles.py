"""Bundling run evidence is lossless, readable in place and reversible."""

import pytest

from research.experiments import run_bundles, stage2b_replay


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as writer:
        writer.write(text)


def _snapshot(root):
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*")) if path.is_file()}


def test_bundle_groups_twenty_cases_and_extract_restores_bytes(tmp_path):
    for number in (1, 2, 20, 21):
        _write(tmp_path / f"case-{number:02d}" / "attempt-001.json", '{"a": 1}\r\n')
        _write(tmp_path / f"case-{number:02d}" / "sub" / "note.txt", f"Lan nạp {number} ADA\n")
    _write(tmp_path / "case-03-attempt-01.json", "{}")
    _write(tmp_path / "run_case_wsl.sh", "#!/bin/sh\n")
    before = _snapshot(tmp_path)

    written = run_bundles.bundle(tmp_path)
    assert [path.name for path in written] == ["cases-01-20.jsonl", "cases-21-40.jsonl"]
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "cases-01-20.jsonl", "cases-21-40.jsonl", "run_case_wsl.sh"]

    cases = dict(run_bundles.iter_cases(tmp_path))
    assert list(cases) == ["case-01", "case-02", "case-03", "case-20", "case-21"]
    assert cases["case-21"]["sub/note.txt"] == "Lan nạp 21 ADA\n"
    assert cases["case-03"] == {"case-03-attempt-01.json": "{}"}

    for path in written:
        run_bundles.extract(path)
    assert _snapshot(tmp_path) == before


def test_bundle_refuses_to_overwrite_and_extract_refuses_existing_files(tmp_path):
    _write(tmp_path / "case-01" / "a.json", "{}")
    (bundle,) = run_bundles.bundle(tmp_path)
    _write(tmp_path / "case-01" / "a.json", "{}")
    with pytest.raises(FileExistsError):
        run_bundles.extract(bundle)
    with pytest.raises(FileExistsError):
        run_bundles.bundle(tmp_path)


def test_replay_reads_bundled_cases(tmp_path):
    _write(tmp_path / "case-01" / "logical-model-outputs.jsonl", "")
    run_bundles.bundle(tmp_path)
    assert stage2b_replay.replay_runs([tmp_path])["cases"] == {"case-01": {"outputs": []}}
